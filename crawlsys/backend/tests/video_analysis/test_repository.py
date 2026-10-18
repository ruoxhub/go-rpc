import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from api.analysis.repository import AnalysisRepository as ListAnalysisRepository
from api.analysis.repository import _item, _result_summary
from api.analysis.schemas import MaterialAnalysisListItem
from models.video_analysis import (
    AnalysisResult,
    ContentClassification,
    ContentType,
    Decision,
    EvaluationResult,
    GateStatus,
    ScoringStatus,
    SystemDisposition,
    Topology,
)
from services.video_analysis.batch import ModelSnapshot
from services.video_analysis.repository import AnalysisJob, VideoAnalysisRepository
from storage.exceptions import SQLOperationError
from storage.sql._base import convert_sql_error


class FakeResult:
    def __init__(self, *, rows=None, rowcount=0, scalar=None):
        self._rows = rows or []
        self.rowcount = rowcount
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def execute(self, statement, params=None):
        self.calls.append((statement, params))
        return self.results.pop(0)

    async def scalar(self, statement):
        self.calls.append((statement, None))
        return self.results.pop(0)._scalar


class FakeScope:
    def __init__(self, session):
        self.session = session
        self.exit_args = None
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        self.exit_args = args
        if args[0] is None:
            self.committed = True
        else:
            self.rolled_back = True
            raise convert_sql_error(args[1])


class FakeDB:
    def __init__(self, *results):
        self.session = FakeSession(results)
        self.scopes = []

    def asession_scope(self):
        scope = FakeScope(self.session)
        self.scopes.append(scope)
        return scope


def normalized(statement):
    return " ".join(str(statement).lower().split())


def _v3_result(*, total, gate_status, scoring_status):
    return AnalysisResult(
        content_classification=ContentClassification(
            primary_type=ContentType.FUNCTIONAL_PROOF,
            topology=Topology.ONE_TAKE,
        ),
        evaluation=EvaluationResult(
            partial_points=total or 0,
            partial_max_points=100,
            diagnostic_total=total,
        ),
        decision=Decision(
            gate_status=gate_status,
            scoring_status=scoring_status,
            system_disposition=(
                SystemDisposition.REJECT
                if gate_status is GateStatus.BLOCK
                else SystemDisposition.OWNER_REVIEW_REQUIRED
            ),
        ),
    ).model_dump(mode="json")


def test_analysis_list_item_exposes_versioned_summary_fields():
    fields = MaterialAnalysisListItem.model_fields

    assert {
        "schema_version",
        "overall_score",
        "gate_status",
        "scoring_status",
    } <= fields.keys()


def test_list_item_uses_the_versioned_summary_without_changing_result_json():
    payload = _v3_result(
        total=99,
        gate_status=GateStatus.BLOCK,
        scoring_status=ScoringStatus.PROVISIONAL,
    )
    original = json.loads(json.dumps(payload))
    now = datetime(2026, 8, 7)
    material = SimpleNamespace(
        platform="tiktok",
        content_id="blocked-high-score",
        is_analysis=1,
        grade_rank=1,
        grade_reason=None,
        grade_time=now,
        snap_view_count=None,
        snap_pub_time=None,
        snap_hours=None,
        clean_status="downloaded",
        expire_time=now,
        created_time=now,
        updated_time=now,
    )
    analysis = SimpleNamespace(
        llm_model_id=7,
        model="test-model",
        attempt_count=1,
        started_time=now,
        finished_time=now,
        updated_time=now,
        analysis_result=payload,
    )

    item = _item(material, analysis)

    assert item.schema_version == "v4.0"
    assert item.overall_score == 99.0
    assert item.gate_status == "BLOCK"
    assert item.scoring_status == "PROVISIONAL"
    assert payload == original


@pytest.mark.asyncio
async def test_list_repository_returns_versioned_summary_fields():
    payload = _v3_result(
        total=99,
        gate_status=GateStatus.BLOCK,
        scoring_status=ScoringStatus.PROVISIONAL,
    )
    now = datetime(2026, 8, 7)
    material = SimpleNamespace(
        platform="tiktok",
        content_id="blocked-high-score",
        is_analysis=1,
        grade_rank=1,
        grade_reason=None,
        grade_time=now,
        snap_view_count=None,
        snap_pub_time=None,
        snap_hours=None,
        clean_status="downloaded",
        expire_time=now,
        created_time=now,
        updated_time=now,
    )
    analysis = SimpleNamespace(
        llm_model_id=7,
        model="test-model",
        attempt_count=1,
        started_time=now,
        finished_time=now,
        updated_time=now,
        analysis_result=payload,
    )
    db = FakeDB(FakeResult(rows=[(material, analysis)]), FakeResult(scalar=1))

    items, total, total_pages = await ListAnalysisRepository(db).list(
        page=1,
        page_size=10,
        platform="tiktok",
        status="succeeded",
        model="test-model",
    )

    assert total == total_pages == 1
    assert len(items) == 1
    assert items[0].overall_score == 99.0
    assert items[0].gate_status == "BLOCK"


def test_result_summary_reads_latest_assembler_fields_without_inferring_gate():
    payload = _v3_result(
        total=99,
        gate_status=GateStatus.BLOCK,
        scoring_status=ScoringStatus.PROVISIONAL,
    )

    assert _result_summary(payload) == ("v4.0", 99.0, "BLOCK", "PROVISIONAL")


def test_result_summary_preserves_nullable_latest_diagnostic_total():
    payload = _v3_result(
        total=None,
        gate_status=GateStatus.INSUFFICIENT_EVIDENCE,
        scoring_status=ScoringStatus.UNAVAILABLE,
    )

    assert _result_summary(payload) == (
        "v4.0",
        None,
        "INSUFFICIENT_EVIDENCE",
        "UNAVAILABLE",
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"meta": []},
        {"meta": {"schema_version": "v4.0"}, "scoring": {"overall": {"score": 9}}},
        {"meta": {"schema_version": 3}, "scoring": {"overall": {"score": 9}}},
        {"meta": {"schema_version": "v2.0"}, "scoring": []},
        {"meta": {"schema_version": "v4.0"}, "evaluation": [], "decision": {}},
        {
            "meta": {"schema_version": "v4.0"},
            "evaluation": {},
            "decision": {"gate_status": "PASS", "scoring_status": "UNAVAILABLE"},
        },
    ],
)
def test_result_summary_fails_soft_for_malformed_or_unknown_payloads(payload):
    assert _result_summary(payload) == (None, None, None, None)


@pytest.mark.parametrize("invalid_score", [True, False, "8", float("nan"), float("inf")])
def test_result_summary_rejects_non_strict_numeric_values(invalid_score):
    payload = {"scoring": {"overall": {"score": invalid_score}}}

    assert _result_summary(payload) == (None, None, None, None)


@pytest.mark.parametrize("invalid_score", [True, "80", float("nan"), float("inf")])
def test_result_summary_rejects_non_strict_latest_diagnostic_totals(invalid_score):
    payload = _v3_result(
        total=80,
        gate_status=GateStatus.PASS,
        scoring_status=ScoringStatus.PROVISIONAL,
    )
    payload["evaluation"]["diagnostic_total"] = invalid_score

    assert _result_summary(payload) == (None, None, None, None)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("gate_status", "ALLOW"),
        ("gate_status", True),
        ("gate_status", []),
        ("scoring_status", "FINAL"),
        ("scoring_status", 1),
        ("scoring_status", {}),
    ],
)
def test_result_summary_rejects_invalid_v3_statuses(field, invalid_value):
    payload = _v3_result(
        total=80,
        gate_status=GateStatus.PASS,
        scoring_status=ScoringStatus.PROVISIONAL,
    )
    payload["decision"][field] = invalid_value

    assert _result_summary(payload) == (None, None, None, None)


@pytest.mark.asyncio
async def test_claim_batch_is_atomic_locked_and_returns_jobs():
    now = datetime(2026, 7, 30, 10, 0)
    db = FakeDB(
        FakeResult(
            rows=[
                {
                    "material_id": 19,
                    "platform": "tiktok",
                    "content_id": "v19",
                    "attempt_count": 2,
                }
            ]
        )
    )

    jobs = await VideoAnalysisRepository(db).claim_batch(
        batch_size=8,
        bucket="videos",
        model=ModelSnapshot(id=17, name="openai/qwen-vl"),
        max_attempts=3,
        now=now,
    )

    assert jobs == [AnalysisJob(19, "tiktok", "v19", 2)]
    assert len(db.scopes) == 1
    assert len(db.session.calls) == 1
    sql = normalized(db.session.calls[0][0])
    assert "with candidates as" in sql
    assert "left join t_video_analysis_result" in sql
    assert "mc.is_delete = 0" in sql
    assert "mc.clean_status = 'downloaded'" in sql
    assert "mc.is_analysis in (0, 3)" in sql
    assert "coalesce(var.attempt_count, 0) < :max_attempts" in sql
    assert "exists (" in sql
    assert "select 1 from t_busi_content" in sql
    assert "content.platform = mc.platform" in sql
    assert "content.content_id = mc.content_id" in sql
    assert "content.is_download = true" in sql
    assert "order by mc.grade_rank asc, mc.id asc" in sql
    assert "for update of mc skip locked" in sql
    assert "limit :batch_size" in sql
    assert "update t_material_clean" in sql
    assert "set is_analysis = 2" in sql
    assert "updated_time = :now" in sql
    assert "on conflict (platform, content_id) do update" in sql
    assert "attempt_count = t_video_analysis_result.attempt_count + 1" in sql
    assert "public." not in sql
    assert db.session.calls[0][1] == {
        "batch_size": 8,
        "bucket": "videos",
        "llm_model_id": 17,
        "model": "openai/qwen-vl",
        "max_attempts": 3,
        "now": now,
    }


@pytest.mark.asyncio
async def test_mark_succeeded_uses_one_transaction_and_complete_json():
    finished = datetime(2026, 7, 30, 10, 5)
    job = AnalysisJob(19, "tiktok", "v19", 2)
    payload = {"总结": "完整", "score": 9}
    db = FakeDB(FakeResult(rowcount=1), FakeResult(rowcount=1))

    await VideoAnalysisRepository(db).mark_succeeded(
        job=job,
        object_name="tiktok/v19.mp4",
        result=payload,
        finished_at=finished,
    )

    assert len(db.scopes) == 1
    result_sql = normalized(db.session.calls[0][0])
    material_sql = normalized(db.session.calls[1][0])
    assert "status = 'succeeded'" in result_sql
    assert "cast(:result as jsonb)" in result_sql
    assert "error_message = null" in result_sql
    assert "finished_time = :finished_at" in result_sql
    assert "status = 'processing'" in result_sql
    assert "attempt_count = :attempt_count" in result_sql
    assert "set is_analysis = 1" in material_sql
    assert "updated_time = :finished_at" in material_sql
    assert "id = :material_id and is_analysis = 2" in material_sql
    params = db.session.calls[0][1]
    assert params["result"] == json.dumps(payload, ensure_ascii=False)
    assert params["object_name"] == "tiktok/v19.mp4"
    assert "minio_bucket = coalesce(:bucket, minio_bucket)" in result_sql
    assert params["attempt_count"] == 2
    assert params["finished_at"] == finished
    assert db.session.calls[1][1]["finished_at"] == finished
    assert db.scopes[0].committed
    assert not db.scopes[0].rolled_back


@pytest.mark.asyncio
async def test_mark_failed_coalesces_object_and_updates_both_states():
    finished = datetime(2026, 7, 30, 10, 5)
    job = AnalysisJob(19, "tiktok", "v19", 2)
    db = FakeDB(FakeResult(rowcount=1), FakeResult(rowcount=1))

    await VideoAnalysisRepository(db).mark_failed(
        job=job,
        object_name=None,
        error_message="模型超时",
        finished_at=finished,
    )

    result_sql = normalized(db.session.calls[0][0])
    material_sql = normalized(db.session.calls[1][0])
    assert "status = 'failed'" in result_sql
    assert "minio_object_name = coalesce(:object_name, minio_object_name)" in result_sql
    assert "minio_bucket = coalesce(:bucket, minio_bucket)" in result_sql
    assert "error_message = :error_message" in result_sql
    assert "status = 'processing'" in result_sql
    assert "attempt_count = :attempt_count" in result_sql
    assert "set is_analysis = 3" in material_sql
    assert "updated_time = :finished_at" in material_sql
    assert db.session.calls[0][1]["error_message"] == "模型超时"
    assert db.session.calls[0][1]["attempt_count"] == 2


@pytest.mark.asyncio
async def test_mark_cancelled_is_atomic_and_does_not_overwrite_terminal_or_new_attempts():
    finished = datetime(2026, 7, 30, 10, 5)
    claimed = [
        AnalysisJob(19, "tiktok", "v19", 2),
        AnalysisJob(20, "tiktok", "v20", 1),
    ]
    db = FakeDB(FakeResult(scalar=1))

    count = await VideoAnalysisRepository(db).mark_cancelled(
        claimed, finished_at=finished
    )

    assert count == 1
    assert len(db.scopes) == 1
    assert len(db.session.calls) == 1
    sql = normalized(db.session.calls[0][0])
    assert "with requested as" in sql
    assert "status = 'failed'" in sql
    assert "error_message = 'analysiscancelled'" in sql
    assert "result.status = 'processing'" in sql
    assert "result.attempt_count = requested.attempt_count" in sql
    assert "set is_analysis = 3" in sql
    assert "material.is_analysis = 2" in sql
    params = db.session.calls[0][1]
    assert json.loads(params["jobs"]) == [
        {"material_id": 19, "platform": "tiktok", "content_id": "v19", "attempt_count": 2},
        {"material_id": 20, "platform": "tiktok", "content_id": "v20", "attempt_count": 1},
    ]
    assert params["finished_at"] == finished


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["mark_succeeded", "mark_failed"])
@pytest.mark.parametrize("rowcounts", [(0, 1), (1, 0)])
async def test_completion_rowcount_mismatch_raises_inside_transaction(
    method, rowcounts
):
    job = AnalysisJob(19, "tiktok", "v19", 2)
    db = FakeDB(*(FakeResult(rowcount=value) for value in rowcounts))
    repository = VideoAnalysisRepository(db)

    with pytest.raises(SQLOperationError) as exc_info:
        if method == "mark_succeeded":
            await repository.mark_succeeded(
                job=job,
                object_name="v19.mp4",
                result={"ok": True},
                finished_at=datetime(2026, 7, 30),
            )
        else:
            await repository.mark_failed(
                job=job,
                object_name="v19.mp4",
                error_message="bad",
                finished_at=datetime(2026, 7, 30),
            )

    assert db.scopes[0].exit_args[0] is SQLOperationError
    assert db.scopes[0].rolled_back
    assert not db.scopes[0].committed
    assert isinstance(exc_info.value.__cause__, SQLOperationError)
    assert "video analysis" in str(exc_info.value)


@pytest.mark.asyncio
async def test_reap_stale_is_one_cte_and_counts_stale_results():
    cutoff = datetime(2026, 7, 30, 9, 0)
    finished = datetime(2026, 7, 30, 10, 0)
    db = FakeDB(FakeResult(rowcount=1, scalar=4))

    count = await VideoAnalysisRepository(db).reap_stale(
        cutoff=cutoff,
        finished_at=finished,
    )

    assert count == 4
    assert len(db.scopes) == 1
    assert len(db.session.calls) == 1
    sql = normalized(db.session.calls[0][0])
    assert "with stale as" in sql
    assert "update t_video_analysis_result" in sql
    assert "status = 'processing'" in sql
    assert "started_time < :cutoff" in sql
    assert (
        "error_message = 'analysistimeout: processing exceeded stale timeout'"
        in sql
    )
    assert "update t_material_clean" in sql
    assert "is_analysis = 2" in sql
    assert "updated_time = :finished_at" in sql
    assert "select count(*) from stale" in sql
    assert db.session.calls[0][1] == {
        "cutoff": cutoff,
        "finished_at": finished,
    }
