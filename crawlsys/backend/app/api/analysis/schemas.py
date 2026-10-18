"""Video material analysis API schemas."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AnalysisStatus = Literal["pending", "succeeded", "processing", "failed"]
GateStatus = Literal["PASS", "BLOCK", "INSUFFICIENT_EVIDENCE"]
ScoringStatus = Literal["PROVISIONAL", "UNAVAILABLE"]


class AnalysisSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class MaterialAnalysisListItem(AnalysisSchema):
    platform: str
    content_id: str
    status: AnalysisStatus
    grade_rank: int
    grade_reason: str | None = None
    grade_time: datetime
    snap_view_count: int | None = None
    snap_pub_time: datetime | None = None
    snap_hours: float | None = None
    clean_status: str
    expire_time: datetime
    created_time: datetime | None = None
    llm_model_id: int | None = None
    model: str | None = None
    attempt_count: int | None = None
    started_time: datetime | None = None
    finished_time: datetime | None = None
    updated_time: datetime | None = None
    schema_version: str | None = None
    overall_score: float | None = None
    gate_status: GateStatus | None = None
    scoring_status: ScoringStatus | None = None


class MaterialAnalysisList(AnalysisSchema):
    items: list[MaterialAnalysisListItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class AnalysisFilters(AnalysisSchema):
    platforms: list[str]
    statuses: list[AnalysisStatus]
    models: list[str]


class VideoAnalysisRead(AnalysisSchema):
    minio_bucket: str
    minio_object_name: str | None = None
    status: str
    analysis_result: dict[str, Any] | None = None
    error_message: str | None = None
    attempt_count: int
    llm_model_id: int | None = None
    model: str
    started_time: datetime
    finished_time: datetime | None = None
    created_time: datetime
    updated_time: datetime


class MaterialAnalysisDetail(MaterialAnalysisListItem):
    analysis: VideoAnalysisRead | None = None


class VideoUrlResponse(AnalysisSchema):
    url: str
    expires_at: datetime
