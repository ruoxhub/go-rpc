"""Queries for cleaned materials and their optional analysis records."""
from __future__ import annotations

from math import ceil, isfinite

from sqlalchemy import and_, func, select

from api.analysis.schemas import MaterialAnalysisListItem
from models.analysis import VideoAnalysisResult
from models.material import MaterialAnalysisStatus, MaterialClean

STATUS_NAMES = {
    MaterialAnalysisStatus.PENDING: "pending",
    MaterialAnalysisStatus.SUCCEEDED: "succeeded",
    MaterialAnalysisStatus.PROCESSING: "processing",
    MaterialAnalysisStatus.FAILED: "failed",
}
STATUS_VALUES = {value: key.value for key, value in STATUS_NAMES.items()}
_GATE_STATUSES = {"PASS", "BLOCK", "INSUFFICIENT_EVIDENCE"}
_SCORING_STATUSES = {"PROVISIONAL", "UNAVAILABLE"}
_EMPTY_SUMMARY = (None, None, None, None)


def _numeric_summary(value) -> tuple[bool, float | None]:
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, None
    try:
        number = float(value)
    except OverflowError:
        return False, None
    return (True, number) if isfinite(number) else (False, None)


def _result_summary(result) -> tuple[
    str | None,
    float | None,
    str | None,
    str | None,
]:
    """Extract a validated list summary without interpreting decision rules."""
    if result is None:
        return _EMPTY_SUMMARY
    if not isinstance(result, dict):
        return _EMPTY_SUMMARY

    meta = result.get("meta")
    if meta is not None and not isinstance(meta, dict):
        return _EMPTY_SUMMARY
    schema_version = meta.get("schema_version") if meta is not None else None
    if schema_version is not None and not isinstance(schema_version, str):
        return _EMPTY_SUMMARY

    if schema_version != "v4.0":
        return _EMPTY_SUMMARY
    evaluation = result.get("evaluation")
    decision = result.get("decision")
    if not isinstance(evaluation, dict) or not isinstance(decision, dict):
        return _EMPTY_SUMMARY
    if "diagnostic_total" not in evaluation:
        return _EMPTY_SUMMARY
    valid, score = _numeric_summary(evaluation.get("diagnostic_total"))
    gate_status = decision.get("gate_status")
    scoring_status = decision.get("scoring_status")
    if (
        not valid
        or not isinstance(gate_status, str)
        or not isinstance(scoring_status, str)
        or gate_status not in _GATE_STATUSES
        or scoring_status not in _SCORING_STATUSES
    ):
        return _EMPTY_SUMMARY
    return schema_version, score, gate_status, scoring_status


def _overall_score(result: dict | None) -> float | None:
    """Compatibility accessor for callers that only need the numeric summary."""
    return _result_summary(result)[1]


def _item(material: MaterialClean, analysis: VideoAnalysisResult | None):
    schema_version, overall_score, gate_status, scoring_status = _result_summary(
        analysis.analysis_result if analysis else None
    )
    return MaterialAnalysisListItem(
        platform=material.platform,
        content_id=material.content_id,
        status=STATUS_NAMES[MaterialAnalysisStatus(material.is_analysis)],
        grade_rank=material.grade_rank,
        grade_reason=material.grade_reason,
        grade_time=material.grade_time,
        snap_view_count=material.snap_view_count,
        snap_pub_time=material.snap_pub_time,
        snap_hours=material.snap_hours,
        clean_status=material.clean_status,
        expire_time=material.expire_time,
        created_time=material.created_time,
        llm_model_id=analysis.llm_model_id if analysis else None,
        model=analysis.model if analysis else None,
        attempt_count=analysis.attempt_count if analysis else None,
        started_time=analysis.started_time if analysis else None,
        finished_time=analysis.finished_time if analysis else None,
        updated_time=analysis.updated_time if analysis else material.updated_time,
        schema_version=schema_version,
        overall_score=overall_score,
        gate_status=gate_status,
        scoring_status=scoring_status,
    )


class AnalysisRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _join():
        return and_(
            MaterialClean.platform == VideoAnalysisResult.platform,
            MaterialClean.content_id == VideoAnalysisResult.content_id,
        )

    async def list(self, *, page, page_size, platform=None, status=None, model=None):
        conditions = [MaterialClean.is_delete == 0]
        if platform:
            conditions.append(MaterialClean.platform == platform)
        if status:
            conditions.append(MaterialClean.is_analysis == STATUS_VALUES[status])
        if model:
            conditions.append(VideoAnalysisResult.model == model)
        stmt = (
            select(MaterialClean, VideoAnalysisResult)
            .outerjoin(VideoAnalysisResult, self._join())
            .where(*conditions)
            .order_by(MaterialClean.created_time.desc(), MaterialClean.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_stmt = (
            select(func.count(MaterialClean.id))
            .outerjoin(VideoAnalysisResult, self._join())
            .where(*conditions)
        )
        async with self.db.asession_scope() as session:
            rows = (await session.execute(stmt)).all()
            total = int((await session.scalar(count_stmt)) or 0)
        return [_item(material, analysis) for material, analysis in rows], total, ceil(total / page_size)

    async def filters(self):
        async with self.db.asession_scope() as session:
            platforms = (await session.scalars(select(MaterialClean.platform).where(MaterialClean.is_delete == 0).distinct().order_by(MaterialClean.platform))).all()
            statuses = (await session.scalars(select(MaterialClean.is_analysis).where(MaterialClean.is_delete == 0).distinct().order_by(MaterialClean.is_analysis))).all()
            models = (await session.scalars(select(VideoAnalysisResult.model).distinct().order_by(VideoAnalysisResult.model))).all()
        return list(platforms), [STATUS_NAMES[MaterialAnalysisStatus(value)] for value in statuses], list(models)

    async def detail(self, platform: str, content_id: str):
        stmt = (
            select(MaterialClean, VideoAnalysisResult)
            .outerjoin(VideoAnalysisResult, self._join())
            .where(MaterialClean.platform == platform, MaterialClean.content_id == content_id, MaterialClean.is_delete == 0)
        )
        async with self.db.asession_scope() as session:
            return (await session.execute(stmt)).one_or_none()
