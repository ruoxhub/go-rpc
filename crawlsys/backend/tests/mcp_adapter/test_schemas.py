"""MCP 适配层公共 Schema、游标和错误边界测试。"""

from datetime import datetime, timezone

import pytest
from minio.error import S3Error
from pydantic import ValidationError
from unittest.mock import MagicMock

from mcp_adapter.errors import McpToolError, ToolErrorCode, map_tool_error
from mcp_adapter.schemas import (
    AnalysisDetail,
    AnalysisSummary,
    BucketInfo,
    ContentDetail,
    ContentSummary,
    ObjectInfo,
    PageMeta,
    ToolErrorResponse,
    ToolResponse,
    UploadResult,
    UserDetail,
    UserSummary,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from models.analysis import VideoAnalysisStatus


def test_cursor_round_trip_preserves_sort_position():
    timestamp = datetime(2026, 8, 6, 12, 30, tzinfo=timezone.utc)

    value = encode_cursor("content", timestamp, 42)

    assert decode_cursor("content", value) == (timestamp, 42)


def test_cursor_rejects_another_tool_kind():
    value = encode_cursor("content", datetime(2026, 8, 6, tzinfo=timezone.utc), 1)

    with pytest.raises(ValueError, match="cursor"):
        decode_cursor("analysis", value)


@pytest.mark.parametrize("value", ["not-base64", "eyJ2IjoxfQ", "Zm9v"])
def test_cursor_rejects_tampered_or_invalid_base64(value: str):
    with pytest.raises(ValueError, match="cursor"):
        decode_cursor("content", value)


def test_tool_error_response_is_safe_and_has_correlation_id():
    response = map_tool_error(
        RuntimeError("postgresql://user:password@db.internal:5432/crawler"),
        resource="content",
    )

    assert isinstance(response, ToolErrorResponse)
    assert response.ok is False
    assert response.error.code is ToolErrorCode.INTERNAL_ERROR
    assert response.error.correlation_id
    assert "postgresql" not in response.error.message
    assert "password" not in response.model_dump_json()


def test_error_mapping_uses_stable_resource_not_found_code():
    response = map_tool_error(FileNotFoundError("bucket private-data missing"), resource="bucket")

    assert response.error.code is ToolErrorCode.BUCKET_NOT_FOUND
    assert response.error.message == "Bucket not found."


@pytest.mark.parametrize(
    ("sdk_code", "resource", "expected"),
    [
        ("NoSuchKey", "bucket", ToolErrorCode.OBJECT_NOT_FOUND),
        ("NoSuchObject", "bucket", ToolErrorCode.OBJECT_NOT_FOUND),
        ("NoSuchBucket", "object", ToolErrorCode.BUCKET_NOT_FOUND),
        ("AccessDenied", "object", ToolErrorCode.STORAGE_UNAVAILABLE),
    ],
)
def test_error_mapping_handles_minio_s3_errors_without_sdk_details(sdk_code, resource, expected):
    response = map_tool_error(
        S3Error(
            response=MagicMock(),
            code=sdk_code,
            message="minio secret message",
            resource="private-resource",
            request_id="private-request",
            host_id="private-host",
            bucket_name="private-bucket",
            object_name="private-object",
        ),
        resource=resource,
    )

    assert response.error.code is expected
    assert "private" not in response.model_dump_json()


def test_mcp_tool_error_does_not_expose_caller_message():
    secret = "postgresql://user:password@db.internal:5432/crawler"

    response = map_tool_error(
        McpToolError(ToolErrorCode.CONTENT_NOT_FOUND, secret),
        resource="content",
    )

    assert response.error.code is ToolErrorCode.CONTENT_NOT_FOUND
    assert response.error.message == "Content not found."
    assert secret not in response.model_dump_json()


def test_invalid_cursor_error_uses_stable_cursor_code():
    response = map_tool_error(
        InvalidCursorError("cursor payload contains a secret"),
        resource="content",
    )

    assert response.error.code is ToolErrorCode.INVALID_CURSOR
    assert response.error.message == "Invalid cursor."


@pytest.mark.parametrize("limit", [1, 100])
def test_page_meta_accepts_limits_between_one_and_one_hundred(limit: int):
    assert PageMeta(limit=limit).limit == limit


@pytest.mark.parametrize("limit", [0, 101])
def test_page_meta_rejects_limits_outside_one_to_one_hundred(limit: int):
    with pytest.raises(ValidationError):
        PageMeta(limit=limit)


def test_response_models_expose_only_approved_summary_and_detail_fields():
    assert set(ContentSummary.model_fields) == {
        "id", "platform", "content_id", "content_type", "title", "desc", "author_id",
        "pub_time", "created_time", "updated_time",
    }
    assert "content" not in ContentSummary.model_fields
    assert "extend" not in ContentSummary.model_fields
    assert ContentDetail.__name__ == "ContentResponse"
    assert set(UserSummary.model_fields) == {
        "id", "platform", "user_id", "avatar", "name", "username",
        "follower_count", "following_count", "content_count", "verified",
        "created_time", "updated_time",
    }
    assert "email" not in UserSummary.model_fields
    assert "description" not in UserSummary.model_fields
    assert "extend" not in UserSummary.model_fields
    assert set(UserDetail.model_fields) == set(UserSummary.model_fields) | {
        "gender", "email", "phone", "website", "description", "education",
        "experience", "location", "city", "country_code", "birthday",
        "extend", "created_at",
    }
    assert set(AnalysisSummary.model_fields) == {
        "id", "platform", "content_id", "status", "model_name", "storage_bucket",
        "score_text", "score_rate_percent", "views_text", "published_text", "material_grade",
        "structure_text", "review_status", "key_issues", "score_details_included",
        "storage_object", "created_time", "updated_time",
        "schema_version", "confidence_overall", "gate_status", "scoring_status",
        "recommended_grade", "system_disposition", "decision_reasons", "review_route",
        "partial_points", "partial_max_points", "diagnostic_total",
        "primary_type", "secondary_types", "topology",
        "scene_count", "cut_frequency", "average_shot_duration",
        "evidence_complete", "sampled_frame_count",
        "common_score_c", "specialized_score_g", "specialized_score_r",
        "pub_time", "view_count", "grade_reason", "created_pub_delta_hours",
        "error_summary",
    }
    assert set(AnalysisDetail.model_fields) == set(AnalysisSummary.model_fields) | {
        "analysis_result", "schema_valid", "schema_issues", "share_count",
        "like_count", "comment_count", "video_url", "video_url_available",
        "video_url_expires_at",
    }
    assert set(BucketInfo.model_fields) == {"name", "creation_date"}
    assert set(ObjectInfo.model_fields) == {
        "bucket", "object_name", "size", "etag", "content_type", "last_modified",
        "version_id", "metadata",
    }
    assert set(UploadResult.model_fields) == {
        "bucket", "object_name", "size", "etag", "version_id",
    }


def test_analysis_summary_accepts_only_known_statuses_and_nullable_updated_time():
    payload = {
        "id": 1,
        "platform": "tiktok",
        "content_id": "123",
        "status": VideoAnalysisStatus.SUCCEEDED,
        "model_name": "gemini",
        "storage_bucket": "analysis-assets",
        "storage_object": None,
        "created_time": datetime(2026, 8, 6),
        "updated_time": None,
        "error_summary": None,
    }

    assert AnalysisSummary.model_validate(payload).updated_time is None
    with pytest.raises(ValidationError):
        AnalysisSummary.model_validate({**payload, "status": "unknown-status"})


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (BucketInfo, {"name": "ab", "creation_date": None}),
        (BucketInfo, {"name": "a" * 64, "creation_date": None}),
        (ObjectInfo, {"bucket": "valid-bucket", "object_name": "", "size": 0}),
        (ObjectInfo, {"bucket": "valid-bucket", "object_name": "a" * 1025, "size": 0}),
    ],
)
def test_bucket_and_object_name_lengths_are_bounded(model: type, payload: dict):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_object_metadata_has_storage_safe_limits():
    valid = ObjectInfo(
        bucket="valid-bucket",
        object_name="video.mp4",
        size=1,
        metadata={"x-amz-meta-source": "crawler"},
    )
    assert valid.metadata == {"x-amz-meta-source": "crawler"}

    with pytest.raises(ValidationError):
        ObjectInfo(
            bucket="valid-bucket",
            object_name="video.mp4",
            size=1,
            metadata={f"key-{index}": "value" for index in range(33)},
        )
    with pytest.raises(ValidationError):
        ObjectInfo(
            bucket="valid-bucket",
            object_name="video.mp4",
            size=1,
            metadata={"k" * 129: "value"},
        )
    with pytest.raises(ValidationError):
        ObjectInfo(
            bucket="valid-bucket",
            object_name="video.mp4",
            size=1,
            metadata={"key": "v" * 1025},
        )


def test_tool_response_has_structured_success_shape():
    response = ToolResponse(data={"content_id": "123"})

    assert response.ok is True
    assert response.data == {"content_id": "123"}
    assert response.meta == {}
