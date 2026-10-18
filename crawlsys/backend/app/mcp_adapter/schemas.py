"""Shared structured response schemas for MCP adapter tools."""

import base64
import binascii
import json
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.analysis import VideoAnalysisStatus
from models.content import ContentResponse


T = TypeVar("T")
_CURSOR_VERSION = 1
_MAX_BUCKET_NAME_LENGTH = 63
_MAX_OBJECT_NAME_LENGTH = 1024
_MAX_METADATA_ITEMS = 32
_MAX_METADATA_KEY_LENGTH = 128
_MAX_METADATA_VALUE_LENGTH = 1024


class ToolErrorCode(str, Enum):
    """Stable MCP error codes."""

    CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"
    INVALID_CURSOR = "INVALID_CURSOR"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    BUCKET_NOT_FOUND = "BUCKET_NOT_FOUND"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    OBJECT_TOO_LARGE = "OBJECT_TOO_LARGE"
    BUCKET_ALREADY_EXISTS = "BUCKET_ALREADY_EXISTS"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ToolResponse(BaseModel, Generic[T]):
    """Successful MCP tool response."""

    ok: Literal[True] = True
    data: T
    meta: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    """A client-safe MCP error payload."""

    code: ToolErrorCode
    message: str
    issues: list[dict[str, str]] = Field(default_factory=list)
    correlation_id: str


class ToolErrorResponse(BaseModel):
    """Failed MCP tool response."""

    ok: Literal[False] = False
    error: ToolError


class PageMeta(BaseModel):
    """Cursor pagination metadata shared by database list tools."""

    next_cursor: str | None = None
    has_more: bool = False
    limit: int = Field(ge=1, le=100)


class ContentSummary(BaseModel):
    """Content list item without body or extension data."""

    id: int
    platform: str = Field(max_length=50)
    content_id: str = Field(max_length=64)
    content_type: str = Field(max_length=10)
    title: str | None = Field(default=None, max_length=512)
    desc: str | None = None
    author_id: str | None = Field(default=None, max_length=64)
    pub_time: datetime | None = None
    created_time: datetime
    updated_time: datetime


ContentDetail = ContentResponse


class UserSummary(BaseModel):
    """User list item without profile body or extension data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str | None = Field(default=None, max_length=50)
    user_id: str | None = Field(default=None, max_length=64)
    avatar: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    follower_count: int = 0
    following_count: int = 0
    content_count: int = 0
    verified: str | None = Field(default=None, max_length=255)
    created_time: datetime | None = None
    updated_time: datetime | None = None


class UserDetail(UserSummary):
    """Full user record including profile, counts and extension data."""

    gender: int | None = None
    email: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=500)
    description: str | None = None
    education: str | None = None
    experience: str | None = None
    location: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    country_code: str | None = Field(default=None, max_length=10)
    birthday: str | None = Field(default=None, max_length=20)
    extend: str | None = None
    created_at: datetime | None = None


class ScoreDimensionSummary(BaseModel):
    """One scored dimension flattened for list summaries."""

    dimension_id: str | None = None
    name: str | None = None
    awarded_points: float | None = None
    max_points: float | None = None
    scorable: bool = False
    unscorable_reason: str | None = None


class AnalysisSummary(BaseModel):
    """Analysis list item with flattened key fields of the result JSON."""

    id: int
    platform: str = Field(max_length=50)
    content_id: str = Field(max_length=64)
    # Operator-first presentation fields. Keep these near the top so MCP clients
    # encounter decision-ready information before technical metadata.
    score_text: str = "未评分"
    score_rate_percent: float | None = None
    views_text: str = "暂无数据"
    published_text: str = Field(
        default="发布日期未知",
        description="由数据库 UTC 发布时间转换得到的北京时间展示文本",
    )
    material_grade: str | None = None
    structure_text: str = "结构未知"
    review_status: str = "待确认"
    key_issues: list[str] = Field(default_factory=list)
    score_details_included: bool = False
    status: VideoAnalysisStatus
    model_name: str = Field(max_length=500)
    storage_bucket: str = Field(min_length=3, max_length=_MAX_BUCKET_NAME_LENGTH)
    storage_object: str | None = Field(default=None, max_length=_MAX_OBJECT_NAME_LENGTH)
    created_time: datetime
    updated_time: datetime | None = None
    # Flattened analysis_result fields (None when the analysis has no result).
    schema_version: str | None = None
    confidence_overall: float | None = None
    gate_status: str | None = None
    scoring_status: str | None = None
    recommended_grade: str | None = None
    system_disposition: str | None = None
    decision_reasons: list[str] = Field(default_factory=list)
    review_route: str | None = None
    partial_points: float | None = None
    partial_max_points: float | None = None
    diagnostic_total: float | None = None
    primary_type: str | None = None
    secondary_types: list[str] = Field(default_factory=list)
    topology: str | None = None
    scene_count: int | None = None
    cut_frequency: float | None = None
    average_shot_duration: float | None = None
    evidence_complete: bool | None = None
    sampled_frame_count: int | None = None
    # Score dimensions with per-dimension results.
    common_score_c: list[ScoreDimensionSummary] = Field(default_factory=list)
    specialized_score_g: list[ScoreDimensionSummary] = Field(default_factory=list)
    specialized_score_r: list[ScoreDimensionSummary] = Field(default_factory=list)
    # Joined content/material fields (None when the source rows are missing).
    pub_time: datetime | None = None
    view_count: int | None = None
    grade_reason: str | None = None
    created_pub_delta_hours: float | None = None
    error_summary: str | None = None


class AnalysisIssue(BaseModel):
    """A compact validation issue for historical analysis JSON."""

    path: str = Field(max_length=256)
    message: str = Field(max_length=512)


class AnalysisDetail(AnalysisSummary):
    """Full analysis record preserving the raw result JSON and validation status."""

    share_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    video_url: str | None = Field(default=None, max_length=4096)
    video_url_available: bool = False
    video_url_expires_at: datetime | None = None
    analysis_result: dict[str, Any] | None = None
    schema_valid: bool
    schema_issues: list[AnalysisIssue] = Field(default_factory=list)


class BucketInfo(BaseModel):
    """MinIO bucket metadata."""

    name: str = Field(min_length=3, max_length=_MAX_BUCKET_NAME_LENGTH)
    creation_date: datetime | None = None


class ObjectInfo(BaseModel):
    """MinIO object metadata returned by list and stat operations."""

    bucket: str = Field(min_length=3, max_length=_MAX_BUCKET_NAME_LENGTH)
    object_name: str = Field(min_length=1, max_length=_MAX_OBJECT_NAME_LENGTH)
    size: int = Field(ge=0)
    etag: str | None = Field(default=None, max_length=256)
    content_type: str | None = Field(default=None, max_length=255)
    last_modified: datetime | None = None
    version_id: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, metadata: dict[str, str]) -> dict[str, str]:
        if len(metadata) > _MAX_METADATA_ITEMS:
            raise ValueError(f"metadata may contain at most {_MAX_METADATA_ITEMS} items")
        for key, value in metadata.items():
            if not 1 <= len(key) <= _MAX_METADATA_KEY_LENGTH:
                raise ValueError("metadata keys must contain 1-128 characters")
            if len(value) > _MAX_METADATA_VALUE_LENGTH:
                raise ValueError("metadata values may contain at most 1024 characters")
        return metadata


class UploadResult(BaseModel):
    """Result of a successful MinIO upload."""

    bucket: str = Field(min_length=3, max_length=_MAX_BUCKET_NAME_LENGTH)
    object_name: str = Field(min_length=1, max_length=_MAX_OBJECT_NAME_LENGTH)
    size: int = Field(ge=0)
    etag: str | None = Field(default=None, max_length=256)
    version_id: str | None = Field(default=None, max_length=1024)


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor is invalid for the requested tool."""


def encode_cursor(kind: str, timestamp: datetime, row_id: int) -> str:
    """Encode an opaque, versioned cursor for a stable timestamp/id ordering."""
    if not kind or not isinstance(row_id, int) or isinstance(row_id, bool) or row_id < 1:
        raise ValueError("Invalid cursor arguments.")

    payload = {
        "v": _CURSOR_VERSION,
        "kind": kind,
        "timestamp": timestamp.isoformat(),
        "row_id": row_id,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(expected_kind: str, value: str) -> tuple[datetime, int]:
    """Decode and validate a cursor for the expected list tool kind."""
    try:
        if not isinstance(value, str) or not value:
            raise InvalidCursorError("Invalid cursor.")
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if not isinstance(payload, dict) or set(payload) != {"v", "kind", "timestamp", "row_id"}:
            raise InvalidCursorError("Invalid cursor.")
        if payload["v"] != _CURSOR_VERSION or payload["kind"] != expected_kind:
            raise InvalidCursorError("Invalid cursor.")
        if not isinstance(payload["timestamp"], str):
            raise InvalidCursorError("Invalid cursor.")
        timestamp = datetime.fromisoformat(payload["timestamp"])
        row_id = payload["row_id"]
        if not isinstance(row_id, int) or isinstance(row_id, bool) or row_id < 1:
            raise InvalidCursorError("Invalid cursor.")
    except (TypeError, ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        if isinstance(exc, InvalidCursorError):
            raise
        raise InvalidCursorError("Invalid cursor.") from exc
    return timestamp, row_id
