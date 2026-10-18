from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
import pytest

import models
from models.material import MaterialAnalysisStatus, MaterialClean
from models.analysis import VideoAnalysisResult, VideoAnalysisStatus
from models.results import (
    AnalysisArtifacts,
    AnalysisRequest,
    AnalysisStage,
    AudioSignals,
    DownloadedVideo,
    MediaProbe,
    ProgressCallback,
    ProgressEvent,
    SceneBoundary,
    VideoMetadata,
    VideoSignals,
)


def test_video_analysis_table_contract():
    table = VideoAnalysisResult.__table__

    assert table.name == "t_video_analysis_result"
    assert table.schema == "public"
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key
    assert table.c.id.autoincrement is True
    assert isinstance(table.c.platform.type, String)
    assert table.c.platform.type.length == 50
    assert isinstance(table.c.content_id.type, String)
    assert table.c.content_id.type.length == 64
    assert isinstance(table.c.minio_bucket.type, String)
    assert table.c.minio_bucket.type.length == 255
    assert isinstance(table.c.minio_object_name.type, String)
    assert table.c.minio_object_name.type.length == 1024
    assert table.c.minio_object_name.nullable
    assert isinstance(table.c.status.type, String)
    assert table.c.status.type.length == 16
    assert isinstance(table.c.error_message.type, Text)
    assert table.c.error_message.nullable
    assert isinstance(table.c.attempt_count.type, Integer)
    assert table.c.attempt_count.default.arg == 0
    assert isinstance(table.c.model.type, String)
    assert table.c.model.type.length == 500
    assert all(
        isinstance(table.c[name].type, DateTime)
        for name in ("started_time", "finished_time", "created_time", "updated_time")
    )
    assert all(
        table.c[name].nullable is False
        for name in (
            "id",
            "platform",
            "content_id",
            "minio_bucket",
            "status",
            "attempt_count",
            "model",
            "created_time",
            "updated_time",
        )
    )
    assert table.c.started_time.nullable is True
    assert table.c.finished_time.nullable is True
    assert table.c.created_time.server_default is not None
    assert table.c.updated_time.server_default is not None
    assert table.c.updated_time.onupdate is not None


def test_video_analysis_uses_postgresql_jsonb():
    column = VideoAnalysisResult.__table__.c.analysis_result

    assert isinstance(column.type, JSONB)
    assert column.nullable


def test_video_analysis_indexes():
    indexes = {index.name: index for index in VideoAnalysisResult.__table__.indexes}

    assert "uq_video_analysis_platform_content" not in indexes

    status_index = indexes["idx_video_analysis_status_updated"]
    assert not status_index.unique
    assert [column.name for column in status_index.columns] == ["status", "updated_time"]


def test_analysis_status_values():
    assert MaterialAnalysisStatus.PENDING == 0
    assert MaterialAnalysisStatus.SUCCEEDED == 1
    assert MaterialAnalysisStatus.PROCESSING == 2
    assert MaterialAnalysisStatus.FAILED == 3
    assert VideoAnalysisStatus.PROCESSING == "processing"
    assert VideoAnalysisStatus.SUCCEEDED == "succeeded"
    assert VideoAnalysisStatus.FAILED == "failed"
    assert isinstance(VideoAnalysisStatus.PROCESSING, str)


def test_models_package_exports_video_analysis_types():
    assert models.MaterialAnalysisStatus is MaterialAnalysisStatus
    assert models.VideoAnalysisResult is VideoAnalysisResult
    assert models.VideoAnalysisStatus is VideoAnalysisStatus
    assert "MaterialAnalysisStatus" in models.__all__
    assert "VideoAnalysisResult" in models.__all__
    assert "VideoAnalysisStatus" in models.__all__


def test_material_analysis_comment_describes_all_four_states():
    comment = MaterialClean.__table__.c.is_analysis.comment

    assert comment is not None
    assert all(
        description in comment
        for description in ("0=未分析", "1=分析成功", "2=分析中", "3=分析失败")
    )


def test_results_keeps_all_runtime_types_importable():
    assert all(
        runtime_type is not None
        for runtime_type in (
            AnalysisArtifacts,
            AnalysisRequest,
            AnalysisStage,
            AudioSignals,
            DownloadedVideo,
            MediaProbe,
            ProgressCallback,
            ProgressEvent,
            SceneBoundary,
            VideoMetadata,
            VideoSignals,
        )
    )


@pytest.mark.parametrize("review_route", ["R", "G", None])
def test_analysis_request_accepts_explicit_review_routes(review_route):
    assert AnalysisRequest(source="video.mp4", review_route=review_route).review_route == review_route


def test_analysis_request_rejects_unknown_review_route():
    with pytest.raises(ValueError, match="review_route"):
        AnalysisRequest(source="video.mp4", review_route="unknown")
