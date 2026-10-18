"""分析结果 MCP 适配工具的行为测试。"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from core.config import McpConfig
from mcp_adapter.context import McpAppResources
from mcp_adapter.schemas import ToolErrorCode, ToolResponse, encode_cursor
from models.analysis import VideoAnalysisResult, VideoAnalysisStatus
from models.content import Content
from models.material import MaterialClean


@compiles(JSONB, "sqlite")
def compile_jsonb_as_sqlite_json(_type, _compiler, **_kwargs):
    return "JSON"


class AnalysisDatabase:
    def __init__(self, sessions, statements):
        self._sessions = sessions
        self.statements = statements
        self.next_id = 1

    @asynccontextmanager
    async def asession_scope(self):
        async with self._sessions() as session:
            async with session.begin():
                yield session


@pytest_asyncio.fixture
async def analysis_db(tmp_path):
    public_db = tmp_path / "analysis-public.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analysis.db'}")
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public(dbapi_connection, _connection_record):
        dbapi_connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    async with engine.begin() as connection:
        updated_time_column = VideoAnalysisResult.__table__.c.updated_time
        original_nullable = updated_time_column.nullable
        updated_time_column.nullable = True
        removed_constraints = {
            c for c in VideoAnalysisResult.__table__.constraints
            if getattr(c, "name", "") in ("ck_video_analysis_status", "ck_video_analysis_migrated_terminal")
        }
        for c in removed_constraints:
            VideoAnalysisResult.__table__.constraints.remove(c)
        try:
            for table in (
                VideoAnalysisResult.__table__,
                Content.__table__,
                MaterialClean.__table__,
            ):
                await connection.run_sync(
                    lambda sync_connection, table=table: table.create(
                        sync_connection, checkfirst=True
                    )
                )
        finally:
            for c in removed_constraints:
                VideoAnalysisResult.__table__.constraints.add(c)
            updated_time_column.nullable = original_nullable

    yield AnalysisDatabase(async_sessionmaker(engine, expire_on_commit=False), statements)
    await engine.dispose()


@pytest.fixture
def resources(analysis_db):
    minio = SimpleNamespace(
        aobject_exists=AsyncMock(return_value=False),
        apresigned_get_object=AsyncMock(),
    )
    return McpAppResources(db=analysis_db, minio=minio, config=McpConfig())


async def add_analysis(
    db,
    *,
    platform: str = "tiktok",
    content_id: str,
    status: str | VideoAnalysisStatus = VideoAnalysisStatus.SUCCEEDED,
    updated_time: datetime | None = datetime(2026, 8, 6, 10, 0),
    analysis_result: dict | None = None,
    error_message: str | None = None,
    pub_time: datetime | None = None,
    view_count: int | None = None,
    share_count: int | None = None,
    like_count: int | None = None,
    comment_count: int | None = None,
    grade_reason: str | None = None,
    material_created_time: datetime | None = None,
):
    async with db.asession_scope() as session:
        event_time = updated_time or datetime(2026, 8, 6, 10, 0)
        row = VideoAnalysisResult(
            id=db.next_id,
            platform=platform,
            content_id=content_id,
            minio_bucket="analysis-assets",
            minio_object_name=f"{platform}/{content_id}.mp4",
            origin="migrated",
            status=status.value if isinstance(status, VideoAnalysisStatus) else status,
            analysis_result=analysis_result,
            error_message=error_message,
            max_attempts=3,
            model="gemini-2.5-pro",
            started_time=event_time,
            finished_time=event_time,
            created_time=event_time,
            updated_time=updated_time,
        )
        session.add(row)
        await session.flush()
        if updated_time is None:
            await session.execute(
                update(VideoAnalysisResult)
                .where(VideoAnalysisResult.id == row.id)
                .values(updated_time=None)
            )
        if any(
            value is not None
            for value in (pub_time, view_count, share_count, like_count, comment_count)
        ):
            session.add(
                Content(
                    content_id=content_id,
                    platform=platform,
                    pub_time=pub_time,
                    view_count=view_count if view_count is not None else 0,
                    share_count=share_count if share_count is not None else 0,
                    like_count=like_count if like_count is not None else 0,
                    comment_count=comment_count if comment_count is not None else 0,
                )
            )
        if grade_reason is not None or material_created_time is not None:
            session.add(
                MaterialClean(
                    id=db.next_id + 100000,
                    platform=platform,
                    content_id=content_id,
                    grade_rank=1,
                    grade_reason=grade_reason,
                    grade_time=material_created_time or event_time,
                    created_time=material_created_time,
                    updated_time=material_created_time,
                    expire_time=datetime(2099, 1, 1),
                )
            )
        db.next_id += 1
        return row.id


@pytest.mark.asyncio
async def test_get_analysis_result_uses_exact_identity_and_validates_current_schema(resources, analysis_db):
    await add_analysis(
        analysis_db,
        platform="tiktok",
        content_id="shared",
        analysis_result={
            "content_classification": {
                "primary_type": "FUNCTIONAL_PROOF",
                "topology": "ONE_TAKE",
            },
            "decision": {
                "gate_status": "INSUFFICIENT_EVIDENCE",
                "scoring_status": "UNAVAILABLE",
                "system_disposition": "OWNER_REVIEW_REQUIRED",
            },
        },
        view_count=120000,
        share_count=320,
        like_count=4800,
        comment_count=96,
    )
    await add_analysis(analysis_db, platform="youtube", content_id="shared", analysis_result=None)
    resources.minio.aobject_exists.return_value = True
    resources.minio.apresigned_get_object.return_value = "https://minio.example/shared-video"

    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "shared")

    assert isinstance(response, ToolResponse)
    assert response.data.platform == "tiktok"
    assert response.data.content_id == "shared"
    assert response.data.view_count == 120000
    assert response.data.share_count == 320
    assert response.data.like_count == 4800
    assert response.data.comment_count == 96
    assert response.data.video_url == "https://minio.example/shared-video"
    assert response.data.video_url_available is True
    assert response.data.video_url_expires_at is not None
    assert response.data.video_url_expires_at > datetime.now(timezone.utc)
    assert response.data.schema_valid is True
    assert response.data.schema_issues == []
    resources.minio.aobject_exists.assert_awaited_once_with("tiktok", "shared/video")


@pytest.mark.asyncio
async def test_get_analysis_result_falls_back_to_analysis_video_object(resources, analysis_db):
    await add_analysis(analysis_db, content_id="fallback", analysis_result={})
    resources.minio.aobject_exists.side_effect = [False, True]
    resources.minio.apresigned_get_object.return_value = "https://minio.example/fallback"

    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "fallback")

    assert response.data.video_url == "https://minio.example/fallback"
    assert response.data.video_url_available is True
    assert resources.minio.aobject_exists.await_args_list[1].args == (
        "analysis-assets",
        "tiktok/fallback.mp4",
    )
    resources.minio.apresigned_get_object.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_analysis_result_keeps_detail_when_video_is_unavailable(resources, analysis_db):
    await add_analysis(analysis_db, content_id="no-video", analysis_result={})
    resources.minio.aobject_exists.side_effect = OSError("private storage failure")

    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "no-video")

    assert response.ok is True
    assert response.data.content_id == "no-video"
    assert response.data.video_url is None
    assert response.data.video_url_available is False
    assert response.data.video_url_expires_at is None


@pytest.mark.asyncio
async def test_get_analysis_result_returns_safe_not_found_error(resources):
    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "missing")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.ANALYSIS_NOT_FOUND


@pytest.mark.asyncio
async def test_get_analysis_result_reports_empty_analysis_result_as_not_validated(resources, analysis_db):
    await add_analysis(analysis_db, content_id="empty", analysis_result=None)

    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "empty")

    assert response.data.analysis_result is None
    assert response.data.schema_valid is False
    assert response.data.schema_issues == []


@pytest.mark.asyncio
async def test_get_analysis_result_preserves_historical_json_with_bounded_schema_issues(resources, analysis_db):
    invalid_json = {"timeline": [None] * 20}
    await add_analysis(analysis_db, content_id="legacy", analysis_result=invalid_json)

    from mcp_adapter.analysis_tools import get_analysis_result

    response = await get_analysis_result(resources, "tiktok", "legacy")

    assert response.data.analysis_result == invalid_json
    assert response.data.schema_valid is False
    assert 1 <= len(response.data.schema_issues) <= 10
    assert all(len(issue.message) <= 512 for issue in response.data.schema_issues)


@pytest.mark.asyncio
async def test_list_analysis_results_filters_platform_status_and_updated_time(resources, analysis_db):
    start = datetime(2026, 8, 6, 10, 0)
    await add_analysis(analysis_db, content_id="before", updated_time=datetime(2026, 8, 6, 9, 59))
    await add_analysis(analysis_db, content_id="included", updated_time=start)
    await add_analysis(
        analysis_db,
        platform="youtube",
        content_id="other-platform",
        updated_time=datetime(2026, 8, 6, 11, 0),
    )
    await add_analysis(
        analysis_db,
        content_id="failed",
        status=VideoAnalysisStatus.FAILED,
        updated_time=datetime(2026, 8, 6, 11, 0),
    )

    from mcp_adapter.analysis_tools import list_analysis_results

    response = await list_analysis_results(
        resources,
        platform="tiktok",
        status="succeeded",
        updated_from=start,
        updated_to=datetime(2026, 8, 6, 11, 0),
    )

    assert [item.content_id for item in response.data] == ["included"]
    assert response.data[0].status == VideoAnalysisStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_list_analysis_results_rejects_unknown_status_before_query(resources, analysis_db):
    from mcp_adapter.analysis_tools import list_analysis_results

    analysis_db.statements.clear()
    response = await list_analysis_results(resources, status="invented")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.INVALID_ARGUMENT
    assert not [statement for statement in analysis_db.statements if statement.startswith("SELECT")]


@pytest.mark.asyncio
async def test_list_analysis_results_hides_invalid_persisted_status_as_internal_error(resources, analysis_db):
    await add_analysis(analysis_db, content_id="corrupt", status="unknown-status")

    from mcp_adapter.analysis_tools import list_analysis_results

    response = await list_analysis_results(resources, status="all")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.INTERNAL_ERROR
    assert "unknown-status" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_list_analysis_results_uses_keyset_pagination_with_analysis_result(resources, analysis_db):
    newest = datetime(2026, 8, 6, 12, 0)
    duplicate = datetime(2026, 8, 6, 11, 0)
    oldest = await add_analysis(analysis_db, content_id="oldest", updated_time=datetime(2026, 8, 6, 10, 0))
    second = await add_analysis(analysis_db, content_id="duplicate-low", updated_time=duplicate)
    third = await add_analysis(analysis_db, content_id="duplicate-high", updated_time=duplicate)
    fourth = await add_analysis(analysis_db, content_id="newest", updated_time=newest)
    analysis_db.statements.clear()

    from mcp_adapter.analysis_tools import list_analysis_results

    first_page = await list_analysis_results(resources, limit=2)
    second_page = await list_analysis_results(resources, limit=2, cursor=first_page.meta["next_cursor"])

    assert [item.id for item in first_page.data] == [fourth, third]
    assert [item.id for item in second_page.data] == [second, oldest]
    assert {
        key: second_page.meta[key] for key in ("has_more", "limit", "next_cursor")
    } == {"has_more": False, "limit": 2, "next_cursor": None}
    query = next(statement for statement in analysis_db.statements if statement.startswith("SELECT"))
    selected_columns = query.split("FROM", maxsplit=1)[0]
    assert "t_video_analysis_result.analysis_result" in selected_columns


@pytest.mark.asyncio
async def test_list_analysis_results_pages_from_dated_into_null_updated_time_section(resources, analysis_db):
    dated = await add_analysis(
        analysis_db,
        content_id="dated",
        updated_time=datetime(2026, 8, 6, 10, 0),
    )
    null_low_id = await add_analysis(analysis_db, content_id="null-low", updated_time=None)
    null_high_id = await add_analysis(analysis_db, content_id="null-high", updated_time=None)

    from mcp_adapter.analysis_tools import list_analysis_results

    first_page = await list_analysis_results(resources, limit=1)
    second_page = await list_analysis_results(resources, limit=1, cursor=first_page.meta["next_cursor"])
    third_page = await list_analysis_results(resources, limit=1, cursor=second_page.meta["next_cursor"])

    assert [item.id for item in first_page.data] == [dated]
    assert [item.id for item in second_page.data] == [null_high_id]
    assert [item.id for item in third_page.data] == [null_low_id]
    assert {
        key: third_page.meta[key] for key in ("has_more", "limit", "next_cursor")
    } == {"has_more": False, "limit": 1, "next_cursor": None}


@pytest.mark.asyncio
async def test_list_analysis_results_defaults_to_succeeded_and_all_opt_in(resources, analysis_db):
    await add_analysis(analysis_db, content_id="ok", status=VideoAnalysisStatus.SUCCEEDED)
    await add_analysis(analysis_db, content_id="bad", status=VideoAnalysisStatus.FAILED)

    from mcp_adapter.analysis_tools import list_analysis_results

    default_response = await list_analysis_results(resources)
    assert [item.content_id for item in default_response.data] == ["ok"]

    all_response = await list_analysis_results(resources, status="all")
    assert {item.content_id for item in all_response.data} == {"ok", "bad"}


@pytest.mark.asyncio
async def test_list_analysis_results_flattens_json_and_truncates_error_summary(resources, analysis_db):
    await add_analysis(
        analysis_db,
        content_id="flat",
        status=VideoAnalysisStatus.SUCCEEDED,
        analysis_result={
            "meta": {"schema_version": "v4.0", "confidence_overall": 0.95},
            "decision": {
                "gate_status": "INSUFFICIENT_EVIDENCE",
                "reasons": ["Evidence is incomplete"],
            },
            "evaluation": {
                "partial_points": 64.5,
                "partial_max_points": 88.0,
                "common_score_c": {
                    "dimensions": [
                        {
                            "dimension_id": "C1",
                            "name": "受众与购买需求",
                            "awarded_points": 4.5,
                            "max_points": 6.0,
                            "scorable": True,
                        }
                    ]
                },
                "specialized_score_g": {
                    "dimensions": [
                        {
                            "dimension_id": "G1",
                            "name": "商品一致性",
                            "awarded_points": None,
                            "max_points": 12.0,
                            "scorable": False,
                            "unscorable_reason": "no product reference",
                        }
                    ]
                },
            },
            "content_classification": {"primary_type": "FUNCTIONAL_PROOF"},
            "technical_analysis": {"scene_count": 1, "cut_frequency": 0.0},
        },
        pub_time=datetime(2026, 8, 5, 10, 0),
        view_count=12345,
        grade_reason="素材质量优秀",
        material_created_time=datetime(2026, 8, 6, 12, 0),
        error_message="x" * 600,
    )

    from mcp_adapter.analysis_tools import list_analysis_results

    response = await list_analysis_results(resources, detail_level="detailed")

    item = response.data[0]
    assert item.gate_status == "INSUFFICIENT_EVIDENCE"
    assert item.partial_points == 64.5
    assert item.partial_max_points == 88.0
    assert item.decision_reasons == ["Evidence is incomplete"]
    assert item.schema_version == "v4.0"
    assert item.confidence_overall == 0.95
    assert item.primary_type == "FUNCTIONAL_PROOF"
    assert item.scene_count == 1
    assert item.cut_frequency == 0.0
    assert [d.model_dump() for d in item.common_score_c] == [
        {
            "dimension_id": "C1",
            "name": "受众与购买需求",
            "awarded_points": 4.5,
            "max_points": 6.0,
            "scorable": True,
            "unscorable_reason": None,
        }
    ]
    assert [d.model_dump() for d in item.specialized_score_g] == [
        {
            "dimension_id": "G1",
            "name": "商品一致性",
            "awarded_points": None,
            "max_points": 12.0,
            "scorable": False,
            "unscorable_reason": "no product reference",
        }
    ]
    assert item.pub_time == datetime(2026, 8, 5, 10, 0)
    assert item.view_count == 12345
    assert item.grade_reason == "素材质量优秀"
    assert item.created_pub_delta_hours == 26.0
    assert "analysis_result" not in item.model_dump()
    assert item.error_summary == "x" * 509 + "..."


@pytest.mark.asyncio
async def test_list_analysis_results_builds_compact_operator_summary(resources, analysis_db):
    await add_analysis(
        analysis_db,
        content_id="operator-ready",
        analysis_result={
            "decision": {
                "gate_status": "INSUFFICIENT_EVIDENCE",
                "system_disposition": "OWNER_REVIEW_REQUIRED",
                "reasons": ["Evidence is incomplete"],
            },
            "evaluation": {
                "partial_points": 64.5,
                "partial_max_points": 88.0,
                "common_score_c": {
                    "dimensions": [
                        {
                            "dimension_id": "C1",
                            "name": "受众与购买需求",
                            "awarded_points": 4.5,
                            "max_points": 6.0,
                            "scorable": True,
                        }
                    ]
                },
                "specialized_score_g": {
                    "dimensions": [
                        {
                            "dimension_id": "G1",
                            "name": "商品一致性",
                            "awarded_points": None,
                            "max_points": 12.0,
                            "scorable": False,
                            "unscorable_reason": "no product reference",
                        }
                    ]
                },
            },
            "content_classification": {
                "primary_type": "FUNCTIONAL_PROOF",
                "topology": "MONTAGE",
            },
            "technical_analysis": {"scene_count": 4},
        },
        pub_time=datetime(2026, 8, 5, 10, 0),
        view_count=216400,
        grade_reason="P3：素材进入人工复核队列",
    )

    from mcp_adapter.analysis_tools import list_analysis_results

    response = await list_analysis_results(resources)

    item = response.data[0]
    assert item.score_text == "64.5 / 88.0（73.3%）"
    assert item.score_rate_percent == 73.3
    assert item.views_text == "21.6万"
    assert item.published_text == "2026-08-05 18:00（北京时间）"
    assert item.material_grade == "P3"
    assert item.structure_text == "多镜头剪辑 · 4 个场景"
    assert item.review_status == "证据不足，待人工复核"
    assert item.key_issues == ["证据不足", "1 个评分维度不可评分"]
    assert item.score_details_included is False
    assert item.common_score_c == []
    assert item.specialized_score_g == []
    assert response.meta["operator_overview"] == {
        "returned_count": 1,
        "review_required_count": 1,
        "average_score_rate_percent": 73.3,
        "max_view_count": 216400,
        "max_view_count_text": "21.6万",
        "display_order": [
            "score",
            "traffic",
            "published",
            "structure",
            "review",
            "issues",
        ],
    }


@pytest.mark.asyncio
async def test_list_analysis_results_detailed_mode_keeps_score_dimensions(resources, analysis_db):
    await add_analysis(
        analysis_db,
        content_id="operator-detailed",
        analysis_result={
            "evaluation": {
                "common_score_c": {
                    "dimensions": [
                        {
                            "dimension_id": "C1",
                            "name": "受众与购买需求",
                            "awarded_points": 4.5,
                            "max_points": 6.0,
                            "scorable": True,
                        }
                    ]
                }
            }
        },
    )

    from mcp_adapter.analysis_tools import list_analysis_results

    response = await list_analysis_results(resources, detail_level="detailed")

    assert response.data[0].score_details_included is True
    assert [dimension.dimension_id for dimension in response.data[0].common_score_c] == ["C1"]


@pytest.mark.asyncio
async def test_list_analysis_results_rejects_unknown_detail_level_before_query(
    resources, analysis_db
):
    from mcp_adapter.analysis_tools import list_analysis_results

    analysis_db.statements.clear()
    response = await list_analysis_results(resources, detail_level="verbose")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.INVALID_ARGUMENT
    assert not any(statement.startswith("SELECT") for statement in analysis_db.statements)
