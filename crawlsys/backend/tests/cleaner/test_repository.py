from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from cleaner.repository import CleanCursorPosition, CleanerRepository, MaterialRecord
from runtime_config.models import FilterRule


def make_db():
    db = MagicMock()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    db.asession_scope.return_value.__aenter__.return_value = session
    db.asession_scope.return_value.__aexit__.return_value = None
    return db, session


@pytest.mark.asyncio
async def test_scan_batch_uses_platform_keyset_and_stable_order():
    db, session = make_db()
    change_time = datetime(2026, 7, 27, 8, 0)
    session.execute.return_value.mappings.return_value.all.return_value = [
        {
            "id": 7,
            "content_id": "video-7",
            "platform": "tiktok",
            "pub_time": datetime(2026, 7, 27, 7, 0),
            "view_count": 8000,
            "download_time": None,
            "created_time": datetime(2026, 7, 27, 7, 1),
            "change_time": change_time,
        }
    ]

    rows = await CleanerRepository(db).scan_batch(
        "tiktok", datetime(1970, 1, 1), 0, 1000
    )

    statement = session.execute.await_args.args[0]
    sql = " ".join(str(statement).lower().split())
    params = session.execute.await_args.args[1]
    assert "platform = :platform" in sql
    assert "coalesce(updated_time, created_time) > :wm_ts" in sql
    assert "coalesce(updated_time, created_time) = :wm_ts and id > :wm_id" in sql
    assert "order by coalesce(updated_time, created_time) asc, id asc" in sql
    assert "limit :batch_size" in sql
    assert params == {
        "platform": "tiktok",
        "wm_ts": datetime(1970, 1, 1),
        "wm_id": 0,
        "batch_size": 1000,
    }
    assert rows[0].change_time == change_time
    assert rows[0].content_id == "video-7"


@pytest.mark.asyncio
async def test_scan_batch_appends_parameterized_filters():
    db, session = make_db()
    session.execute.return_value.mappings.return_value.all.return_value = []
    rules = [FilterRule(field="extend_data.aigcLabelType", operator=">", value=0)]

    await CleanerRepository(db).scan_batch(
        "tiktok", datetime(1970, 1, 1), 0, 1000, filters=rules
    )

    statement, params = session.execute.await_args.args
    sql = str(statement)
    assert "aigcLabelType" not in sql
    assert "AND (" in sql
    assert params["filter_path_0"] == ["aigcLabelType"]
    assert params["filter_value_0"] == 0


@pytest.mark.asyncio
async def test_upsert_sql_is_monotonic_and_does_not_refresh_expiry():
    db, session = make_db()
    now = datetime(2026, 7, 27, 8, 0)
    record = MaterialRecord(
        platform="tiktok",
        content_id="video-1",
        grade_rank=1,
        grade_reason="P1",
        grade_time=now,
        snap_view_count=80000,
        snap_pub_time=datetime(2026, 7, 24, 8, 0),
        snap_hours=72.0,
        clean_status="graded",
        expire_time=datetime(2026, 8, 10, 8, 0),
    )

    count = await CleanerRepository(db).upsert_materials([record])

    statement = session.execute.await_args.args[0]
    sql = " ".join(str(statement).lower().split())
    assert "(datatype, platform, content_id" in sql
    assert "('clean', :platform, :content_id" in sql
    assert "source_id" not in sql
    assert " title" not in sql
    assert " url" not in sql
    assert "least(excluded.grade_rank, t_material_clean.grade_rank)" in sql
    assert "excluded.grade_rank < t_material_clean.grade_rank" in sql
    update_clause = sql.split("do update set", 1)[1]
    assert "expire_time" not in update_clause
    assert count == 1


@pytest.mark.asyncio
async def test_empty_upsert_does_not_open_transaction():
    db, _ = make_db()

    count = await CleanerRepository(db).upsert_materials([])

    assert count == 0
    db.asession_scope.assert_not_called()


@pytest.mark.asyncio
async def test_load_cursor_defaults_to_epoch_when_missing_or_policy_changes():
    db, session = make_db()
    session.execute.return_value.mappings.return_value.one_or_none.side_effect = [
        None,
        {
            "policy_hash": "policy-v1",
            "watermark_ts": datetime(2026, 8, 9, 1, 2, 3),
            "watermark_id": 99,
        },
        {
            "policy_hash": "policy-v1",
            "watermark_ts": datetime(2026, 8, 9, 1, 2, 3),
            "watermark_id": 99,
        },
    ]
    repo = CleanerRepository(db)

    assert await repo.load_cursor("task:41", "tiktok", "policy-v1") == (
        CleanCursorPosition(datetime(1900, 1, 1), 0)
    )
    assert await repo.load_cursor("task:41", "tiktok", "policy-v2") == (
        CleanCursorPosition(datetime(1900, 1, 1), 0)
    )
    assert await repo.load_cursor("task:42", "douyin", "policy-v1") == (
        CleanCursorPosition(datetime(2026, 8, 9, 1, 2, 3), 99)
    )
    assert session.execute.await_args.args[1] == {
        "consumer_key": "task:42",
        "platform": "douyin",
    }


@pytest.mark.asyncio
async def test_commit_empty_batch_advances_cursor_without_opening_another_session():
    db, session = make_db()
    cursor = CleanCursorPosition(datetime(2026, 8, 9, 1, 2, 3), 99)

    count = await CleanerRepository(db).commit_batch(
        "task:41", "tiktok", "policy-v1", [], cursor
    )

    assert count == 0
    statement, params = session.execute.await_args.args
    sql = " ".join(str(statement).lower().split())
    assert "insert into t_video_clean_cursor" in sql
    assert "on conflict (consumer_key, platform)" in sql
    assert "t_video_clean_cursor.policy_hash <> excluded.policy_hash" in sql
    assert "(excluded.watermark_ts, excluded.watermark_id) >" in sql
    assert params == {
        "consumer_key": "task:41",
        "platform": "tiktok",
        "policy_hash": "policy-v1",
        "watermark_ts": datetime(2026, 8, 9, 1, 2, 3),
        "watermark_id": 99,
    }
    assert db.asession_scope.call_count == 1


@pytest.mark.asyncio
async def test_commit_material_and_cursor_share_one_transaction():
    db, session = make_db()
    now = datetime(2026, 8, 9, 1, 2, 3)
    row = MaterialRecord(
        platform="tiktok",
        content_id="video-1",
        grade_rank=1,
        grade_reason="P1",
        grade_time=now,
        snap_view_count=100,
        snap_pub_time=now,
        snap_hours=1.0,
        clean_status="graded",
        expire_time=now,
    )

    count = await CleanerRepository(db).commit_batch(
        "task:41", "tiktok", "policy-v1", [row], CleanCursorPosition(now, 1)
    )

    assert count == 1
    assert session.execute.await_count == 2
    assert "t_material_clean" in str(session.execute.await_args_list[0].args[0])
    assert "t_video_clean_cursor" in str(session.execute.await_args_list[1].args[0])
    assert db.asession_scope.call_count == 1


@pytest.mark.asyncio
async def test_purge_deletes_only_expired_rows():
    db, session = make_db()
    session.execute.return_value.rowcount = 3
    now = datetime(2026, 7, 27, 8, 0)

    count = await CleanerRepository(db).purge_expired(now)

    statement = session.execute.await_args.args[0]
    sql = " ".join(str(statement).lower().split())
    assert sql == "delete from t_material_clean where expire_time < :now"
    assert session.execute.await_args.args[1] == {"now": now}
    assert count == 3
