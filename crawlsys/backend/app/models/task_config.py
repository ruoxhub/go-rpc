# models/task_config.py
"""Worker task config schema — typed access for BusTask.config JSON."""
from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator

ExecutorType = Literal["rpc_crawl", "video_clean", "video_download", "video_analysis"]
REDIS_STREAM_NAME_PATTERN = re.compile(r"^[^{}]*\{([^{}]+)\}[^{}]*$")


def validate_redis_stream_name(value: str) -> str:
    """校验 Redis Stream 名称恰好包含一个非空 hash tag。"""
    if REDIS_STREAM_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError("Redis Stream name must contain exactly one nonempty hash tag")
    return value


def _redis_hash_tag(value: str) -> str:
    match = REDIS_STREAM_NAME_PATTERN.fullmatch(value)
    assert match is not None
    return match.group(1)


class PaginationConfig(BaseModel):
    """分页执行配置。"""
    cursor_param: str = "cursor"
    initial_cursor: int = 0
    max_pages: int = Field(default=0, ge=0)
    response_cursor_keys: list[str] = Field(
        default_factory=lambda: ["nextCursor", "next_cursor", "maxCursor", "cursor"]
    )


class VideoCleanTaskConfig(BaseModel):
    """视频清洗执行器配置。"""
    platforms: list[str] = Field(default_factory=list)
    batch_size: Optional[int] = Field(default=None, ge=1)


class VideoDownloadTaskConfig(BaseModel):
    """视频下载执行器配置。"""
    batch_size: int = Field(default=50, ge=1, le=500)
    min_grade: int = Field(default=3, ge=1, le=3)
    use_proxy: bool = True
    rps: float = Field(default=0, ge=0)
    max_attempts: int = Field(default=5, ge=1, le=20)
    claim_timeout_seconds: int = Field(default=1800, ge=60, le=86400)
    retry_base_seconds: int = Field(default=60, ge=1, le=86400)
    retry_max_seconds: int = Field(default=3600, ge=1, le=604800)

    @model_validator(mode="after")
    def validate_retry_window(self) -> Self:
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be >= retry_base_seconds")
        return self


class VideoAnalysisTaskConfig(BaseModel):
    """视频分析执行器配置。"""
    batch_size: int = Field(default=10, ge=1, le=100)
    max_attempts: int = Field(default=3, ge=1)
    llm_model_id: Optional[int] = Field(default=None, gt=0)
    review_route: Literal["R", "G"] | None = None


class DatabaseSourceCompletionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1)
    value: bool = True


class DatabaseSourceConfig(BaseModel):
    """数据源配置: 如何从业务表找到待抓实体。"""
    type: Literal["database"] = "database"
    table: str
    where: Optional[str] = None
    key_column: str
    param_map: dict[str, str] = Field(default_factory=dict)
    extra_columns: list[str] = Field(default_factory=list)
    # 是否自动追加 `WHERE platform = :platform` 过滤。
    # 多平台业务表（如 t_busi_search_keyword）需置 True；
    # 平台专属表（如 tk_challenge，表内数据天然只属于该平台且无 platform 列）置 False。
    filter_by_platform: bool = True
    # 可选排序：每项 "column" 或 "column ASC|DESC"；Worker 侧再做标识符校验。
    order_by: list[str] = Field(default_factory=list)
    # 每轮拉取上限；默认 50，与历史硬编码 LIMIT 50 对齐。
    limit: int = Field(default=50, ge=1, le=500)
    completion: DatabaseSourceCompletionConfig | None = None


SourceConfig = DatabaseSourceConfig


class RedisStreamSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["redis_stream"] = "redis_stream"
    stream: str
    group: str
    batch_size: int = Field(default=50, ge=1, le=500)
    block_ms: int = Field(default=1000, ge=0, le=5000)
    claim_idle_ms: int = Field(default=60000, ge=1000, le=86_400_000)
    max_deliveries: int = Field(default=5, ge=1, le=100)
    dead_letter_stream: str

    @field_validator("stream", "dead_letter_stream")
    @classmethod
    def validate_stream_name(cls, value: str) -> str:
        return validate_redis_stream_name(value)

    @model_validator(mode="after")
    def validate_dead_letter_hash_tag(self):
        if _redis_hash_tag(self.stream) != _redis_hash_tag(self.dead_letter_stream):
            raise ValueError("source and dead-letter streams must share the same hash tag")
        return self


class DatabaseSinkConfig(BaseModel):
    """结果写回配置: 跑完后怎么处理结果。"""
    type: Literal["database"] = "database"
    mode: Literal["standard", "direct", "none", "auto"] = "auto"
    result_column: Optional[str] = None
    mark_done_column: Optional[str] = None
    mark_done_table: Optional[str] = None


SinkConfig = DatabaseSinkConfig


class RedisStreamSinkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["redis_stream"] = "redis_stream"
    stream: str
    param_map: dict[str, str] = Field(min_length=1)
    dedupe_ttl_seconds: int = Field(default=86400, ge=1, le=31_536_000)

    @field_validator("stream")
    @classmethod
    def validate_stream_name(cls, value: str) -> str:
        return validate_redis_stream_name(value)


WorkItemSourceConfig = Annotated[
    DatabaseSourceConfig | RedisStreamSourceConfig,
    Field(discriminator="type"),
]
WorkItemSinkConfig = Annotated[
    DatabaseSinkConfig | RedisStreamSinkConfig,
    Field(discriminator="type"),
]


class TaskConfig(BaseModel):
    """BusTask.config JSON 的 typed 形态。"""
    executor: ExecutorType = "rpc_crawl"
    max_inflight_items: int = Field(default=1, ge=1, le=100)
    pagination: Optional[PaginationConfig] = None
    clean: Optional[VideoCleanTaskConfig] = None
    download: Optional[VideoDownloadTaskConfig] = None
    analysis: Optional[VideoAnalysisTaskConfig] = None
    source: WorkItemSourceConfig | None = None
    sink: WorkItemSinkConfig = Field(default_factory=DatabaseSinkConfig)
    execution_mode: Literal["invoke_action", "publish_source"] = "invoke_action"

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_io_types(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = value.copy()
        for field_name in ("source", "sink"):
            nested = normalized.get(field_name)
            if isinstance(nested, dict) and "type" not in nested:
                normalized[field_name] = {**nested, "type": "database"}
        return normalized

    @model_validator(mode="after")
    def validate_io_pipeline(self):
        database_to_stream = (
            isinstance(self.source, DatabaseSourceConfig)
            and isinstance(self.sink, RedisStreamSinkConfig)
        )
        if database_to_stream and self.source.completion is None:
            raise ValueError("database source to Redis sink requires source.completion")
        if self.execution_mode == "publish_source" and (
            not database_to_stream or self.pagination is not None
        ):
            raise ValueError(
                "publish_source requires a database source, Redis Stream sink, and no pagination"
            )
        return self

    @field_validator("executor", mode="before")
    @classmethod
    def normalize_legacy_executor(cls, value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "rpc_crawl"
        return value


class TaskConfigType(TypeDecorator):
    """SQLAlchemy TypeDecorator: 将 TaskConfig 映射为 PostgreSQL JSONB（或其他 DB 的 JSON），
    Python 端使用 TaskConfig pydantic 实例。
    必须使用 load_dialect_impl 声明正确的列类型，否则 UPDATE 时会以 VARCHAR 绑定导致 DatatypeMismatchError。
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        if dialect.name in ("mysql", "mariadb"):
            return dialect.type_descriptor(JSON())
        # SQLite 原生支持 JSON (3.9+)，其他回退到 Text 存 JSON 字符串
        if dialect.name == "sqlite":
            # 让 SQLAlchemy 用 JSON 类型（会用 sqlite json1 扩展或 TEXT+处理）
            try:
                return dialect.type_descriptor(JSON())
            except Exception:
                return dialect.type_descriptor(Text())
        # 其他数据库回退为 TEXT 存 JSON 字符串
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, TaskConfig):
            data = value.model_dump(exclude_defaults=True)
            for field_name in ("source", "sink"):
                if field_name in data:
                    field_value = getattr(value, field_name)
                    data[field_name]["type"] = field_value.type
        elif isinstance(value, dict):
            data = value
        else:
            raise TypeError(f"TaskConfigType expects TaskConfig/dict/None, got {type(value).__name__}")

        # 对于原生 JSON/JSONB 列，返回 Python dict/list，让驱动负责序列化
        # 对于 Text 回退，返回 JSON 字符串
        if dialect is None:
            # 测试或未知 dialect：优先返回 dict（多数路径都能处理）
            return data
        if dialect.name in ("postgresql", "mysql", "mariadb", "sqlite"):
            return data
        return json.dumps(data)

    def process_result_value(self, value: Any, dialect) -> Optional[TaskConfig]:
        if value is None:
            return None
        if isinstance(value, (str, bytes)):
            try:
                data = json.loads(value)
            except Exception:
                data = {}
        else:
            # JSONB / JSON 列：驱动已反序列化为 dict/list
            data = value
        if isinstance(data, dict):
            return TaskConfig.model_validate(data)
        # 兜底
        return TaskConfig()
