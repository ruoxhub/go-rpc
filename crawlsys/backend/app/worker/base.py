"""Worker 通用生命周期。"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar

from common.logging import get_logger
from common.errors import format_error
from common.constants import MIN_ZOMBIE_REAP_SECONDS
from core.repository import TaskRepo
from core.task_schedule import ScheduleRule, next_schedule_at, retry_delay
from models import BusTask, BusTaskLog, TaskStatus
from models.task import TaskRunStatus, TaskScheduleType
from models.task_config import ExecutorType
from runtime_config.models import SchedulerSettings
from .result import WorkerResult

logger = get_logger(__file__)


def _as_naive_utc(value: datetime) -> datetime:
    """DateTime 列存 naive；把 aware UTC 时间折叠为 naive UTC。"""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


_HEARTBEAT_CONFIG_REFRESH_SECONDS = 5.0
_RUNTIME_CONFIG_RETRY_SECONDS = 0.5


class BaseWorker(ABC):
    executor: ClassVar[ExecutorType]

    def __init__(self, platform: str, repo: TaskRepo, db: Any, quota: Any,
                 poll_interval: float = 1.0, default_loop_interval_seconds: int = 3600,
                 zombie_reap_after_seconds: int = 600,
                 heartbeat_interval_seconds: float | None = None,
                 config_store: Any = None):
        self.platform = platform
        self.repo = repo
        self.db = db
        self.quota = quota
        self.poll_interval = poll_interval
        self.default_loop_interval_seconds = default_loop_interval_seconds
        self.zombie_reap_after_seconds = zombie_reap_after_seconds
        self._heartbeat_interval_override = heartbeat_interval_seconds
        if (heartbeat_interval_seconds is not None
                and heartbeat_interval_seconds <= 0):
            raise ValueError("heartbeat_interval_seconds must be > 0")
        self.heartbeat_interval_seconds = (
            self._heartbeat_interval_override
            if heartbeat_interval_seconds is not None
            else max(0.1, zombie_reap_after_seconds / 3)
        )
        self.config_store = config_store
        self._running = True

    @property
    def task_platform_scope(self) -> str | None:
        return None

    async def run(self) -> None:
        logger.info(
            "Worker[%s] started, poll_interval=%.1fs, quota(rps=%.2f burst=%d conc=%d cd=%ds)",
            self.platform,
            self.poll_interval,
            self.quota.rps,
            getattr(self.quota, "burst", 1),
            self.quota.concurrency,
            self.quota.cooldown_on_block,
        )
        sem = asyncio.Semaphore(max(1, self.quota.concurrency))

        async def guarded(task: BusTask, settings: SchedulerSettings) -> None:
            async with sem:
                await self.execute(task, settings)

        while self._running:
            try:
                settings = await self._scheduler_settings()
            except Exception as exc:
                logger.warning("Worker[%s] runtime config read failed: %s", self.platform,
                               format_error(exc, max_length=500))
                await asyncio.sleep(_RUNTIME_CONFIG_RETRY_SECONDS)
                continue
            tasks = await self.repo.get_pending_tasks(
                platform=self.task_platform_scope,
                executor=self.executor,
                limit=min(settings.batch_size, max(1, self.quota.concurrency)),
            )
            if tasks:
                logger.info("Worker[%s] picked up %d pending task(s)", self.platform, len(tasks))
                await asyncio.gather(*(guarded(task, settings) for task in tasks if self._running))
                continue
            try:
                reclaimed = await self.repo.reclaim_stuck_running(
                    executor=self.executor,
                    platform=self.task_platform_scope,
                    older_than=datetime.now() - timedelta(seconds=settings.zombie_reap_after_seconds),
                )
                if reclaimed:
                    logger.info("Worker[%s] reclaimed %d stuck RUNNING task(s)", self.platform, reclaimed)
            except Exception as exc:
                logger.warning(
                    "Worker[%s] reclaim failed: %s",
                    self.platform,
                    format_error(exc, max_length=500),
                )
            await asyncio.sleep(settings.poll_interval_ms / 1000)

    async def _scheduler_settings(self) -> SchedulerSettings:
        if self.config_store is not None:
            return await self.config_store.get_scheduler()
        return SchedulerSettings(
            poll_interval_ms=round(self.poll_interval * 1000),
            default_loop_interval_seconds=self.default_loop_interval_seconds,
            zombie_reap_after_seconds=self.zombie_reap_after_seconds,
        )

    def stop(self) -> None:
        logger.info("Worker[%s] stop requested", self.platform)
        self._running = False

    async def execute(self, task: BusTask,
                      settings: SchedulerSettings | None = None) -> None:
        settings = settings or await self._scheduler_settings()
        started = time.monotonic()
        result = WorkerResult()
        succeeded = False
        cancelled = False
        log = self._create_log(task)
        task.status = TaskStatus.RUNNING
        await self.repo.save(task)
        heartbeat = asyncio.create_task(self._heartbeat(task, settings))
        try:
            result = await self.execute_business(task)
            finished_at = datetime.now(timezone.utc)
            if result.failed:
                self._mark_failure(
                    task,
                    now=finished_at,
                    error=(
                        f"Partial failure: succeeded={result.succeeded} "
                        f"failed={result.failed} total={result.total}"
                    ),
                    settings=settings,
                )
            else:
                self._finish_success(
                    task,
                    processed=result.succeeded,
                    now=finished_at,
                    settings=settings,
                )
                succeeded = True
            logger.info(
                "Worker[%s] task %s/%s round complete: task_id=%s "
                "priority=%s processed=%d failed=%d total=%d outcome=%s next_status=%s",
                self.platform,
                task.platform,
                task.action,
                task.task_id,
                task.priority,
                result.succeeded,
                result.failed,
                result.total,
                "success" if succeeded else "partial_failure",
                task.status,
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as exc:
            self._mark_failure(
                task,
                now=datetime.now(timezone.utc),
                error=format_error(exc, max_length=500),
                settings=settings,
            )
            logger.error(
                "Worker[%s] task %s/%s failed: task_id=%s priority=%s "
                "outcome=failed error=%s",
                self.platform,
                task.platform,
                task.action,
                task.task_id,
                task.priority,
                task.error_msg,
            )
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
            if not cancelled:
                try:
                    # 日志已复制本次触发快照；任务完成时清空，下一轮由领取重新写入。
                    task.active_trigger = None
                    task.active_scheduled_at = None
                    await self.repo.save(task)
                finally:
                    await self._finalize_log(log, task, started, result, succeeded)

    async def _heartbeat(
        self, task: BusTask, settings: SchedulerSettings
    ) -> None:
        last_heartbeat = time.monotonic()
        while True:
            interval = min(
                settings.zombie_reap_after_seconds / 3,
                MIN_ZOMBIE_REAP_SECONDS / 3,
            )
            if self._heartbeat_interval_override is not None:
                interval = min(interval, self._heartbeat_interval_override)
            elapsed = time.monotonic() - last_heartbeat
            if elapsed >= interval:
                try:
                    await self.repo.heartbeat_running(
                        task.task_id,
                        executor=self.executor,
                        platform=self.task_platform_scope,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Worker[%s] task heartbeat failed: %s",
                        self.platform,
                        format_error(exc, max_length=500),
                    )
                last_heartbeat = time.monotonic()
                continue
            await asyncio.sleep(min(
                interval - elapsed, _HEARTBEAT_CONFIG_REFRESH_SECONDS
            ))
            if self.config_store is None:
                continue
            try:
                settings = await self._scheduler_settings()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Worker[%s] heartbeat config read failed: %s",
                    self.platform,
                    format_error(exc, max_length=500),
                )
                remaining = interval - (time.monotonic() - last_heartbeat)
                if remaining > 0:
                    await asyncio.sleep(min(_RUNTIME_CONFIG_RETRY_SECONDS, remaining))

    @abstractmethod
    async def execute_business(self, task: BusTask) -> WorkerResult:
        """执行一个任务的业务部分。"""

    def _finish_success(self, task: BusTask, *, processed: int,
                        now: datetime,
                        settings: SchedulerSettings | None = None) -> None:
        """逻辑轮次成功收尾：记录次数与结果，再按调度模式安排下一轮。"""
        task.attempts = processed
        task.last_run_status = TaskRunStatus.SUCCESS.value
        task.run_count += 1
        task.retry_count = 0
        task.next_retry_at = None
        task.error_msg = None
        self._finish_logical_run(task, now=now, settings=settings, failed=False)

    def _schedule_retry(self, task: BusTask, *, now: datetime, error: str) -> bool:
        """指数退避调度下一次物理尝试；达到上限返回 False。"""
        if task.retry_count >= task.retry_max_attempts:
            return False
        task.retry_count += 1
        task.next_retry_at = _as_naive_utc(
            now
            + retry_delay(
                attempt=task.retry_count,
                initial_seconds=task.retry_delay_seconds,
                multiplier=task.retry_backoff_multiplier,
                max_seconds=task.retry_max_delay_seconds,
            )
        )
        task.status = TaskStatus.PENDING.value
        task.error_msg = error
        return True

    def _mark_failure(self, task: BusTask, *, now: datetime, error: str,
                      settings: SchedulerSettings | None = None) -> None:
        """物理尝试失败：有重试额度则调度重试；否则结束本轮逻辑轮次。"""
        task.error_msg = error
        if self._schedule_retry(task, now=now, error=error):
            return
        task.last_run_status = TaskRunStatus.FAILED.value
        task.run_count += 1
        task.retry_count = 0
        self._finish_logical_run(task, now=now, settings=settings, failed=True)

    def _finish_logical_run(self, task: BusTask, *, now: datetime,
                            settings: SchedulerSettings | None = None,
                            failed: bool = False) -> None:
        """收敛到逻辑轮次终点：决定 DONE/FAILED/PAUSED/PENDING 与下一轮时间。

        - manual/once：成功 DONE，最终失败 FAILED，不再调度。
        - interval/cron：本轮结束后继续后续计划；支持次数上限、
          pause-after-run 与运行期间触发合并（只合并一次）。
        """
        settings = settings or SchedulerSettings()
        # last_run_at / next_run_at / updated_at 存储为 naive UTC（与 DateTime 列一致）
        task.last_run_at = _as_naive_utc(now)
        schedule_type = task.schedule_type or TaskScheduleType.MANUAL.value
        periodic = schedule_type in (
            TaskScheduleType.INTERVAL.value,
            TaskScheduleType.CRON.value,
        )

        if task.pause_requested:
            task.pause_requested = False
            task.status = TaskStatus.PAUSED.value
            task.next_run_at = None
            task.run_now_requested_at = None
            return

        if task.max_runs is not None and task.run_count >= task.max_runs:
            task.status = TaskStatus.DONE.value
            task.next_run_at = None
            return

        # 运行期间已有立即执行请求 → 合并为一次，立即重新执行
        if task.run_now_requested_at is not None:
            task.status = TaskStatus.PENDING.value
            task.next_run_at = None
            return

        if not periodic:
            task.status = (
                TaskStatus.FAILED.value if failed else TaskStatus.DONE.value
            )
            task.next_run_at = None
            return

        if schedule_type == TaskScheduleType.INTERVAL.value:
            interval = (
                task.loop_interval_seconds
                if task.loop_interval_seconds and task.loop_interval_seconds > 0
                else settings.default_loop_interval_seconds
            )
            next_run = now + timedelta(seconds=interval)
        else:
            rule = ScheduleRule(
                type="cron",
                cron_expression=task.cron_expression,
                start_at=task.schedule_start_at,
                end_at=task.schedule_end_at,
            )
            base = task.active_scheduled_at or task.last_run_at or now
            if base.tzinfo is None:  # DB naive 值按 UTC 解释
                base = base.replace(tzinfo=timezone.utc)
            due_while_running = next_schedule_at(
                rule, now=base, timezone_name=settings.timezone
            )
            if due_while_running is not None and due_while_running <= now:
                # 运行期间错过至少一个触发点 → 合并为一次立即执行
                task.run_now_requested_at = now
                task.status = TaskStatus.PENDING.value
                task.next_run_at = None
                return
            next_run = next_schedule_at(
                rule, now=now, timezone_name=settings.timezone
            )

        task.next_run_at = _as_naive_utc(next_run) if next_run is not None else None
        task.status = TaskStatus.PENDING.value

    def _create_log(self, task: BusTask) -> BusTaskLog:
        return BusTaskLog(
            btl_taskid=task.task_id,
            btl_platformid=task.platform_id,
            btl_start_time=datetime.now(),
            btl_request_rate=int(self.quota.rps),
            btl_active_trigger=task.active_trigger,
            btl_active_scheduled_at=task.active_scheduled_at,
            btl_retry_count=task.retry_count,
        )

    async def _finalize_log(self, log: BusTaskLog, task: BusTask, started: float,
                            result: WorkerResult, succeeded: bool) -> None:
        log.btl_end_time = datetime.now()
        log.btl_consume_time = int((time.monotonic() - started) * 1000)
        log.btl_all_item_num = result.total
        log.btl_item_num = result.succeeded
        log.btl_collect_num = result.succeeded
        log.btl_err_num = result.failed
        log.btl_status = 1 if succeeded else -1
        log.btl_err_msg = task.error_msg
        try:
            await self.db.aadd(log)
        except Exception as exc:
            logger.warning(
                "Worker[%s] failed to write BusTaskLog: %s",
                self.platform,
                format_error(exc, max_length=500),
            )
