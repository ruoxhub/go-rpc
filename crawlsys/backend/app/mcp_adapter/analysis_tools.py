"""Read-only MCP adapter tools for persisted video analysis results."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import and_, or_, select

from mcp_adapter.context import McpAppResources
from mcp_adapter.errors import McpToolError, map_tool_error
from mcp_adapter.observability import observe_tool_call
from mcp_adapter.schemas import (
    AnalysisDetail,
    AnalysisIssue,
    AnalysisSummary,
    PageMeta,
    ToolErrorCode,
    ToolResponse,
    decode_cursor,
    encode_cursor,
)
from models.analysis import VideoAnalysisResult, VideoAnalysisStatus
from models.content import Content
from models.material import MaterialClean
from models.results import AnalysisResult
from services.video_download.naming import video_object_name


_ANALYSIS_LIST_CURSOR_KIND = "analysis-list-v1"
_NULL_UPDATED_TIME_CURSOR_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)
_MAX_SCHEMA_ISSUES = 10
_MAX_ERROR_SUMMARY_LENGTH = 512
_ALL_STATUSES = "all"
_DETAIL_LEVEL_COMPACT = "compact"
_DETAIL_LEVEL_DETAILED = "detailed"
_DETAIL_LEVELS = {_DETAIL_LEVEL_COMPACT, _DETAIL_LEVEL_DETAILED}
_OPERATOR_DISPLAY_ORDER = [
    "score",
    "traffic",
    "published",
    "structure",
    "review",
    "issues",
]
_TOPOLOGY_LABELS = {
    "ONE_TAKE": "一镜到底",
    "MONTAGE": "多镜头剪辑",
}
_BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


@observe_tool_call("get_analysis_result", resource="analysis")
async def get_analysis_result(
    resources: McpAppResources,
    platform: str,
    content_id: str,
):
    """Return one persisted analysis result by its platform-local content id."""
    try:
        async with resources.db.asession_scope() as session:
            row = (
                await session.execute(
                    select(VideoAnalysisResult, Content)
                    .outerjoin(
                        Content,
                        and_(
                            Content.platform == VideoAnalysisResult.platform,
                            Content.content_id == VideoAnalysisResult.content_id,
                        ),
                    )
                    .where(
                        VideoAnalysisResult.platform == platform,
                        VideoAnalysisResult.content_id == content_id,
                    )
                )
            ).first()
        if row is None:
            raise FileNotFoundError
        result, content = row
        video_url, video_url_expires_at = await _analysis_video_url(resources, result)
        return ToolResponse(
            data=_to_analysis_detail(
                result,
                content=content,
                video_url=video_url,
                video_url_expires_at=video_url_expires_at,
            )
        )
    except Exception as exc:
        return map_tool_error(exc, resource="analysis")


@observe_tool_call("list_analysis_results", resource="analysis")
async def list_analysis_results(
    resources: McpAppResources,
    platform: str | None = None,
    status: str | VideoAnalysisStatus | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    limit: int = 20,
    cursor: str | None = None,
    detail_level: Literal["compact", "detailed"] = _DETAIL_LEVEL_COMPACT,
):
    """Return analysis summaries in stable newest-first cursor order.

    ``status`` defaults to ``succeeded``; pass ``"all"`` to include every status.
    ``detail_level`` defaults to ``compact`` for operator-facing output. Pass
    ``"detailed"`` to include every C/G/R score dimension.
    """
    try:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if detail_level not in _DETAIL_LEVELS:
            raise ValueError("detail_level must be 'compact' or 'detailed'")

        status_value: VideoAnalysisStatus | None
        if status is None:
            status_value = VideoAnalysisStatus.SUCCEEDED
        elif status == _ALL_STATUSES:
            status_value = None
        else:
            status_value = VideoAnalysisStatus(status)
        cursor_position = (
            decode_cursor(_ANALYSIS_LIST_CURSOR_KIND, cursor) if cursor is not None else None
        )
        filters = []
        if platform is not None:
            filters.append(VideoAnalysisResult.platform == platform)
        if status_value is not None:
            filters.append(VideoAnalysisResult.status == status_value.value)
        if updated_from is not None:
            filters.append(VideoAnalysisResult.updated_time >= updated_from)
        if updated_to is not None:
            filters.append(VideoAnalysisResult.updated_time <= updated_to)
        if cursor_position is not None:
            cursor_time, cursor_id = cursor_position
            if cursor_time == _NULL_UPDATED_TIME_CURSOR_TIMESTAMP:
                filters.append(
                    and_(
                        VideoAnalysisResult.updated_time.is_(None),
                        VideoAnalysisResult.id < cursor_id,
                    )
                )
            else:
                filters.append(
                    or_(
                        VideoAnalysisResult.updated_time < cursor_time,
                        VideoAnalysisResult.updated_time.is_(None),
                        and_(
                            VideoAnalysisResult.updated_time == cursor_time,
                            VideoAnalysisResult.id < cursor_id,
                        ),
                    )
                )

        statement = (
            select(
                VideoAnalysisResult.id,
                VideoAnalysisResult.platform,
                VideoAnalysisResult.content_id,
                VideoAnalysisResult.status,
                VideoAnalysisResult.model.label("model_name"),
                VideoAnalysisResult.minio_bucket.label("storage_bucket"),
                VideoAnalysisResult.minio_object_name.label("storage_object"),
                VideoAnalysisResult.created_time,
                VideoAnalysisResult.updated_time,
                VideoAnalysisResult.error_message,
                VideoAnalysisResult.analysis_result,
                Content.pub_time.label("pub_time"),
                Content.view_count.label("view_count"),
                MaterialClean.grade_reason.label("grade_reason"),
                MaterialClean.created_time.label("material_created_time"),
            )
            .outerjoin(
                Content,
                and_(
                    Content.platform == VideoAnalysisResult.platform,
                    Content.content_id == VideoAnalysisResult.content_id,
                ),
            )
            .outerjoin(
                MaterialClean,
                and_(
                    MaterialClean.platform == VideoAnalysisResult.platform,
                    MaterialClean.content_id == VideoAnalysisResult.content_id,
                ),
            )
            .where(*filters)
            .order_by(
                VideoAnalysisResult.updated_time.desc().nulls_last(),
                VideoAnalysisResult.id.desc(),
            )
            .limit(limit + 1)
        )
        async with resources.db.asession_scope() as session:
            rows = list((await session.execute(statement)).all())

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = (
            encode_cursor(
                _ANALYSIS_LIST_CURSOR_KIND,
                page_rows[-1]._mapping["updated_time"] or _NULL_UPDATED_TIME_CURSOR_TIMESTAMP,
                page_rows[-1]._mapping["id"],
            )
            if has_more
            else None
        )
        include_score_details = detail_level == _DETAIL_LEVEL_DETAILED
        summaries = [
            _to_analysis_summary(row, include_score_details=include_score_details)
            for row in page_rows
        ]
        page_meta = PageMeta(
                has_more=has_more,
                limit=limit,
                next_cursor=next_cursor,
            ).model_dump()
        page_meta["detail_level"] = detail_level
        page_meta["operator_overview"] = _operator_overview(summaries)
        return ToolResponse(
            data=summaries,
            meta=page_meta,
        )
    except Exception as exc:
        return map_tool_error(exc, resource="analysis")


def _to_analysis_detail(
    result: VideoAnalysisResult,
    *,
    content: Content | None = None,
    video_url: str | None = None,
    video_url_expires_at: datetime | None = None,
) -> AnalysisDetail:
    analysis_result = result.analysis_result
    schema_valid = False
    schema_issues: list[AnalysisIssue] = []
    if analysis_result is not None:
        try:
            AnalysisResult.model_validate(analysis_result)
            schema_valid = True
        except ValidationError as exc:
            schema_issues = _validation_issues(exc)

    values = _summary_values(result, content=content)
    values.update(
        {
            "share_count": getattr(content, "share_count", None),
            "like_count": getattr(content, "like_count", None),
            "comment_count": getattr(content, "comment_count", None),
            "video_url": video_url,
            "video_url_available": video_url is not None,
            "video_url_expires_at": video_url_expires_at,
        }
    )
    return AnalysisDetail(
        **values,
        analysis_result=analysis_result,
        schema_valid=schema_valid,
        schema_issues=schema_issues,
    )


def _to_analysis_summary(row, *, include_score_details: bool) -> AnalysisSummary:
    return AnalysisSummary(
        **_summary_values(row._mapping, include_score_details=include_score_details)
    )


def _summary_values(
    result,
    *,
    include_score_details: bool = True,
    content: Content | None = None,
) -> dict:
    values = {
        "id": result.id,
        "platform": result.platform,
        "content_id": result.content_id,
        "status": _persisted_status(result.status),
        "model_name": result.model_name if hasattr(result, "model_name") else result.model,
        "storage_bucket": (
            result.storage_bucket if hasattr(result, "storage_bucket") else result.minio_bucket
        ),
        "storage_object": (
            result.storage_object if hasattr(result, "storage_object") else result.minio_object_name
        ),
        "created_time": result.created_time,
        "updated_time": result.updated_time,
        **_flatten_analysis_result(result.analysis_result),
        "pub_time": getattr(content, "pub_time", getattr(result, "pub_time", None)),
        "view_count": getattr(content, "view_count", getattr(result, "view_count", None)),
        "grade_reason": _truncate_error(getattr(result, "grade_reason", None)),
        "created_pub_delta_hours": _created_pub_delta_hours(result),
        "error_summary": _truncate_error(result.error_message),
    }
    values.update(_operator_summary(values, include_score_details=include_score_details))
    if not include_score_details:
        values["common_score_c"] = []
        values["specialized_score_g"] = []
        values["specialized_score_r"] = []
    return values


async def _analysis_video_url(
    resources: McpAppResources,
    result: VideoAnalysisResult,
) -> tuple[str | None, datetime | None]:
    candidates = [(result.platform, video_object_name(result.content_id))]
    fallback = (result.minio_bucket, result.minio_object_name)
    if all(fallback) and fallback not in candidates:
        candidates.append(fallback)

    expires = timedelta(minutes=resources.config.presigned_expiry_minutes)
    try:
        for bucket, object_name in candidates:
            if await resources.minio.aobject_exists(bucket, object_name):
                url = await resources.minio.apresigned_get_object(
                    bucket,
                    object_name,
                    expires=expires,
                )
                return url, datetime.now(timezone.utc) + expires
    except Exception:
        return None, None
    return None, None


def _operator_summary(values: dict[str, Any], *, include_score_details: bool) -> dict[str, Any]:
    score_rate = _score_rate(values.get("partial_points"), values.get("partial_max_points"))
    unscorable_count = sum(
        not dimension.get("scorable", False)
        for field_name in ("common_score_c", "specialized_score_g", "specialized_score_r")
        for dimension in values.get(field_name, [])
    )
    key_issues = []
    if values.get("gate_status") == "INSUFFICIENT_EVIDENCE":
        key_issues.append("证据不足")
    if unscorable_count:
        key_issues.append(f"{unscorable_count} 个评分维度不可评分")
    if values.get("status") == VideoAnalysisStatus.FAILED:
        key_issues.append("分析失败")

    return {
        "score_text": _score_text(
            values.get("partial_points"),
            values.get("partial_max_points"),
            score_rate,
        ),
        "score_rate_percent": score_rate,
        "views_text": _format_view_count(values.get("view_count")),
        "published_text": _format_published_time(values.get("pub_time")),
        "material_grade": _material_grade(values.get("grade_reason")),
        "structure_text": _structure_text(values.get("topology"), values.get("scene_count")),
        "review_status": _review_status(values),
        "key_issues": key_issues,
        "score_details_included": include_score_details,
    }


def _operator_overview(items: list[AnalysisSummary]) -> dict[str, Any]:
    score_rates = [
        item.score_rate_percent
        for item in items
        if item.score_rate_percent is not None
    ]
    view_counts = [item.view_count for item in items if item.view_count is not None]
    max_view_count = max(view_counts, default=None)
    return {
        "returned_count": len(items),
        "review_required_count": sum("复核" in item.review_status for item in items),
        "average_score_rate_percent": (
            round(sum(score_rates) / len(score_rates), 1) if score_rates else None
        ),
        "max_view_count": max_view_count,
        "max_view_count_text": _format_view_count(max_view_count),
        "display_order": _OPERATOR_DISPLAY_ORDER,
    }


def _score_rate(points: float | None, max_points: float | None) -> float | None:
    if points is None or max_points is None or max_points <= 0:
        return None
    return round(points / max_points * 100, 1)


def _score_text(
    points: float | None,
    max_points: float | None,
    score_rate: float | None,
) -> str:
    if points is None or max_points is None or score_rate is None:
        return "未评分"
    return f"{points:.1f} / {max_points:.1f}（{score_rate:.1f}%）"


def _format_view_count(view_count: int | None) -> str:
    if view_count is None:
        return "暂无数据"
    if view_count >= 100_000_000:
        return f"{view_count / 100_000_000:.1f}亿"
    if view_count >= 10_000:
        return f"{view_count / 10_000:.1f}万"
    return f"{view_count:,}"


def _format_published_time(pub_time: datetime | None) -> str:
    if pub_time is None:
        return "发布日期未知"
    utc_time = (
        pub_time.replace(tzinfo=timezone.utc)
        if pub_time.tzinfo is None
        else pub_time.astimezone(timezone.utc)
    )
    beijing_time = utc_time.astimezone(_BEIJING_TIMEZONE)
    return f"{beijing_time:%Y-%m-%d %H:%M}（北京时间）"


def _material_grade(grade_reason: str | None) -> str | None:
    if not grade_reason:
        return None
    prefix = grade_reason.replace("：", ":", 1).split(":", 1)[0].strip()
    return prefix if len(prefix) <= 10 else None


def _structure_text(topology: str | None, scene_count: int | None) -> str:
    topology_text = _TOPOLOGY_LABELS.get(topology or "", topology or "结构未知")
    if scene_count is None:
        return topology_text
    return f"{topology_text} · {scene_count} 个场景"


def _review_status(values: dict[str, Any]) -> str:
    status = values.get("status")
    if status == VideoAnalysisStatus.FAILED:
        return "分析失败"
    if status == VideoAnalysisStatus.PROCESSING:
        return "分析中"
    if values.get("gate_status") == "INSUFFICIENT_EVIDENCE":
        return "证据不足，待人工复核"
    if values.get("system_disposition") == "OWNER_REVIEW_REQUIRED" or values.get(
        "review_route"
    ):
        return "待人工复核"
    return "分析完成"


def _created_pub_delta_hours(result) -> float | None:
    """Hours between the material creation time and the content publish time."""
    material_created = getattr(result, "material_created_time", None)
    pub_time = getattr(result, "pub_time", None)
    if material_created is None or pub_time is None:
        return None
    try:
        return round((material_created - pub_time).total_seconds() / 3600, 2)
    except TypeError:
        return None


def _dimension_summary(dimension: dict | None) -> dict[str, Any]:
    if not isinstance(dimension, dict):
        return {}
    return {
        "dimension_id": dimension.get("dimension_id"),
        "name": dimension.get("name"),
        "awarded_points": dimension.get("awarded_points"),
        "max_points": dimension.get("max_points"),
        "scorable": dimension.get("scorable", False),
        "unscorable_reason": dimension.get("unscorable_reason"),
    }


def _flatten_analysis_result(raw: dict | None) -> dict[str, Any]:
    """Extract the key fields of a persisted analysis JSON for flat summaries."""
    if not raw:
        return {}
    meta = raw.get("meta") or {}
    decision = raw.get("decision") or {}
    evaluation = raw.get("evaluation") or {}
    classification = raw.get("content_classification") or {}
    technical = raw.get("technical_analysis") or {}
    evidence = raw.get("evidence_card") or {}
    common_score = (evaluation.get("common_score_c") or {}).get("dimensions") or []
    specialized_g = (evaluation.get("specialized_score_g") or {}).get("dimensions") or []
    specialized_r = (evaluation.get("specialized_score_r") or {}).get("dimensions") or []
    return {
        "schema_version": meta.get("schema_version"),
        "confidence_overall": meta.get("confidence_overall"),
        "gate_status": decision.get("gate_status"),
        "scoring_status": decision.get("scoring_status"),
        "recommended_grade": decision.get("recommended_grade"),
        "system_disposition": decision.get("system_disposition"),
        "decision_reasons": decision.get("reasons") or [],
        "review_route": evaluation.get("review_route"),
        "partial_points": evaluation.get("partial_points"),
        "partial_max_points": evaluation.get("partial_max_points"),
        "diagnostic_total": evaluation.get("diagnostic_total"),
        "primary_type": classification.get("primary_type"),
        "secondary_types": classification.get("secondary_types") or [],
        "topology": classification.get("topology"),
        "scene_count": technical.get("scene_count"),
        "cut_frequency": technical.get("cut_frequency"),
        "average_shot_duration": technical.get("average_shot_duration"),
        "evidence_complete": evidence.get("evidence_complete"),
        "sampled_frame_count": evidence.get("sampled_frame_count"),
        "common_score_c": [_dimension_summary(d) for d in common_score],
        "specialized_score_g": [_dimension_summary(d) for d in specialized_g],
        "specialized_score_r": [_dimension_summary(d) for d in specialized_r],
    }


def _persisted_status(value: str | VideoAnalysisStatus) -> VideoAnalysisStatus:
    try:
        return VideoAnalysisStatus(value)
    except ValueError as exc:
        raise McpToolError(
            ToolErrorCode.INTERNAL_ERROR,
            "Persisted analysis status is invalid.",
        ) from exc


def _validation_issues(exc: ValidationError) -> list[AnalysisIssue]:
    return [
        AnalysisIssue(
            path=".".join(str(part) for part in issue["loc"])[:256],
            message=_truncate_error(str(issue["msg"])),
        )
        for issue in exc.errors()[:_MAX_SCHEMA_ISSUES]
    ]


def _truncate_error(value: str | None) -> str | None:
    if value is None or len(value) <= _MAX_ERROR_SUMMARY_LENGTH:
        return value
    return f"{value[:_MAX_ERROR_SUMMARY_LENGTH - 3]}..."
