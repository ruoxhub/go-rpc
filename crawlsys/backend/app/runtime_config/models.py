"""Pure Pydantic models for validated runtime configuration."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlparse

from common.constants import (
    MAX_ANALYSIS_FRAMES,
    MIN_FRAME_INTERVAL_SECONDS,
    MIN_ZOMBIE_REAP_SECONDS,
)
from core.task_schedule import validate_timezone
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)


PositiveInt = Annotated[StrictInt, Field(gt=0)]
PositiveNumber = Annotated[StrictFloat, Field(gt=0, allow_inf_nan=False)]
NonNegativeNumber = Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]
FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]


class RuntimeConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class LlmSettings(RuntimeConfigModel):
    default_analysis_model_id: PositiveInt | None = None
    default_transcription_model_id: PositiveInt | None = None
    max_tokens: PositiveInt = 8192
    temperature: NonNegativeNumber = 0.0
    enable_thinking: StrictBool = False


class LlmSettingsUpdate(RuntimeConfigModel):
    default_analysis_model_id: PositiveInt | None = None
    default_transcription_model_id: PositiveInt | None = None
    max_tokens: PositiveInt | None = Field(default=None, validate_default=False)
    temperature: NonNegativeNumber | None = Field(default=None, validate_default=False)
    enable_thinking: StrictBool | None = Field(default=None, validate_default=False)

    @field_validator("max_tokens", "temperature", "enable_thinking", mode="before")
    @classmethod
    def reject_null_generation_fields(cls, value):
        if value is None:
            raise ValueError("may not be null")
        return value


class SchedulerSettings(RuntimeConfigModel):
    worker_id: StrictStr = "scheduler-local-01"
    timezone: StrictStr = "Asia/Shanghai"
    poll_interval_ms: PositiveInt = 1000
    default_loop_interval_seconds: PositiveInt = 3600
    batch_size: PositiveInt = 10
    zombie_reap_after_seconds: Annotated[
        StrictInt, Field(ge=MIN_ZOMBIE_REAP_SECONDS)
    ] = 600
    graceful_shutdown_seconds: PositiveInt = 30

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        validate_timezone(value)
        return value


def _is_http_url(
    value: str,
    *,
    allow_userinfo: bool,
    allow_query_fragment: bool = True,
) -> bool:
    if any(character.isspace() for character in value):
        return False
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and (allow_userinfo or (parsed.username is None and parsed.password is None))
        and (allow_query_fragment or (not parsed.query and not parsed.fragment))
    )


class RpcSettings(RuntimeConfigModel):
    base_url: StrictStr = "http://localhost:5612"
    timeout_seconds: PositiveInt = 60

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not _is_http_url(
            value,
            allow_userinfo=False,
            allow_query_fragment=False,
        ):
            raise ValueError("must be a valid http(s) URL")
        return value


class AnalysisVideoSettings(RuntimeConfigModel):
    is_base64: StrictBool = False
    frame_sampling_strategy: Literal[
        "interval", "count", "timestamps", "scene_guided"
    ] = "scene_guided"
    max_frames: Annotated[StrictInt, Field(ge=2, le=MAX_ANALYSIS_FRAMES)] = 32
    frame_interval_seconds: Annotated[
        StrictFloat,
        Field(ge=MIN_FRAME_INTERVAL_SECONDS, allow_inf_nan=False),
    ] = 5.0
    frame_timestamps: tuple[NonNegativeNumber, ...] = ()

    @field_validator("frame_interval_seconds", mode="before")
    @classmethod
    def reject_boolean_interval(cls, value):
        if isinstance(value, bool):
            raise ValueError("must be a number, not a boolean")
        return value

    @field_validator("frame_timestamps", mode="before")
    @classmethod
    def reject_boolean_timestamps(cls, value):
        if isinstance(value, (list, tuple)) and any(
            isinstance(timestamp, bool) for timestamp in value
        ):
            raise ValueError("must contain numbers, not booleans")
        return value

    @model_validator(mode="after")
    def require_explicit_timestamps(self):
        if self.frame_sampling_strategy == "timestamps" and not self.frame_timestamps:
            raise ValueError(
                "frame_timestamps must not be empty for timestamps strategy"
            )
        return self


class ProxySettings(RuntimeConfigModel):
    url: StrictStr = ""

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if value and not _is_http_url(value, allow_userinfo=True):
            raise ValueError("must be empty or a valid http(s) URL")
        return value


class ProxySettingsUpdate(RuntimeConfigModel):
    url: StrictStr | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value and value.strip() and not _is_http_url(value, allow_userinfo=True):
            raise ValueError("must be empty or a valid http(s) URL")
        return value


class GradeRuleModel(RuntimeConfigModel):
    max_hours: PositiveNumber
    min_views: Annotated[StrictInt, Field(ge=0)]


FilterOperator = Literal["=", "!=", ">", ">=", "<", "<=", "in", "exists"]
JsonScalar = StrictStr | StrictInt | FiniteFloat | StrictBool | None

_PLAIN_FILTER_FIELDS = {
    "view_count",
    "pub_time",
    "download_time",
    "created_time",
}
_EXTEND_DATA_FIELD = re.compile(
    r"^extend_data\.[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class FilterRule(RuntimeConfigModel):
    field: StrictStr
    operator: FilterOperator
    value: JsonScalar | datetime | list[JsonScalar | datetime] = None

    @field_validator("field")
    @classmethod
    def validate_field(cls, value: str) -> str:
        if value not in _PLAIN_FILTER_FIELDS and not _EXTEND_DATA_FIELD.fullmatch(value):
            raise ValueError("field is not allowed")
        return value

    @field_validator("value")
    @classmethod
    def validate_operator_value(
        cls,
        value: JsonScalar | datetime | list[JsonScalar | datetime],
        info: ValidationInfo,
    ) -> JsonScalar | datetime | list[JsonScalar | datetime]:
        operator = info.data.get("operator")
        field = info.data.get("field")
        if operator == "exists":
            if value is not None:
                raise ValueError("exists requires a null value")
            return value
        if operator == "in":
            if not isinstance(value, list) or not value:
                raise ValueError("in requires a non-empty scalar list")
        elif value is None or isinstance(value, list):
            raise ValueError("comparison operators require a scalar value")

        values = value if isinstance(value, list) else [value]
        if field == "view_count":
            if any(type(item) is not int for item in values):
                raise ValueError("view_count requires strict integers")
            return value

        if field in {"pub_time", "download_time", "created_time"}:
            if any(not isinstance(item, str) for item in values):
                raise ValueError("date fields require ISO date-time strings")
            try:
                parsed = [
                    _as_naive_utc(datetime.fromisoformat(item)) for item in values
                ]
            except ValueError as error:
                raise ValueError("date fields require valid ISO date-time strings") from error
            return parsed if isinstance(value, list) else parsed[0]

        if any(isinstance(item, datetime) for item in values):
            raise ValueError("extend_data requires JSON scalar values")
        if operator == "in":
            return value
        if operator in {">", ">=", "<", "<="}:
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise ValueError("numeric comparison requires a number")
        return value


class PlatformCleanerPolicy(RuntimeConfigModel):
    p2: list[GradeRuleModel] = Field(default_factory=list)
    p3: list[GradeRuleModel] = Field(default_factory=list)
    p1: list[GradeRuleModel] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)

    @field_validator("p1")
    @classmethod
    def require_grade_rule(
        cls, value: list[GradeRuleModel], info: ValidationInfo
    ) -> list[GradeRuleModel]:
        if not (value or info.data.get("p2") or info.data.get("p3")):
            raise ValueError("at least one p1, p2, or p3 grade rule is required")
        return value


class CleanerSettings(RuntimeConfigModel):
    enabled: StrictBool = True
    poll_interval: PositiveNumber = 3600.0
    batch_size: PositiveInt = 1000
    max_batches_per_platform: PositiveInt = 10
    ttl_days: PositiveInt = 14
    watermark_key: StrictStr = Field(default="cleaner:grade:watermark", min_length=1)
    suspect_seconds: PositiveNumber = 120.0
