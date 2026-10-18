"""Scheduler task model — one row per (platform, action) pair."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from models.base import Base
from models.task_config import TaskConfig, TaskConfigType


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in {TaskStatus.DONE, TaskStatus.FAILED}


class TaskPriority(str, Enum):
    LOWEST = "lowest"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def db_value(self) -> int:
        return _PRIORITY_DB_VALUE[self]

    @classmethod
    def from_db_value(cls, value: object) -> TaskPriority:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("priority must be an integer from 0 to 4")
        try:
            return _DB_VALUE_TO_PRIORITY[value]
        except KeyError as exc:
            raise ValueError("priority must be an integer from 0 to 4") from exc


_PRIORITY_DB_VALUE = {
    TaskPriority.LOWEST: 0,
    TaskPriority.LOW: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.HIGH: 3,
    TaskPriority.URGENT: 4,
}
_DB_VALUE_TO_PRIORITY = {
    value: priority for priority, value in _PRIORITY_DB_VALUE.items()
}


class TaskScheduleType(str, Enum):
    """任务调度模式；新调度判断只使用 schedule_type。"""

    MANUAL = "manual"
    ONCE = "once"
    INTERVAL = "interval"
    CRON = "cron"


class TaskRunStatus(str, Enum):
    """上一逻辑轮次的成功/失败结果，与可调度 status 分离。"""

    SUCCESS = "success"
    FAILED = "failed"


class TaskTrigger(str, Enum):
    """本次物理尝试的触发来源。"""

    SCHEDULED = "scheduled"
    RETRY = "retry"
    MANUAL = "manual"
    COALESCED = "coalesced"


class InvalidTaskTransitionError(ValueError):
    """Raised when a task is moved through an unsupported lifecycle transition."""


_ALLOWED_TASK_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.PAUSED},
    TaskStatus.RUNNING: {
        TaskStatus.PENDING,
        TaskStatus.PAUSED,
        TaskStatus.DONE,
        TaskStatus.FAILED,
    },
    TaskStatus.PAUSED: {TaskStatus.PENDING},
    TaskStatus.DONE: {TaskStatus.PENDING},
    TaskStatus.FAILED: {TaskStatus.PENDING},
}


class BusTaskLog(Base):
    """任务日志模型 - 基于 t_busi_task_logs 表生成

    字段说明：
    - btl_status: 异常状态，1 正常，-1 异常
    - btl_request_rate: 请求频率
    - btl_runtime_efficiency: 执行效率
    """

    __tablename__ = 't_busi_task_logs'
    __table_args__ = (
        Index('idx_bus_task_log_taskid', 'btl_taskid'),
        Index('idx_bus_task_log_start_time', 'btl_start_time'),
        CheckConstraint(
            "btl_active_trigger IS NULL OR btl_active_trigger IN ('scheduled', 'retry', 'manual', 'coalesced')",
            name="ck_task_log_active_trigger",
        ),
        CheckConstraint("btl_retry_count >= 0", name="ck_task_log_retry_count_non_negative"),
        {'schema': 'public'}
    )

    # 主键
    btl_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment='pk')

    # 关联字段
    btl_taskid: Mapped[int] = mapped_column(Integer, nullable=False, comment='任务 id')
    btl_platformid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment='站点 id')
    btl_node_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment='节点 id')

    # 时间字段
    btl_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='任务执行时间')
    btl_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='结束时间')

    # 统计字段
    btl_item_num: Mapped[int] = mapped_column(Integer, default=0, comment='识别数量')
    btl_consume_time: Mapped[int] = mapped_column("btl_consue_time", Integer, default=0, comment='耗时（毫秒）')
    btl_pageturn_num: Mapped[int] = mapped_column(Integer, default=0, comment='翻页数量')
    btl_collect_num: Mapped[int] = mapped_column(Integer, default=0, comment='采集数量')
    btl_runtime_efficiency: Mapped[int] = mapped_column(Integer, default=0, comment='执行效率')
    btl_err_num: Mapped[int] = mapped_column(Integer, default=0, comment='异常数量')
    btl_all_item_num: Mapped[int] = mapped_column(Integer, default=0, comment='所有数量')
    btl_request_rate: Mapped[int] = mapped_column(Integer, default=5, comment='请求频率')

    # 状态字段
    btl_status: Mapped[int] = mapped_column(Integer, default=0, comment='异常状态，1 正常，-1 异常')

    # 标识字段
    btl_uuid: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, comment='页面唯一 id')

    # 日志信息
    btl_err_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='异常信息')
    btl_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='日志信息')

    # 调度可观测字段
    btl_active_trigger: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment='触发来源')
    btl_active_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment='原计划时间'
    )
    btl_retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment='当前重试次数')



class BusTask(Base):
    __tablename__ = "t_crawl_task"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("public.t_busi_platform.bs_platform_code"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    ba_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("public.t_busi_action.ba_id"),
        nullable=True,
        comment="关联接口定义, NULL=未关联",
    )
    platform_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("public.t_busi_platform.bs_id"),
        nullable=True,
        comment="平台主键 id，供日志关联使用",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskStatus.PENDING, server_default="pending",
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=TaskPriority.NORMAL.db_value,
        server_default="2",
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    loop_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    loop_interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- 定时调度字段（新调度判断只使用 schedule_type 与以下字段）---
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskScheduleType.MANUAL, server_default="manual",
    )
    cron_expression: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    run_once_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    max_runs: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_run_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # --- 指数退避重试 ---
    retry_max_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, default=60, server_default="60")
    retry_backoff_multiplier: Mapped[float] = mapped_column(Float, default=2.0, server_default="2")
    retry_max_delay_seconds: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # --- 手动/合并触发与暂停 ---
    run_now_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # --- 本次物理尝试的触发快照 ---
    active_trigger: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    active_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 任务完整定义 (数据源 + 结果写回); Pydantic typed 访问
    config: Mapped[Optional[TaskConfig]] = mapped_column(
        TaskConfigType(), nullable=True, comment="任务配置 JSON"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, server_default="now()",
    )

    __table_args__ = (
        UniqueConstraint("platform", "action", name="uq_task_platform_action"),
        CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'done', 'failed')",
            name="ck_task_status",
        ),
        CheckConstraint(
            "priority BETWEEN 0 AND 4",
            name="ck_task_priority_range",
        ),
        CheckConstraint("attempts >= 0", name="ck_task_attempts_non_negative"),
        CheckConstraint(
            "schedule_type IN ('manual', 'once', 'interval', 'cron')",
            name="ck_task_schedule_type",
        ),
        CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN ('success', 'failed')",
            name="ck_task_last_run_status",
        ),
        CheckConstraint(
            "active_trigger IS NULL OR active_trigger IN ('scheduled', 'retry', 'manual', 'coalesced')",
            name="ck_task_active_trigger",
        ),
        CheckConstraint("run_count >= 0", name="ck_task_run_count_non_negative"),
        CheckConstraint("retry_count >= 0", name="ck_task_retry_count_non_negative"),
        CheckConstraint("retry_max_attempts >= 0", name="ck_task_retry_max_attempts_non_negative"),
        CheckConstraint("retry_backoff_multiplier >= 1", name="ck_task_retry_backoff_multiplier_ge_1"),
        Index("idx_task_ready", "status", "next_run_at"),
        Index("idx_task_due", "status", "next_retry_at", "next_run_at"),
        Index("idx_task_platform_status", "platform", "status"),
        Index("idx_task_action_id", "ba_id"),
        {"schema": "public"},
    )

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("status", TaskStatus.PENDING.value)
        kwargs.setdefault("priority", TaskPriority.NORMAL.db_value)
        kwargs.setdefault("attempts", 0)
        kwargs.setdefault("loop_enabled", False)
        kwargs.setdefault("schedule_type", TaskScheduleType.MANUAL.value)
        kwargs.setdefault("run_count", 0)
        kwargs.setdefault("retry_count", 0)
        kwargs.setdefault("retry_max_attempts", 0)
        kwargs.setdefault("retry_delay_seconds", 60)
        kwargs.setdefault("retry_backoff_multiplier", 2.0)
        kwargs.setdefault("retry_max_delay_seconds", 3600)
        kwargs.setdefault("pause_requested", False)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<BusTask {self.platform}/{self.action} [{self.status}]>"

    @validates("platform", "action")
    def _normalize_identity(self, key: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{key} 不能为空")
        return normalized

    @validates("status")
    def _normalize_status(self, _key: str, value: str | TaskStatus) -> str:
        try:
            return TaskStatus(value).value
        except ValueError as exc:
            raise ValueError(f"未知任务状态: {value}") from exc

    @validates("attempts")
    def _validate_attempts(self, _key: str, value: int) -> int:
        if value < 0:
            raise ValueError("attempts 不能小于 0")
        return value

    @validates("priority")
    def validate_priority(self, _key: str, value: int | TaskPriority) -> int:
        if isinstance(value, TaskPriority):
            return value.db_value
        return TaskPriority.from_db_value(value).db_value

    @validates("schedule_type")
    def _normalize_schedule_type(self, _key: str, value: str | TaskScheduleType) -> str:
        try:
            return TaskScheduleType(value).value
        except ValueError as exc:
            raise ValueError(f"未知调度类型: {value}") from exc

    @validates("last_run_status")
    def _normalize_last_run_status(self, _key: str, value: str | TaskRunStatus | None) -> str | None:
        if value is None:
            return value
        try:
            return TaskRunStatus(value).value
        except ValueError as exc:
            raise ValueError(f"未知运行状态: {value}") from exc

    @validates("active_trigger")
    def _normalize_active_trigger(self, _key: str, value: str | TaskTrigger | None) -> str | None:
        if value is None:
            return value
        try:
            return TaskTrigger(value).value
        except ValueError as exc:
            raise ValueError(f"未知触发来源: {value}") from exc

    @validates("run_count", "retry_count", "retry_max_attempts")
    def _validate_non_negative_count(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError(f"{key} 不能小于 0")
        return value

    @validates("retry_backoff_multiplier")
    def _validate_backoff_multiplier(self, _key: str, value: float) -> float:
        if value < 1:
            raise ValueError("retry_backoff_multiplier 不能小于 1")
        return value

    @property
    def status_value(self) -> TaskStatus:
        return TaskStatus(self.status)

    def is_ready(self, *, at: datetime | None = None) -> bool:
        """Return whether the scheduler may claim this task at the given time."""
        if self.status_value is not TaskStatus.PENDING:
            return False
        return self.next_run_at is None or self.next_run_at <= (at or datetime.now())

    def can_transition_to(self, target: str | TaskStatus) -> bool:
        target_status = TaskStatus(target)
        current_status = self.status_value
        return target_status is current_status or target_status in _ALLOWED_TASK_TRANSITIONS[current_status]

    def transition_to(
        self,
        target: str | TaskStatus,
        *,
        at: datetime | None = None,
        error_msg: str | None = None,
    ) -> None:
        """Apply a validated lifecycle transition and its shared field semantics."""
        target_status = TaskStatus(target)
        current_status = self.status_value
        if not self.can_transition_to(target_status):
            raise InvalidTaskTransitionError(
                f"不允许任务从 {current_status.value} 转换为 {target_status.value}"
            )

        self.status = target_status.value
        if target_status is TaskStatus.RUNNING:
            self.last_run_at = at or datetime.now()
            self.error_msg = None
        elif target_status is TaskStatus.PENDING:
            self.error_msg = None
        elif target_status is TaskStatus.FAILED:
            self.error_msg = error_msg
