"""Action parser configuration request and response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from api.crawler.schemas import CrawlerReadSchema, CrawlerSchema
from parser.definition import FieldType, ParserDefinition, ParserOutput


class ParserSampleCreateRequest(CrawlerSchema):
    params: dict[str, Any] = Field(default_factory=dict)
    confirm_side_effect: bool = False


class ParserSampleRead(CrawlerReadSchema):
    sample_id: int
    ba_id: int
    response_sha256: str
    response_bytes: int
    sanitizer_version: str
    rpc_duration_ms: int
    created_at: datetime


class ParserSampleDetailRead(ParserSampleRead):
    redacted_preview: dict[str, Any] | list[Any]


class ParserSampleList(CrawlerSchema):
    items: list[ParserSampleRead]


class ParserRevisionCreateRequest(CrawlerSchema):
    definition: ParserDefinition
    assist_receipt: str | None = None


class ParserRevisionPatchRequest(CrawlerSchema):
    lock_version: int = Field(ge=0)
    definition: ParserDefinition
    assist_receipt: str | None = None


class ParserPreviewRequest(CrawlerSchema):
    lock_version: int = Field(ge=0)
    sample_ids: list[int] = Field(min_length=1, max_length=50)


class ParserAssistRequest(CrawlerSchema):
    lock_version: int = Field(ge=0)
    sample_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    output: ParserOutput


class ParserSuggestionRequest(CrawlerSchema):
    sample_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    output: ParserOutput


class ParserAssistRead(CrawlerSchema):
    definition: ParserDefinition
    preview: list[Any]
    assist_receipt: str


class ParserCapabilitiesRead(CrawlerSchema):
    model_datatypes: list[str]
    field_types: list[FieldType]
    model_fields: dict[str, list[ParserModelFieldRead]]


class ParserModelFieldRead(CrawlerSchema):
    target: str
    required: bool
    value_types: list[FieldType]


class ParserRevisionRead(CrawlerReadSchema):
    revision_id: int
    ba_id: int
    revision_no: int
    status: Literal["draft", "published", "archived"]
    definition: ParserDefinition
    definition_sha256: str
    source: Literal["manual", "ai", "restore"]
    source_sample_id: int | None = None
    restored_from_revision_id: int | None = None
    validation_report: dict[str, Any] | None = None
    lock_version: int
    generation_metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class ParserRevisionList(CrawlerSchema):
    items: list[ParserRevisionRead]


class ParserPreviewRead(CrawlerReadSchema):
    definition_sha256: str
    samples: list[dict[str, Any]]
    sample_ids: list[int]
    source_records: int
    valid_records: int
    invalid_records: int
    passed: bool
    errors: list[dict[str, Any]]
    errors_truncated: bool
    preview: list[Any]


__all__ = [
    "ParserAssistRequest",
    "ParserAssistRead",
    "ParserCapabilitiesRead",
    "ParserModelFieldRead",
    "ParserPreviewRead",
    "ParserPreviewRequest",
    "ParserRevisionCreateRequest",
    "ParserRevisionList",
    "ParserRevisionPatchRequest",
    "ParserRevisionRead",
    "ParserSampleCreateRequest",
    "ParserSampleDetailRead",
    "ParserSampleList",
    "ParserSampleRead",
    "ParserSuggestionRequest",
]
