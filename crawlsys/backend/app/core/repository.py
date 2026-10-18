"""TaskRepo — CRUD operations on the t_crawl_task table."""
from __future__ import annotations

import json

from datetime import datetime, timezone

from sqlalchemy import select, inspect, update, delete, or_, func, case

from core.param_schema import InvalidActionParamSchema, normalize_action_param_schema
from core.task_schedule import ScheduleRule, next_schedule_at
from models.task import BusTask, TaskPriority, TaskScheduleType, TaskStatus, TaskTrigger
from models.action import Action
from models.datatype import SysDatatype, introspect_datatype_models
from models.keyword import BusiSearchKeyword
from models.platform import platformSource, PlatformStatus
from common.logging import get_logger
from storage import SQLAlchemyDB
logger = get_logger(__file__)


class TaskRepo:
    def __init__(self, db: SQLAlchemyDB):
        self.db = db

    @staticmethod
    def _as_aware_utc(value: datetime | None) -> datetime | None:
        """SQLite 存储无时区时间；统一按 UTC 解释以便与 aware now 比较。"""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _executor_filter(executor: str | None):
        normalized = executor.strip() if executor and executor.strip() else "rpc_crawl"
        stored_executor = func.nullif(func.trim(BusTask.config["executor"].as_string()), "")
        return func.coalesce(stored_executor, "rpc_crawl") == normalized

    async def reclaim_stuck_running(
        self,
        older_than: datetime,
        platform: str | None = None,
        *,
        executor: str | None = "rpc_crawl",
    ) -> int:
        """将卡在 RUNNING 且更新时间早于 older_than 的任务回滚为 PENDING。

        用于 Worker 异常退出后，避免任务永久停留在 RUNNING 而无法被重新调度。
        """
        async with self.db.asession_scope() as session:
            stmt = (
                update(BusTask)
                .where(
                    BusTask.status == TaskStatus.RUNNING.value,
                    BusTask.updated_at < older_than,
                    self._executor_filter(executor),
                )
                .values(
                    status=TaskStatus.PENDING.value,
                    error_msg="reclaimed after timeout",
                    next_retry_at=case(
                        (
                            BusTask.active_trigger == TaskTrigger.RETRY.value,
                            func.coalesce(
                                BusTask.next_retry_at,
                                BusTask.active_scheduled_at,
                            ),
                        ),
                        else_=BusTask.next_retry_at,
                    ),
                    run_now_requested_at=case(
                        (
                            BusTask.active_trigger == TaskTrigger.MANUAL.value,
                            func.coalesce(
                                BusTask.run_now_requested_at,
                                BusTask.active_scheduled_at,
                            ),
                        ),
                        else_=BusTask.run_now_requested_at,
                    ),
                )
            )
            if platform:
                stmt = stmt.where(BusTask.platform == platform)
            result = await session.execute(stmt)
            return result.rowcount

    async def heartbeat_running(
        self,
        task_id: int,
        *,
        executor: str,
        platform: str | None = None,
    ) -> bool:
        """Refresh only a RUNNING task owned by the given executor."""
        async with self.db.asession_scope() as session:
            stmt = (
                update(BusTask)
                .where(
                    BusTask.task_id == task_id,
                    BusTask.status == TaskStatus.RUNNING.value,
                    self._executor_filter(executor),
                )
                .values(updated_at=datetime.now())
            )
            if platform:
                stmt = stmt.where(BusTask.platform == platform)
            result = await session.execute(stmt)
            return result.rowcount == 1

    async def update_priority(
        self,
        task_id: int,
        priority: TaskPriority,
    ) -> BusTask | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                update(BusTask)
                .where(BusTask.task_id == task_id)
                .values(priority=priority.db_value)
                .returning(BusTask)
            )
            return result.scalar_one_or_none()

    async def get_pending_tasks(
        self,
        platform: str | None = None,
        *,
        executor: str | None = "rpc_crawl",
        limit: int = 10,
    ) -> list[BusTask]:
        """原子领取到期任务，并写入本次物理尝试的触发快照。

        到期来源三个：重试（next_retry_at）、立即执行（run_now_requested_at）、
        常规计划（next_run_at）。触发来源顺序优先；同一来源内按业务优先级从高到低；
        领取只消费本次对应的请求字段。
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        async with self.db.asession_scope() as session:
            now = datetime.now(timezone.utc)
            retry_due = BusTask.next_retry_at.is_not(None) & (BusTask.next_retry_at <= func.now())
            stmt = select(BusTask).where(
                BusTask.status == TaskStatus.PENDING.value,
                or_(
                    retry_due,
                    BusTask.run_now_requested_at.is_not(None),
                    BusTask.next_run_at.is_(None),
                    BusTask.next_run_at <= func.now(),
                ),
                self._executor_filter(executor),
            )
            if platform:
                stmt = stmt.where(BusTask.platform == platform)
            trigger_rank = case(
                (retry_due, 0),
                (BusTask.run_now_requested_at.is_not(None), 1),
                else_=2,
            )
            due_at = case(
                (retry_due, BusTask.next_retry_at),
                (
                    BusTask.run_now_requested_at.is_not(None),
                    BusTask.run_now_requested_at,
                ),
                else_=BusTask.next_run_at,
            )
            stmt = (
                stmt.order_by(
                    trigger_rank.asc(),
                    BusTask.priority.desc(),
                    due_at.asc().nulls_first(),
                    BusTask.task_id.asc(),
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )

            result = await session.execute(stmt)
            tasks = list(result.scalars().all())

            claimed_now = datetime.now()
            for t in tasks:
                retry_at = self._as_aware_utc(t.next_retry_at)
                if retry_at is not None and retry_at <= now:
                    t.active_trigger = TaskTrigger.RETRY.value
                    t.active_scheduled_at = t.next_retry_at
                    t.next_retry_at = None
                elif t.run_now_requested_at is not None:
                    t.active_trigger = TaskTrigger.MANUAL.value
                    t.active_scheduled_at = t.run_now_requested_at
                    t.run_now_requested_at = None
                else:
                    t.active_trigger = TaskTrigger.SCHEDULED.value
                    t.active_scheduled_at = t.next_run_at
                t.status = TaskStatus.RUNNING.value
                t.updated_at = claimed_now

            return tasks

    async def request_run_now(self, task_id: int) -> bool:
        """幂等排队一次立即执行请求；返回 False 表示任务不存在或已达次数上限。

        运行中重复请求只保留最早一次（合并触发），由 Worker 在下一轮消费。
        """
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(BusTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            if task.max_runs is not None and task.run_count >= task.max_runs:
                return False
            end_at = self._as_aware_utc(task.schedule_end_at)
            if end_at is not None and datetime.now(timezone.utc) > end_at:
                return False
            if task.run_now_requested_at is None:
                task.run_now_requested_at = datetime.now(timezone.utc)
            return True

    async def pause(self, task_id: int) -> bool:
        """暂停任务：running 设置 pause_requested（本轮结束后暂停）；
        其他可调度状态直接置为 paused。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(BusTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            if task.status == TaskStatus.RUNNING.value:
                task.pause_requested = True
            else:
                task.status = TaskStatus.PAUSED.value
            return True

    async def resume(self, task_id: int, *, next_run_at: datetime | None) -> bool:
        """恢复任务：清除暂停与合并请求，并从当前时刻恢复未来计划。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(BusTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if task is None:
                return False
            task.pause_requested = False
            if task.status == TaskStatus.RUNNING.value:
                return True
            task.run_now_requested_at = None
            task.status = TaskStatus.PENDING.value
            task.error_msg = None
            task.next_run_at = next_run_at
            return True

    async def recompute_cron_schedules(self, *, timezone_name: str, now: datetime) -> int:
        """按新时区重算 pending/paused Cron 任务的 next_run_at。

        running 任务在本轮结束后读取最新 Scheduler 配置，不在此重算；
        同时清除暂停期间遗留的合并请求（run_now_requested_at）。
        """
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(
                    BusTask.schedule_type == TaskScheduleType.CRON.value,
                    BusTask.status.in_(
                        [TaskStatus.PENDING.value, TaskStatus.PAUSED.value]
                    ),
                )
            )
            tasks = list(result.scalars().all())
            updated = 0
            for task in tasks:
                if not task.cron_expression:
                    continue
                task.next_run_at = next_schedule_at(
                    ScheduleRule(
                        type="cron",
                        cron_expression=task.cron_expression,
                        start_at=task.schedule_start_at,
                        end_at=task.schedule_end_at,
                    ),
                    now=now,
                    timezone_name=timezone_name,
                )
                if task.status == TaskStatus.PAUSED.value:
                    task.run_now_requested_at = None
                updated += 1
            return updated

    async def save(self, task: BusTask) -> BusTask | None:
        async with self.db.asession_scope() as session:
            return await self.save_in_session(session, task)

    async def save_in_session(self, session, task: BusTask) -> BusTask | None:
        """Save a task without taking ownership of the caller's transaction."""
        return await self._merge_task_in_session(session, task)

    async def init_tasks(self, platform: str, task_configs: list[dict]) -> None:
        from models.task_config import TaskConfig, SourceConfig, SinkConfig

        existing = await self._get_existing_actions(platform)
        new_tasks: list[BusTask] = []
        for cfg in task_configs:
            action = cfg["action"]
            if action in existing:
                continue
            source_raw = cfg.get("source")
            sink_raw = cfg.get("sink")
            task_config = TaskConfig(
                source=SourceConfig(**source_raw) if source_raw else None,
                sink=SinkConfig(**sink_raw) if sink_raw else SinkConfig(),
            )
            new_tasks.append(BusTask(
                platform=platform,
                action=action,
                status=TaskStatus.PENDING,
                config=task_config,
            ))
        if new_tasks:
            await self._insert_tasks(new_tasks)
            logger.info("Initialized %d tasks for %s", len(new_tasks), platform)

    async def _merge_task(self, task: BusTask) -> BusTask | None:
        async with self.db.asession_scope() as session:
            return await self._merge_task_in_session(session, task)

    async def _merge_task_in_session(self, session, task: BusTask) -> BusTask | None:
        # 新建任务 task_id 为 None，直接 merge（insert）；
        # 仅当 task_id 已知时才校验它是否仍存在，避免新任务被误判为“不存在”而跳过保存。
        if task.task_id is not None:
            result = await session.execute(
                select(BusTask.task_id).where(BusTask.task_id == task.task_id)
            )
            if result.scalar_one_or_none() is None:
                logger.info("Task %d no longer exists, skipping save", task.task_id)
                return

        def _safe_merge(sync_session):
            # merge 对新建任务（task_id=None）会插入新行，返回的是 pending
            # 状态对象；已有任务则必须保持 persistent，避免并发删除后被重新插入。
            merged = sync_session.merge(task)
            if task.task_id is None:
                return merged
            st = inspect(merged)
            if not st.persistent:
                sync_session.expunge(merged)
                return None
            return merged

        persisted = await session.run_sync(_safe_merge)
        if persisted is None:
            logger.info(
                "Task %d was concurrently deleted during merge, skipping save",
                task.task_id,
            )
        return persisted

    async def _get_existing_actions(self, platform: str) -> set[str]:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask.action).where(BusTask.platform == platform)
            )
            return {row[0] for row in result.all()}

    async def _insert_tasks(self, tasks: list[BusTask]) -> None:
        await self.db.aadds(tasks)

    async def find_all(self, platform: str | None = None) -> list[BusTask]:
        """获取所有任务，按 task_id 降序。可选按 platform 过滤。"""
        async with self.db.asession_scope() as session:
            stmt = select(BusTask).order_by(BusTask.task_id)
            if platform:
                stmt = stmt.where(BusTask.platform == platform)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_id(self, task_id: int) -> BusTask | None:
        """按主键查找任务。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(BusTask.task_id == task_id)
            )
            return result.scalar_one_or_none()

    async def delete(self, task_id: int) -> None:
        """按主键删除任务。"""
        async with self.db.asession_scope() as session:
            await session.execute(
                delete(BusTask).where(BusTask.task_id == task_id)
            )

    async def set_status(self, task_id: int, status: TaskStatus) -> bool:
        """设置单个任务状态。返回是否成功找到任务。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusTask).where(BusTask.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return False
            task.status = status.value
            if status == TaskStatus.PENDING:
                task.error_msg = None
            return True

    async def batch_set_status(
        self, platform: str | None, status: TaskStatus, skip_running: bool = False
    ) -> int:
        """批量更新任务状态，返回影响行数。

        Args:
            platform: 可选按平台过滤
            status: 目标状态
            skip_running: 如果为 True，跳过 RUNNING 状态的任务（用于 pause-all）
        """
        async with self.db.asession_scope() as session:
            stmt = update(BusTask)
            if platform:
                stmt = stmt.where(BusTask.platform == platform)
            if skip_running:
                stmt = stmt.where(BusTask.status != TaskStatus.RUNNING.value)
            values = {"status": status.value}
            if status == TaskStatus.PENDING:
                values["error_msg"] = None
            result = await session.execute(stmt.values(**values))
            return result.rowcount


class ActionRepo:
    """CRUD operations on the t_busi_action table."""

    def __init__(self, db: SQLAlchemyDB):
        self.db = db

    async def find_by_platform(self, bs_id: int) -> list[Action]:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(Action)
                .where(Action.bs_id == bs_id, Action.ba_enabled.is_(True))
                .order_by(Action.ba_action)
            )
            return list(result.scalars().all())

    async def find_all(self, platform_id: int | None = None) -> list[Action]:
        async with self.db.asession_scope() as session:
            stmt = select(Action).order_by(Action.bs_id, Action.ba_action)
            if platform_id:
                stmt = stmt.where(Action.bs_id == platform_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_id(self, ba_id: int) -> Action | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(Action).where(Action.ba_id == ba_id)
            )
            return result.scalar_one_or_none()

    async def find_by_name(self, bs_id: int, name: str) -> Action | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(Action).where(
                    Action.bs_id == bs_id, Action.ba_action == name
                )
            )
            return result.scalar_one_or_none()

    async def save(self, action: Action) -> Action:
        async with self.db.asession_scope() as session:
            managed = await session.merge(action)
            await session.flush()
            await session.refresh(managed)
            return managed

    async def update(self, ba_id: int, **kwargs) -> bool:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(Action).where(Action.ba_id == ba_id)
            )
            action = result.scalar_one_or_none()
            if not action:
                return False
            for key, value in kwargs.items():
                if hasattr(action, key):
                    setattr(action, key, value)
            return True

    async def delete_with_unlink(self, ba_id: int) -> None:
        """删除接口定义，同时将该接口关联的任务的 ba_id 置空。"""
        async with self.db.asession_scope() as session:
            await session.execute(
                update(BusTask).where(BusTask.ba_id == ba_id).values(ba_id=None)
            )
            await session.flush()
            await session.execute(
                delete(Action).where(Action.ba_id == ba_id)
            )

    async def batch_update_status(self, action_ids: list[int], enabled: bool) -> int:
        if not action_ids:
            return 0
        async with self.db.asession_scope() as session:
            result = await session.execute(
                update(Action)
                .where(Action.ba_id.in_(action_ids))
                .values(ba_enabled=enabled)
            )
            return result.rowcount

    async def get_schema(
        self,
        ba_id: int,
    ) -> dict[str, object] | bool | None:
        """获取并规范化 action 的 params schema。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(Action).where(Action.ba_id == ba_id)
            )
            action = result.scalar_one_or_none()
            if action is None or action.ba_params_schema is None:
                return None
            try:
                schema = json.loads(action.ba_params_schema)
            except (json.JSONDecodeError, TypeError):
                raise InvalidActionParamSchema("invalid JSON Schema") from None
            return normalize_action_param_schema(schema)


class PlatformRepo:
    """CRUD operations on the t_busi_platform table."""

    def __init__(self, db: SQLAlchemyDB):
        self.db = db

    async def find_all_active(self) -> list[platformSource]:
        """加载未软删除的平台列表（bs_status != 'D'）。"""
        async with self.db.asession_scope() as session:
            stmt = (
                select(platformSource)
                .where(
                    (platformSource.bs_status != PlatformStatus.DELETED)
                    | platformSource.bs_status.is_(None)
                )
                .order_by(platformSource.bs_id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_all_enabled(self) -> list[platformSource]:
        """加载所有启用且平台代码有效的平台。"""
        async with self.db.asession_scope() as session:
            stmt = (
                select(platformSource)
                .where(
                    platformSource.bs_status == PlatformStatus.ENABLED,
                    platformSource.bs_platform_code.isnot(None),
                    func.trim(platformSource.bs_platform_code) != "",
                )
                .order_by(platformSource.bs_id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_all(self, include_deleted: bool = False) -> list[platformSource]:
        async with self.db.asession_scope() as session:
            stmt = select(platformSource).order_by(platformSource.bs_id)
            if not include_deleted:
                stmt = stmt.where(
                    (platformSource.bs_status != PlatformStatus.DELETED)
                    | platformSource.bs_status.is_(None)
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_id(self, bs_id: int) -> platformSource | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(platformSource.bs_id == bs_id)
            )
            return result.scalar_one_or_none()

    async def find_by_code(self, code: str) -> platformSource | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(platformSource.bs_platform_code == code)
            )
            return result.scalar_one_or_none()

    async def find_by_name(self, name: str) -> platformSource | None:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(platformSource.bs_name == name)
            )
            return result.scalar_one_or_none()

    async def save(self, platform: platformSource) -> platformSource:
        async with self.db.asession_scope() as session:
            merged = await session.merge(platform)
            await session.flush()
            await session.refresh(merged)
            return merged

    async def soft_delete(self, bs_id: int) -> bool:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(platformSource.bs_id == bs_id)
            )
            platform = result.scalar_one_or_none()
            if not platform:
                return False
            platform.bs_status = PlatformStatus.DELETED
            return True

    async def restore(self, bs_id: int) -> bool:
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(platformSource.bs_id == bs_id)
            )
            platform = result.scalar_one_or_none()
            if not platform:
                return False
            platform.bs_status = PlatformStatus.ENABLED
            return True


class KeywordRepo:
    """CRUD operations on the t_busi_search_keyword table."""

    def __init__(self, db: SQLAlchemyDB):
        self.db = db

    async def find_all(self, platform: str | None = None) -> list:
        """返回全部关键词，按 platform ASC、created_at DESC 排序。
        可选按 platform 过滤。
        """

        async with self.db.asession_scope() as session:
            stmt = select(BusiSearchKeyword).order_by(
                BusiSearchKeyword.platform.asc(),
                BusiSearchKeyword.created_at.desc(),
            )
            if platform:
                stmt = stmt.where(BusiSearchKeyword.platform == platform)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_id(self, kid: int):
        """按主键查找。"""

        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusiSearchKeyword).where(BusiSearchKeyword.id == kid)
            )
            return result.scalar_one_or_none()

    async def save(self, kw) -> BusiSearchKeyword:
        """插入或更新（merge 按主键判断）。"""
        async with self.db.asession_scope() as session:
            merged = await session.merge(kw)
            await session.flush()
            await session.refresh(merged)
            return merged

    async def delete(self, kid: int) -> bool:
        """物理删除；返回是否找到并删除。"""

        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(BusiSearchKeyword).where(BusiSearchKeyword.id == kid)
            )
            kw = result.scalar_one_or_none()
            if not kw:
                return False
            await session.delete(kw)
            return True

    async def platform_exists(self, platform_code: str) -> bool:
        """检查某 platform_code 是否对应一个启用平台（bs_status='1'）。"""

        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(platformSource).where(
                    platformSource.bs_platform_code == platform_code,
                    platformSource.bs_status == PlatformStatus.ENABLED,
                )
            )
            return result.scalar_one_or_none() is not None


class DatatypeRepo:
    """CRUD and sync operations on the t_sys_datatype table."""

    def __init__(self, db: SQLAlchemyDB):
        self.db = db

    async def find_all(self, is_active: bool | None = None) -> list[SysDatatype]:
        """查询已注册的数据类型列表。"""
        async with self.db.asession_scope() as session:
            stmt = select(SysDatatype).order_by(SysDatatype.datatype_id.asc())
            if is_active is not None:
                stmt = stmt.where(SysDatatype.is_active == is_active)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def find_by_key(self, datatype_key: str) -> SysDatatype | None:
        """根据 datatype_key 查询单个数据类型。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(SysDatatype).where(SysDatatype.datatype_key == datatype_key)
            )
            return result.scalar_one_or_none()

    async def update_status(self, datatype_key: str, is_active: bool) -> SysDatatype | None:
        """更新指定数据类型的启用状态，返回更新后的记录；不存在时返回 None。"""
        async with self.db.asession_scope() as session:
            result = await session.execute(
                select(SysDatatype).where(SysDatatype.datatype_key == datatype_key)
            )
            record = result.scalar_one_or_none()
            if not record:
                return None
            record.is_active = is_active
            await session.commit()
            await session.refresh(record)
            return record

    async def sync_from_code(self) -> tuple[int, list[str]]:
        """从 Python 代码内省结果同步落库至 t_sys_datatype。"""
        # 确保数据表已存在（自愈机制）
        impl = getattr(self.db, "_impl", None)
        if impl and hasattr(impl, "engine"):
            async with impl.engine.begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: SysDatatype.__table__.create(sync_conn, checkfirst=True)
                )

        introspected = introspect_datatype_models()
        keys: list[str] = []
        async with self.db.asession_scope() as session:
            for item in introspected:
                stmt = select(SysDatatype).where(SysDatatype.datatype_key == item["datatype_key"])
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()
                if existing:
                    existing.table_name = item["table_name"]
                    existing.model_name = item["model_name"]
                    existing.description = item["description"]
                    existing.unique_field = item["unique_field"]
                    existing.update_fields = item["update_fields"]
                    existing.columns = item["columns"]
                    existing.dto_fields = item["dto_fields"]
                    existing.is_active = item["is_active"]
                else:
                    record = SysDatatype(**item)
                    session.add(record)
                keys.append(item["datatype_key"])
            await session.commit()
        return len(keys), keys

