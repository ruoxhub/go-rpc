"""Analysis API contract tests that do not require PostgreSQL."""
from api.main import create_app
from api.analysis.repository import STATUS_NAMES, STATUS_VALUES, _overall_score
from api.analysis.schemas import VideoAnalysisRead
from core.config import SchedulerConfig
from models.analysis import VideoAnalysisResult
from models.material import MaterialAnalysisStatus


def test_app_registers_analysis_routes():
    schema = create_app(SchedulerConfig()).openapi()
    paths = schema["paths"]
    assert "/api/analysis" in paths
    assert "/api/analysis/filters" in paths
    assert "/api/analysis/{platform}/{content_id}" in paths
    assert "/api/analysis/{platform}/{content_id}/video-url" in paths
    assert "/api/analysis/{platform}/{content_id}/thumbnail" in paths


def test_material_analysis_status_mapping_is_bidirectional():
    assert STATUS_NAMES[MaterialAnalysisStatus.PENDING] == "pending"
    assert STATUS_NAMES[MaterialAnalysisStatus.SUCCEEDED] == "succeeded"
    assert STATUS_VALUES["processing"] == MaterialAnalysisStatus.PROCESSING
    assert STATUS_VALUES["failed"] == MaterialAnalysisStatus.FAILED


def test_overall_score_is_optional_and_numeric():
    result = {
        "meta": {"schema_version": "v4.0"},
        "evaluation": {"diagnostic_total": 8},
        "decision": {
            "gate_status": "PASS",
            "scoring_status": "PROVISIONAL",
        },
    }

    assert _overall_score(result) == 8.0
    assert _overall_score({"meta": {"schema_version": "v4.0"}}) is None
    assert _overall_score(None) is None


def test_video_analysis_model_reference_is_nullable_for_historical_rows():
    assert VideoAnalysisResult.__table__.c.llm_model_id.nullable is True
    assert any(
        foreign_key.target_fullname == "public.t_llm_model.id"
        for foreign_key in VideoAnalysisResult.__table__.c.llm_model_id.foreign_keys
    )
    payload = VideoAnalysisRead.model_validate(
        {
            "minio_bucket": "videos",
            "status": "succeeded",
            "attempt_count": 1,
            "model": "provider/legacy-model",
            "started_time": "2026-01-01T00:00:00",
            "created_time": "2026-01-01T00:00:00",
            "updated_time": "2026-01-01T00:00:00",
        }
    )
    assert payload.llm_model_id is None
