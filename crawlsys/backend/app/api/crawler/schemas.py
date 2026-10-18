"""Crawler JSON API request and response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.task import TaskPriority, TaskScheduleType, TaskStatus
from models.task_config import (
    ExecutorType,
    TaskConfig,
    VideoDownloadTaskConfig,
    WorkItemSinkConfig,
    WorkItemSourceConfig,
)


class CrawlerSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CrawlerReadSchema(CrawlerSchema):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        populate_by_name=True,
    )


class PlatformFields(CrawlerSchema):
    bs_name: str = Field(min_length=1, max_length=100)
    bs_platform_code: str = Field(min_length=1, max_length=100)
    bs_url: str | None = Field(default=None, max_length=2048)
    bs_remark: str | None = None
    bs_status: str = Field(default="1", pattern=r"^[01D]$")
    bs_concurrency: int = Field(default=1, ge=1)
    bs_rps: float = Field(default=1.0, ge=0.1)
    bs_burst: int = Field(default=3, ge=1)
    bs_cooldown: int = Field(default=300, ge=0)

    @field_validator("bs_name", "bs_platform_code", mode="before")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("bs_url", "bs_remark")
    @classmethod
    def empty_optional_strings_are_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class PlatformCreate(PlatformFields):
    pass


class PlatformUpdate(PlatformFields):
    pass


class PlatformRead(CrawlerReadSchema):
    bs_id: int
    bs_name: str | None = None
    bs_platform_code: str | None = None
    bs_url: str | None = None
    bs_remark: str | None = None
    bs_status: str | None = None
    bs_concurrency: int | None = None
    bs_rps: float | None = None
    bs_burst: int | None = None
    bs_cooldown: int | None = None


class PlatformList(CrawlerSchema):
    items: list[PlatformRead]


class ActionFields(CrawlerSchema):
    bs_id: int = Field(gt=0)
    ba_action: str = Field(min_length=1, max_length=100)
    ba_desc: str | None = None
    ba_params_schema: str | None = None
    ba_api_url: str | None = Field(default=None, max_length=500)
    ba_api_method: str | None = Field(default="GET", max_length=10)
    ba_enabled: bool = True
    ba_sample_safe: bool = False
    ba_schema_source: str | None = Field(default="synced", max_length=16)
    ba_synced_at: datetime | None = None

    @field_validator("ba_action", mode="before")
    @classmethod
    def strip_action_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("ba_desc", "ba_params_schema", "ba_api_url", "ba_api_method")
    @classmethod
    def empty_optional_strings_are_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ActionCreate(ActionFields):
    pass


class ActionUpdate(CrawlerSchema):
    ba_action: str | None = Field(default=None, min_length=1, max_length=100)
    ba_desc: str | None = None
    ba_params_schema: str | None = None
    ba_api_url: str | None = Field(default=None, max_length=500)
    ba_api_method: str | None = Field(default=None, max_length=10)
    ba_enabled: bool | None = None
    ba_sample_safe: bool | None = None
    ba_schema_source: str | None = Field(default=None, max_length=16)
    ba_synced_at: datetime | None = None

    @field_validator("ba_action", mode="before")
    @classmethod
    def strip_action_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("不能为空")
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("ba_desc", "ba_params_schema", "ba_api_url", "ba_api_method")
    @classmethod
    def empty_optional_strings_are_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ActionRead(CrawlerReadSchema):
    ba_id: int
    bs_id: int
    ba_action: str
    ba_desc: str | None = None
    ba_params_schema: str | None = None
    ba_api_url: str | None = None
    ba_api_method: str | None = None
    ba_enabled: bool
    ba_sample_safe: bool = False
    ba_schema_source: str | None = None
    ba_synced_at: datetime | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class ActionList(CrawlerSchema):
    items: list[ActionRead]


class ActionImportItem(CrawlerSchema):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    params: list[Any] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class ActionImportRequest(CrawlerSchema):
    platform_id: int = Field(gt=0)
    actions: list[ActionImportItem]


class ActionImportResponse(CrawlerSchema):
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)


class ActionBatchStatusRequest(CrawlerSchema):
    action_ids: list[int] = Field(min_length=1)
    enabled: bool


class ActionBatchStatusResponse(CrawlerSchema):
    updated_count: int = Field(ge=0)


class ActionBatchDeleteRequest(CrawlerSchema):
    action_ids: list[int] = Field(min_length=1)


class ActionBatchDeleteResponse(CrawlerSchema):
    deleted_count: int = Field(ge=0)


class ActionSyncItemDetail(CrawlerSchema):
    platform: str
    action: str
    status: str
    reason: str | None = None


class ActionSyncRequest(CrawlerSchema):
    platform_id: int | None = Field(default=None, gt=0, description="平台 ID，空则同步所有平台")
    force: bool = Field(default=False, description="是否强制覆盖 manual 人工配置的 schema")


class ActionSyncResponse(CrawlerSchema):
    inserted_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    skipped_manual_count: int = Field(ge=0)
    total_synced: int = Field(ge=0)
    unknown_groups: list[str] = Field(default_factory=list)
    details: list[ActionSyncItemDetail] = Field(default_factory=list)


class KeywordFields(CrawlerSchema):
    platform: str = Field(min_length=1, max_length=100)
    keyword: str = Field(min_length=1, max_length=1000)

    @field_validator("platform", "keyword", mode="before")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class KeywordCreate(KeywordFields):
    pass


class KeywordUpdate(KeywordFields):
    pass


class KeywordRead(CrawlerReadSchema):
    id: int
    platform: str
    keyword: str
    is_crawled: bool
    created_at: datetime


class KeywordList(CrawlerSchema):
    items: list[KeywordRead]


class TaskSchedule(CrawlerSchema):
    """结构化调度配置；type 之外的模式字段互斥。"""

    type: Literal["manual", "once", "interval", "cron"] = "manual"
    cron: str | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = Field(default=None, gt=0)
    start_at: datetime | None = None
    end_at: datetime | None = None
    max_runs: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_schedule_mode(self) -> Self:
        if self.type == "cron" and not self.cron:
            raise ValueError("cron 模式必须提供 cron 表达式")
        if self.type == "once" and self.run_at is None:
            raise ValueError("once 模式必须提供 run_at")
        if self.type == "interval" and self.interval_seconds is None:
            raise ValueError("interval 模式必须提供 interval_seconds")
        if self.type != "cron" and self.cron is not None:
            raise ValueError("只有 cron 模式可以设置 cron 表达式")
        if self.type != "interval" and self.interval_seconds is not None:
            raise ValueError("只有 interval 模式可以设置 interval_seconds")
        if (
            self.type != "once"
            and self.run_at is not None
        ):
            raise ValueError("只有 once 模式可以设置 run_at")
        if self.start_at is not None and self.end_at is not None and self.start_at > self.end_at:
            raise ValueError("start_at 不能晚于 end_at")
        return self


class TaskRetryPolicy(CrawlerSchema):
    max_attempts: int = Field(default=0, ge=0)
    initial_delay_seconds: int = Field(default=60, gt=0)
    backoff_multiplier: float = Field(default=2, ge=1)
    max_delay_seconds: int = Field(default=3600, gt=0)


class TaskScheduleInfo(CrawlerSchema):
    """响应侧调度快照：不做跨字段严格校验，容忍旧数据。"""

    type: TaskScheduleType
    cron: str | None = None
    run_at: datetime | None = None
    interval_seconds: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    max_runs: int | None = None


class SchedulePreviewRequest(CrawlerSchema):
    cron: str

    @field_validator("cron")
    @classmethod
    def validate_cron_expression(cls, value: str) -> str:
        if len(value.split()) != 5:
            raise ValueError("Cron 表达式必须包含 5 段")
        return value


class SchedulePreviewResponse(CrawlerSchema):
    timezone: str
    occurrences: list[datetime]

class TaskFields(CrawlerSchema):
    ba_id: int = Field(gt=0)
    priority: TaskPriority = TaskPriority.NORMAL
    execution_mode: Literal["invoke_action", "publish_source"] = "invoke_action"
    source: WorkItemSourceConfig | None = None
    sink: WorkItemSinkConfig | None = None
    ref_table: str = ""
    ref_where: str = ""
    params_columns: str = ""
    entity_column: str = ""
    result_column: str = ""
    post_update_column: str = ""
    post_update_table: str = ""
    sink_mode: str = Field(default="auto", pattern=r"^(standard|direct|none|auto)$")
    loop_enabled: bool = False
    loop_interval_seconds: int | None = None
    schedule: TaskSchedule = Field(default_factory=TaskSchedule)
    retry_policy: TaskRetryPolicy = Field(default_factory=TaskRetryPolicy)
    executor: ExecutorType = "rpc_crawl"
    download: VideoDownloadTaskConfig | None = None
    llm_model_id: int | None = Field(default=None, gt=0)
    review_route: Literal["R", "G"] | None = None

    @field_validator(
        "ref_table",
        "ref_where",
        "params_columns",
        "entity_column",
        "result_column",
        "post_update_column",
        "post_update_table",
    )
    @classmethod
    def strip_task_strings(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_task_settings(self) -> Self:
        legacy_source_set = any(
            (self.ref_table, self.ref_where, self.params_columns, self.entity_column)
        )
        legacy_sink_set = any(
            (
                self.result_column,
                self.post_update_column,
                self.post_update_table,
                "sink_mode" in self.model_fields_set,
            )
        )
        if "source" in self.model_fields_set and legacy_source_set:
            raise ValueError("source 不能与旧数据源字段同时提交")
        if "sink" in self.model_fields_set and legacy_sink_set:
            raise ValueError("sink 不能与旧结果字段同时提交")
        source_fields = (
            self.ref_table,
            self.ref_where,
            self.params_columns,
            self.entity_column,
        )
        if any(source_fields) and (not self.ref_table or not self.entity_column):
            raise ValueError("配置数据源时必须同时填写查询表和主键列")
        if not self.loop_enabled:
            self.loop_interval_seconds = None
        elif self.loop_interval_seconds is not None and self.loop_interval_seconds <= 0:
            raise ValueError("循环间隔必须大于 0")
        if (
            self.llm_model_id is not None
            and "executor" in self.model_fields_set
            and self.executor != "video_analysis"
        ):
            raise ValueError("只有视频分析任务可以指定模型")
        return self


class TaskCreate(TaskFields):
    pass


class TaskUpdate(TaskFields):
    pass


class TaskPriorityUpdate(CrawlerSchema):
    priority: TaskPriority


class TaskRead(CrawlerReadSchema):
    task_id: int
    priority: TaskPriority = TaskPriority.NORMAL
    platform: str
    action: str
    ba_id: int | None = None
    platform_id: int | None = None
    status: TaskStatus
    attempts: int
    error_msg: str | None = None
    last_run_at: datetime | None = None
    loop_enabled: bool
    loop_interval_seconds: int | None = None
    schedule_type: TaskScheduleType
    cron_expression: str | None = None
    run_once_at: datetime | None = None
    schedule_start_at: datetime | None = None
    schedule_end_at: datetime | None = None
    max_runs: int | None = None
    run_count: int
    last_run_status: str | None = None
    retry_max_attempts: int
    retry_delay_seconds: int
    retry_backoff_multiplier: float
    retry_max_delay_seconds: int
    retry_count: int
    next_retry_at: datetime | None = None
    run_now_requested_at: datetime | None = None
    pause_requested: bool
    active_trigger: str | None = None
    active_scheduled_at: datetime | None = None
    next_run_at: datetime | None = None
    schedule: TaskScheduleInfo | None = None
    retry_policy: TaskRetryPolicy | None = None
    config: TaskConfig | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("priority", mode="before")
    @classmethod
    def priority_from_db(cls, value: object) -> TaskPriority:
        # TODO(user): 实现多种数据源（ORM integer、枚举实例、字符串、或缺失/None）到 TaskPriority 的安全转换策略
        if value is None:
            return TaskPriority.NORMAL
        if isinstance(value, TaskPriority):
            return value
        if isinstance(value, str):
            try:
                return TaskPriority(value)
            except ValueError:
                pass
        return TaskPriority.from_db_value(value)


class TaskList(CrawlerSchema):
    items: list[TaskRead]


class TaskBatchStatusRequest(CrawlerSchema):
    platform: str | None = Field(default=None, max_length=100)

    @field_validator("platform")
    @classmethod
    def strip_platform(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None



class TaskBatchStatusResponse(CrawlerSchema):
    updated_count: int = Field(ge=0)


class TableColumnsResponse(CrawlerSchema):
    columns: list[str]


class DatatypeRowColumnRead(CrawlerSchema):
    """数据记录编辑器使用的单列元数据。"""

    name: str
    sql_type: str
    value_type: str
    nullable: bool
    primary_key: bool
    comment: str | None = None
    max_length: int | None = None
    editable: bool
    required: bool


class DatatypeRowsMetaResponse(CrawlerSchema):
    datatype_key: str
    table_name: str
    model_name: str
    description: str | None = None
    unique_field: str | None = None
    pk_columns: list[str]
    columns: list[DatatypeRowColumnRead]


class DatatypeRowFilter(CrawlerSchema):
    field: str = Field(min_length=1, max_length=64)
    operator: Literal[
        "eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_null"
    ] = "eq"
    value: Any = None


class DatatypeRowCreate(CrawlerSchema):
    values: dict[str, Any] = Field(default_factory=dict)


class DatatypeRowUpdate(CrawlerSchema):
    values: dict[str, Any] = Field(default_factory=dict)


class DatatypeRowPageResponse(CrawlerSchema):
    items: list[dict[str, Any]]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class DatatypeRowResponse(CrawlerSchema):
    item: dict[str, Any]


class DatatypeRowDeleteResponse(CrawlerSchema):
    deleted: bool = True


class DatatypeRowErrorResponse(CrawlerSchema):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ActionSchemaResponse(CrawlerSchema):
    action_schema: dict[str, Any] | list[Any] | bool = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )


class LlmModelOption(CrawlerSchema):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    display_name: str
    litellm_model: str


class LlmModelMetadataResponse(CrawlerSchema):
    llm_models: list[LlmModelOption]
