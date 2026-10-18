"""Tests for TaskRepo, ActionRepo, PlatformRepo."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone

from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite

from core.param_schema import InvalidActionParamSchema
from core.repository import TaskRepo, ActionRepo, PlatformRepo
from models.task import BusTask, TaskPriority, TaskStatus, TaskTrigger
from models.action import Action
from models.platform import platformSource, PlatformStatus
from models.task_config import TaskConfig
from storage import SQLAlchemyDB


# ── helpers ──

def _mock_db():
    """Create a mock SQLAlchemyDB with asession_scope support.

    The session is a plain MagicMock. ``execute``/``flush`` are AsyncMock
    (they are real coroutine methods on AsyncSession), but their
    ``return_value`` is forced to a sync MagicMock so that sync SQLAlchemy
    Result methods (scalars / all / scalar_one_or_none) stay synchronous —
    otherwise AsyncMock's default return_value is itself async and breaks
    the sync chain.
    """
    db = MagicMock()
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock())
    mock_session.flush = AsyncMock()
    mock_session.run_sync = AsyncMock()
    db.asession_scope = MagicMock()
    db.asession_scope.return_value.__aenter__.return_value = mock_session
    db.asession_scope.return_value.__aexit__.return_value = None
    return db, mock_session


@pytest_asyncio.fixture
async def sqlite_task_db(tmp_path):
    db = SQLAlchemyDB("", "", "", 0, ":memory:", amode=True, driver="sqlite")
    public_db = tmp_path / "public.sqlite3"

    @event.listens_for(db.engine.sync_engine, "connect")
    def attach_public_schema(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    await db.aconnect()
    async with db.engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: BusTask.metadata.create_all(
                sync_connection,
                tables=[platformSource.__table__, Action.__table__, BusTask.__table__],
            )
        )
    try:
        yield db
    finally:
        await db.aclose()


# ── TaskRepo tests ──

@pytest.mark.asyncio
async def test_update_priority_uses_single_update_returning_statement():
    db, session = _mock_db()
    updated = BusTask(task_id=7, platform="test", action="search", priority=4)
    result = MagicMock()
    result.scalar_one_or_none.return_value = updated
    session.execute.return_value = result

    returned = await TaskRepo(db).update_priority(7, TaskPriority.URGENT)

    statement = session.execute.await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert returned is updated
    assert "update public.t_crawl_task" in sql
    assert "set priority=4" in sql
    assert "where public.t_crawl_task.task_id = 7" in sql
    assert "returning" in sql
    assert not sql.lstrip().startswith("select")

@pytest.mark.asyncio
async def test_get_pending_tasks_filters_status_and_next_run_time():
    db, session = _mock_db()
    session.execute.return_value.scalars.return_value.all.return_value = []

    await TaskRepo(db).get_pending_tasks("tiktok", executor="video_clean", limit=7)

    stmt = session.execute.await_args_list[0].args[0]
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "status = 'pending'" in sql
    assert "next_run_at is null" in sql
    assert "next_run_at <=" in sql
    assert "video_clean" in sql
    assert "executor" in sql
    assert "platform = 'tiktok'" in sql
    assert "limit 7" in sql
    trigger_order = sql.index("order by case")
    business_priority = sql.index("priority desc")
    due_time = sql.index("nulls first")
    task_id = sql.index("task_id asc")
    assert trigger_order < business_priority < due_time < task_id


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
async def test_get_pending_tasks_rejects_invalid_limit(limit):
    db, _session = _mock_db()

    with pytest.raises(ValueError, match="positive integer"):
        await TaskRepo(db).get_pending_tasks(limit=limit)


@pytest.mark.asyncio
async def test_get_pending_tasks_marks_claimed_rows_running():
    db, session = _mock_db()
    task = BusTask(task_id=5, platform="tiktok", action="Search")
    session.execute.return_value.scalars.return_value.all.return_value = [task]

    tasks = await TaskRepo(db).get_pending_tasks()

    assert tasks == [task]
    assert task.status == TaskStatus.RUNNING.value
    assert task.active_trigger == TaskTrigger.SCHEDULED.value  # 常规计划触发
    assert session.execute.await_count == 1  # 领取标记随事务内对象属性写入


@pytest.mark.asyncio
async def test_get_pending_tasks_keeps_legacy_platform_api():
    db, session = _mock_db()
    session.execute.return_value.scalars.return_value.all.return_value = []

    await TaskRepo(db).get_pending_tasks("tiktok")

    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "platform = 'tiktok'" in sql
    assert "rpc_crawl" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("executor", [None, "", "   "])
async def test_get_pending_tasks_normalizes_empty_executor_to_rpc_crawl(executor):
    db, session = _mock_db()
    session.execute.return_value.scalars.return_value.all.return_value = []

    await TaskRepo(db).get_pending_tasks(executor=executor)

    stmt = session.execute.await_args.args[0]
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        sql = str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True})).lower()
        assert "executor" in sql
        assert "rpc_crawl" in sql


@pytest.mark.asyncio
async def test_reclaim_stuck_running_filters_by_executor():
    db, session = _mock_db()
    session.execute.return_value.rowcount = 1

    count = await TaskRepo(db).reclaim_stuck_running(
        executor="video_clean", older_than=datetime(2026, 8, 1)
    )

    assert count == 1
    stmt = session.execute.await_args.args[0]
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        sql = str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True})).lower()
        assert "video_clean" in sql
        assert "executor" in sql


@pytest.mark.asyncio
async def test_heartbeat_running_filters_status_executor_and_platform():
    db, session = _mock_db()
    session.execute.return_value.rowcount = 1

    updated = await TaskRepo(db).heartbeat_running(
        7, executor="video_clean", platform="tiktok"
    )

    assert updated is True
    stmt = session.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(),
                           compile_kwargs={"literal_binds": True})).lower()
    assert "task_id = 7" in sql
    assert "status = 'running'" in sql
    assert "video_clean" in sql
    assert "platform = 'tiktok'" in sql
    assert "updated_at" in sql


@pytest.mark.asyncio
async def test_sqlite_claims_legacy_and_explicit_executors_in_isolation(sqlite_task_db):
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        BusTask(platform="test", action="legacy", config=None),
        BusTask(platform="test", action="empty", config={"executor": "   "}),
        BusTask(platform="test", action="clean", config=TaskConfig(executor="video_clean")),
    ])
    repo = TaskRepo(sqlite_task_db)

    clean_tasks = await repo.get_pending_tasks(executor="video_clean")
    rpc_tasks = await repo.get_pending_tasks(executor=None)

    assert [task.action for task in clean_tasks] == ["clean"]
    assert [task.action for task in rpc_tasks] == ["legacy", "empty"]


@pytest.mark.asyncio
async def test_sqlite_claims_pending_tasks_in_bounded_batches(sqlite_task_db):
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        *[
            BusTask(platform="test", action=f"action-{index}")
            for index in range(5)
        ],
    ])
    repo = TaskRepo(sqlite_task_db)

    first = await repo.get_pending_tasks(limit=2)
    second = await repo.get_pending_tasks(limit=2)
    third = await repo.get_pending_tasks(limit=2)

    assert [task.action for task in first] == ["action-0", "action-1"]
    assert [task.action for task in second] == ["action-2", "action-3"]
    assert [task.action for task in third] == ["action-4"]


@pytest.mark.asyncio
async def test_sqlite_reclaims_only_matching_executor(sqlite_task_db):
    old = datetime(2026, 7, 31)
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        BusTask(platform="test", action="legacy", status="running", config=None, updated_at=old),
        BusTask(
            platform="test", action="clean", status="running",
            config=TaskConfig(executor="video_clean"), updated_at=old,
        ),
    ])
    repo = TaskRepo(sqlite_task_db)

    reclaimed = await repo.reclaim_stuck_running(
        executor="video_clean", older_than=datetime(2026, 8, 1)
    )

    assert reclaimed == 1
    tasks = {task.action: task.status for task in await repo.find_all()}
    assert tasks == {"legacy": "running", "clean": "pending"}


@pytest.mark.asyncio
async def test_sqlite_heartbeat_updates_only_matching_running_task(sqlite_task_db):
    old = datetime(2026, 7, 31)
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        BusTask(platform="test", action="running", status="running",
                config=TaskConfig(executor="video_clean"), updated_at=old),
        BusTask(platform="test", action="done", status="done",
                config=TaskConfig(executor="video_clean"), updated_at=old),
        BusTask(platform="test", action="other", status="running",
                config=TaskConfig(executor="video_download"), updated_at=old),
    ])
    repo = TaskRepo(sqlite_task_db)
    tasks = {task.action: task for task in await repo.find_all()}

    assert await repo.heartbeat_running(
        tasks["running"].task_id, executor="video_clean", platform="test"
    )
    assert not await repo.heartbeat_running(
        tasks["done"].task_id, executor="video_clean", platform="test"
    )
    assert not await repo.heartbeat_running(
        tasks["other"].task_id, executor="video_clean", platform="test"
    )
    refreshed = {task.action: task for task in await repo.find_all()}
    assert refreshed["running"].updated_at > old
    assert refreshed["done"].updated_at == old
    assert refreshed["other"].updated_at == old


@pytest.mark.asyncio
async def test_sqlite_claim_and_reclaim_isolate_same_executor_by_platform(sqlite_task_db):
    old = datetime(2026, 7, 31)
    await sqlite_task_db.aadds([
        platformSource(bs_name="One", bs_platform_code="one"),
        platformSource(bs_name="Two", bs_platform_code="two"),
        BusTask(platform="one", action="pending", config=None),
        BusTask(platform="two", action="pending", config=None),
        BusTask(platform="one", action="running", status="running", config=None, updated_at=old),
        BusTask(platform="two", action="running", status="running", config=None, updated_at=old),
    ])
    repo = TaskRepo(sqlite_task_db)

    claimed = await repo.get_pending_tasks("one", executor="rpc_crawl")
    reclaimed = await repo.reclaim_stuck_running(
        datetime(2026, 8, 1), "one", executor="rpc_crawl"
    )

    assert [(task.platform, task.action) for task in claimed] == [("one", "pending")]
    assert reclaimed == 1
    states = {
        (task.platform, task.action): task.status for task in await repo.find_all()
    }
    assert states[("two", "pending")] == "pending"
    assert states[("two", "running")] == "running"

@pytest.mark.asyncio
async def test_find_all_returns_tasks():
    db, session = _mock_db()
    expected = [BusTask(task_id=1, platform="test", action="ping")]
    session.execute.return_value.scalars.return_value.all.return_value = expected

    repo = TaskRepo(db)
    tasks = await repo.find_all()

    assert tasks == expected


@pytest.mark.asyncio
async def test_find_all_with_platform_filter():
    db, session = _mock_db()
    session.execute.return_value.scalars.return_value.all.return_value = []

    repo = TaskRepo(db)
    await repo.find_all(platform="douyin")

    # execute called with a select statement; platform filter applied via where()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_by_id_returns_task():
    db, session = _mock_db()
    task = BusTask(task_id=42, platform="test", action="ping")
    session.execute.return_value.scalar_one_or_none.return_value = task

    repo = TaskRepo(db)
    result = await repo.find_by_id(42)

    assert result is task


@pytest.mark.asyncio
async def test_find_by_id_returns_none():
    db, session = _mock_db()
    session.execute.return_value.scalar_one_or_none.return_value = None

    repo = TaskRepo(db)
    result = await repo.find_by_id(999)

    assert result is None


@pytest.mark.asyncio
async def test_delete_executes_delete_statement():
    db, session = _mock_db()

    repo = TaskRepo(db)
    await repo.delete(42)

    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_status_updates_task():
    db, session = _mock_db()
    task = BusTask(task_id=1, status="running")
    session.execute.return_value.scalar_one_or_none.return_value = task

    repo = TaskRepo(db)
    result = await repo.set_status(1, TaskStatus.PENDING)

    assert result is True
    assert task.status == TaskStatus.PENDING.value
    assert task.error_msg is None


@pytest.mark.asyncio
async def test_set_status_not_found():
    db, session = _mock_db()
    session.execute.return_value.scalar_one_or_none.return_value = None

    repo = TaskRepo(db)
    result = await repo.set_status(999, TaskStatus.PENDING)

    assert result is False


@pytest.mark.asyncio
async def test_batch_set_status_skips_running():
    db, session = _mock_db()
    session.execute.return_value.rowcount = 1

    repo = TaskRepo(db)
    count = await repo.batch_set_status(None, TaskStatus.PAUSED, skip_running=True)

    assert count == 1
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_merge_task_skips_existing_task_deleted_during_merge(monkeypatch):
    db, session = _mock_db()
    session.execute.return_value.scalar_one_or_none.return_value = 7
    sync_session = MagicMock()
    merged = MagicMock()
    sync_session.merge.return_value = merged
    session.run_sync.side_effect = lambda fn: fn(sync_session)
    monkeypatch.setattr(
        "core.repository.inspect",
        lambda obj: MagicMock(persistent=False),
    )

    repo = TaskRepo(db)
    await repo._merge_task(BusTask(task_id=7, platform="test", action="ping"))

    sync_session.expunge.assert_called_once_with(merged)


@pytest.mark.asyncio
async def test_merge_task_allows_new_task_pending_state(monkeypatch):
    db, session = _mock_db()
    sync_session = MagicMock()
    session.run_sync.side_effect = lambda fn: fn(sync_session)
    monkeypatch.setattr(
        "core.repository.inspect",
        MagicMock(side_effect=AssertionError("new task must not inspect merge state")),
    )

    repo = TaskRepo(db)
    await repo._merge_task(BusTask(platform="test", action="ping"))

    session.execute.assert_not_awaited()
    sync_session.merge.assert_called_once()


@pytest.mark.asyncio
async def test_save_in_session_reuses_caller_transaction(monkeypatch):
    db, session = _mock_db()
    sync_session = MagicMock()
    merged = BusTask(task_id=7, platform="test", action="ping")
    sync_session.merge.return_value = merged
    session.run_sync.side_effect = lambda fn: fn(sync_session)
    session.execute.return_value.scalar_one_or_none.return_value = 7
    monkeypatch.setattr(
        "core.repository.inspect",
        lambda obj: MagicMock(persistent=True),
    )

    result = await TaskRepo(db).save_in_session(
        session,
        BusTask(task_id=7, platform="test", action="ping"),
    )

    assert result is merged
    db.asession_scope.assert_not_called()
    session.run_sync.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_keeps_legacy_session_ownership(monkeypatch):
    db, session = _mock_db()
    sync_session = MagicMock()
    merged = BusTask(platform="test", action="ping")
    sync_session.merge.return_value = merged
    session.run_sync.side_effect = lambda fn: fn(sync_session)

    result = await TaskRepo(db).save(BusTask(platform="test", action="ping"))

    assert result is merged
    db.asession_scope.assert_called_once()


# ── ActionRepo tests ──

@pytest.mark.asyncio
async def test_action_repo_find_by_platform():
    db, session = _mock_db()
    expected = [Action(ba_id=1, bs_id=5, ba_action="getUserInfo")]
    session.execute.return_value.scalars.return_value.all.return_value = expected

    repo = ActionRepo(db)
    actions = await repo.find_by_platform(5)

    assert actions == expected


@pytest.mark.asyncio
async def test_action_repo_find_by_name():
    db, session = _mock_db()
    action = Action(ba_id=1, bs_id=5, ba_action="getUserInfo")
    session.execute.return_value.scalar_one_or_none.return_value = action

    repo = ActionRepo(db)
    result = await repo.find_by_name(5, "getUserInfo")

    assert result is action


@pytest.mark.asyncio
async def test_action_repo_delete_with_unlink():
    db, session = _mock_db()

    repo = ActionRepo(db)
    await repo.delete_with_unlink(1)

    # update BusTask + delete Action → execute awaited twice, flush once
    assert session.execute.await_count == 2
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_repo_batch_update_status():
    db, session = _mock_db()
    session.execute.return_value.rowcount = 3

    repo = ActionRepo(db)
    count = await repo.batch_update_status([1, 2, 3], False)

    assert count == 3
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_repo_batch_update_status_empty():
    db, session = _mock_db()

    repo = ActionRepo(db)
    count = await repo.batch_update_status([], True)

    assert count == 0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_repo_get_schema_parses_json():
    db, session = _mock_db()
    import json
    action = Action(ba_id=1, ba_params_schema=json.dumps([{"name": "keyword"}]))
    session.execute.return_value.scalar_one_or_none.return_value = action

    repo = ActionRepo(db)
    schema = await repo.get_schema(1)

    assert schema == {
        "type": "object",
        "properties": {"keyword": {"type": "string"}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_schema",
    ["", "not-json", '{"type": "not-a-json-schema-type"}'],
)
async def test_action_repo_get_schema_rejects_corrupt_schema(stored_schema):
    db, session = _mock_db()
    action = Action(ba_id=1, ba_params_schema=stored_schema)
    session.execute.return_value.scalar_one_or_none.return_value = action

    with pytest.raises(InvalidActionParamSchema):
        await ActionRepo(db).get_schema(1)


# ── PlatformRepo tests ──

@pytest.mark.asyncio
async def test_platform_repo_find_all_active():
    db, session = _mock_db()
    expected = [platformSource(bs_id=1, bs_name="Test")]
    session.execute.return_value.scalars.return_value.all.return_value = expected

    repo = PlatformRepo(db)
    platforms = await repo.find_all_active()

    assert platforms == expected


@pytest.mark.asyncio
async def test_platform_repo_save_returns_refreshed_merged_instance():
    db, session = _mock_db()
    source = platformSource(bs_name="Test", bs_platform_code="test")
    merged = platformSource(bs_id=7, bs_name="Test", bs_platform_code="test")
    session.merge = AsyncMock(return_value=merged)
    session.refresh = AsyncMock()

    result = await PlatformRepo(db).save(source)

    assert result is merged
    session.merge.assert_awaited_once_with(source)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(merged)


@pytest.mark.asyncio
async def test_platform_repo_soft_delete():
    db, session = _mock_db()
    platform = platformSource(bs_id=1, bs_status=PlatformStatus.ENABLED)
    session.execute.return_value.scalar_one_or_none.return_value = platform

    repo = PlatformRepo(db)
    result = await repo.soft_delete(1)

    assert result is True
    assert platform.bs_status == PlatformStatus.DELETED


@pytest.mark.asyncio
async def test_platform_repo_restore():
    db, session = _mock_db()
    platform = platformSource(bs_id=1, bs_status=PlatformStatus.DELETED)
    session.execute.return_value.scalar_one_or_none.return_value = platform

    repo = PlatformRepo(db)
    result = await repo.restore(1)

    assert result is True
    assert platform.bs_status == PlatformStatus.ENABLED

# ���� TaskRepo recompute_cron_schedules tests ����

@pytest.mark.asyncio
async def test_recompute_cron_schedules_updates_pending_and_paused(sqlite_task_db):
    now = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        BusTask(
            platform="test", action="cron-a", schedule_type="cron",
            cron_expression="0 3 * * *", status=TaskStatus.PENDING, next_run_at=None,
        ),
        BusTask(
            platform="test", action="cron-b", schedule_type="cron",
            cron_expression="0 4 * * *", status=TaskStatus.PAUSED, next_run_at=None,
            run_now_requested_at=now,
        ),
        BusTask(
            platform="test", action="cron-c", schedule_type="cron",
            cron_expression="0 5 * * *", status=TaskStatus.RUNNING, next_run_at=now,
        ),
        BusTask(platform="test", action="manual-a", status=TaskStatus.PENDING, next_run_at=None),
    ])
    repo = TaskRepo(sqlite_task_db)

    updated = await repo.recompute_cron_schedules(
        timezone_name="Asia/Shanghai", now=now
    )

    assert updated == 2  # pending + paused; running 与 manual 不重算
    reloaded = await repo.find_all()
    by_action = {t.action: t for t in reloaded}
    assert by_action["cron-a"].next_run_at.replace(tzinfo=None) == datetime(2026, 8, 10, 19, 0, 0)
    assert by_action["cron-b"].next_run_at.replace(tzinfo=None) == datetime(2026, 8, 10, 20, 0, 0)
    assert by_action["cron-b"].run_now_requested_at is None  # 暂停期间遗留合并请求被清除
    assert by_action["cron-c"].next_run_at.replace(tzinfo=None) == now.replace(tzinfo=None)  # running 保持本轮时间
    assert by_action["manual-a"].next_run_at is None

# ���� Task 5: 原子领取与任务操作 ����

@pytest.mark.asyncio
async def test_sqlite_claim_prefers_retry_then_manual_and_persists_trigger(sqlite_task_db):
    retry = BusTask(
        platform="test", action="retry", status=TaskStatus.PENDING,
        priority=TaskPriority.LOWEST,
        next_retry_at=datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc),
        run_now_requested_at=datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc),
    )
    manual = BusTask(
        platform="test", action="manual", status=TaskStatus.PENDING,
        priority=TaskPriority.URGENT,
        run_now_requested_at=datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc),
    )
    scheduled = BusTask(
        platform="test", action="scheduled", status=TaskStatus.PENDING,
        priority=TaskPriority.URGENT,
        next_run_at=datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        retry, manual, scheduled,
    ])
    repo = TaskRepo(sqlite_task_db)

    claimed = await repo.get_pending_tasks(limit=3)
    by_action = {t.action: t for t in claimed}

    # 重试 > 立即执行 > 常规计划
    assert [t.action for t in claimed] == ["retry", "manual", "scheduled"]
    assert by_action["retry"].active_trigger == "retry"
    assert by_action["retry"].next_retry_at is None  # 只消费本次对应请求字段
    assert by_action["manual"].active_trigger == "manual"
    assert by_action["manual"].run_now_requested_at is None
    assert by_action["manual"].active_scheduled_at is not None
    assert by_action["scheduled"].active_trigger == "scheduled"
    assert all(t.status == TaskStatus.RUNNING.value for t in claimed)


@pytest.mark.asyncio
async def test_sqlite_claim_orders_same_trigger_rank_by_trigger_time(sqlite_task_db):
    now = datetime.now(timezone.utc)
    later = BusTask(
        platform="test", action="later", status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        next_retry_at=now - timedelta(hours=1),
    )
    earlier = BusTask(
        platform="test", action="earlier", status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        next_retry_at=now - timedelta(hours=2),
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        later, earlier,
    ])

    claimed = await TaskRepo(sqlite_task_db).get_pending_tasks(limit=2)

    assert [task.action for task in claimed] == ["earlier", "later"]


@pytest.mark.asyncio
async def test_sqlite_claim_orders_high_business_priority_first(sqlite_task_db):
    due = datetime.now(timezone.utc) - timedelta(hours=1)
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        BusTask(
            platform="test",
            action="normal",
            priority=TaskPriority.NORMAL,
            next_retry_at=due,
        ),
        BusTask(
            platform="test",
            action="urgent",
            priority=TaskPriority.URGENT,
            next_retry_at=due,
        ),
    ])

    claimed = await TaskRepo(sqlite_task_db).get_pending_tasks(limit=2)

    assert [task.action for task in claimed] == ["urgent", "normal"]


@pytest.mark.asyncio
async def test_init_tasks_uses_normal_priority_default():
    repo = TaskRepo(MagicMock())
    repo._get_existing_actions = AsyncMock(return_value=set())
    repo._insert_tasks = AsyncMock()

    await repo.init_tasks("test", [{"action": "search"}])

    inserted = repo._insert_tasks.await_args.args[0]
    assert len(inserted) == 1
    assert inserted[0].priority == TaskPriority.NORMAL.db_value


@pytest.mark.asyncio
async def test_sqlite_reclaimed_tasks_keep_original_trigger(sqlite_task_db):
    scheduled_at = datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)
    manual = BusTask(
        platform="test", action="manual-zombie", status=TaskStatus.RUNNING,
        active_trigger="manual", active_scheduled_at=scheduled_at,
    )
    retry = BusTask(
        platform="test", action="retry-zombie", status=TaskStatus.RUNNING,
        active_trigger="retry", active_scheduled_at=scheduled_at,
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        manual, retry,
    ])
    repo = TaskRepo(sqlite_task_db)

    assert await repo.reclaim_stuck_running(
        datetime.now(timezone.utc) + timedelta(days=1)
    ) == 2
    claimed = await repo.get_pending_tasks(limit=2)

    assert {task.action: task.active_trigger for task in claimed} == {
        "manual-zombie": "manual",
        "retry-zombie": "retry",
    }


@pytest.mark.asyncio
async def test_sqlite_repeated_run_now_requests_coalesce(sqlite_task_db):
    running = BusTask(
        platform="test",
        action="running",
        status=TaskStatus.RUNNING,
        priority=TaskPriority.LOW,
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        running,
    ])
    repo = TaskRepo(sqlite_task_db)

    assert await repo.request_run_now(running.task_id)
    requested = await repo.find_by_id(running.task_id)
    first = requested.run_now_requested_at
    assert first is not None
    assert requested.priority == 1
    assert await repo.request_run_now(running.task_id)
    requested = await repo.find_by_id(running.task_id)
    assert requested.run_now_requested_at == first  # 幂等：不覆盖已排队请求
    assert requested.priority == 1


@pytest.mark.asyncio
async def test_sqlite_request_run_now_misses_task_and_limit(sqlite_task_db):
    at_limit = BusTask(
        platform="test", action="limit", status=TaskStatus.PENDING,
        max_runs=1, run_count=1,
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        at_limit,
    ])
    repo = TaskRepo(sqlite_task_db)

    assert await repo.request_run_now(99999) is False  # 不存在
    assert await repo.request_run_now(at_limit.task_id) is False  # 已达 max_runs


@pytest.mark.asyncio
async def test_sqlite_request_run_now_rejects_expired_task(sqlite_task_db):
    expired = BusTask(
        platform="test", action="expired", status=TaskStatus.PENDING,
        schedule_end_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        expired,
    ])

    assert await TaskRepo(sqlite_task_db).request_run_now(expired.task_id) is False


@pytest.mark.asyncio
async def test_sqlite_pause_and_resume_lifecycle(sqlite_task_db):
    running = BusTask(platform="test", action="running", status=TaskStatus.RUNNING)
    waiting = BusTask(platform="test", action="waiting", status=TaskStatus.PENDING)
    await sqlite_task_db.aadds([
        platformSource(bs_name="Test", bs_platform_code="test"),
        running, waiting,
    ])
    repo = TaskRepo(sqlite_task_db)

    assert await repo.pause(running.task_id)
    run_after = await repo.find_by_id(running.task_id)
    assert run_after.pause_requested is True  # running: 本轮结束后暂停
    assert run_after.status == TaskStatus.RUNNING.value

    assert await repo.pause(waiting.task_id)
    assert (await repo.find_by_id(waiting.task_id)).status == TaskStatus.PAUSED.value  # 其他状态直接暂停

    assert await repo.resume(running.task_id, next_run_at=None)
    run_after = await repo.find_by_id(running.task_id)
    assert run_after.pause_requested is False
    assert run_after.status == TaskStatus.RUNNING.value  # 取消运行中暂停，不创建并行轮次

    resumed_at = datetime(2026, 8, 10, 6, 0, 0, tzinfo=timezone.utc)
    assert await repo.resume(waiting.task_id, next_run_at=resumed_at)
    run_after = await repo.find_by_id(waiting.task_id)
    assert run_after.run_now_requested_at is None
    assert run_after.status == TaskStatus.PENDING.value
    assert run_after.next_run_at.replace(tzinfo=None) == resumed_at.replace(tzinfo=None)
