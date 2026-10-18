from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from cleaner.repository import CleanerRepository, MaterialRecord
from runtime_config.models import FilterRule


@pytest.mark.asyncio
async def test_keyset_scans_3000_equal_timestamps_without_loss(cleaner_postgres_db):
    change_time = datetime(2026, 7, 27, 8, 0)
    async with cleaner_postgres_db.asession_scope() as session:
        await session.execute(
            text(
                """
                INSERT INTO t_busi_content
                  (content_id, platform, pub_time, view_count,
                   created_time, updated_time)
                SELECT
                  'video-' || n,
                  'tiktok',
                  :pub_time,
                  10000,
                  :change_time,
                  :change_time
                FROM generate_series(1, 3000) AS n
                """
            ),
            {
                "pub_time": change_time - timedelta(hours=1),
                "change_time": change_time,
            },
        )

    repo = CleanerRepository(cleaner_postgres_db)
    watermark_ts = datetime(1970, 1, 1)
    watermark_id = 0
    seen: list[int] = []
    for _ in range(3):
        rows = await repo.scan_batch(
            "tiktok", watermark_ts, watermark_id, batch_size=1000
        )
        assert len(rows) == 1000
        seen.extend(row.id for row in rows)
        watermark_ts = rows[-1].change_time
        watermark_id = rows[-1].id

    assert len(seen) == 3000
    assert len(set(seen)) == 3000
    assert await repo.scan_batch(
        "tiktok", watermark_ts, watermark_id, batch_size=1000
    ) == []


@pytest.mark.asyncio
async def test_json_numeric_filter_is_safe_and_preserves_keyset(cleaner_postgres_db):
    change_time = datetime(2026, 7, 27, 8, 0)
    values = [1, 0, -1, None, "null", '"not-a-number"', "{}", "[]", '"2.5"']
    async with cleaner_postgres_db.asession_scope() as session:
        for index, value in enumerate(values):
            extend = "{}" if value is None else '{"aigcLabelType":' + value + "}"
            await session.execute(
                text(
                    """
                    INSERT INTO t_busi_content
                      (content_id, platform, view_count, created_time, updated_time, extend)
                    VALUES (:content_id, 'tiktok', 1, :change_time, :change_time, :extend)
                    """
                ),
                {"content_id": f"filtered-{index}", "change_time": change_time, "extend": extend},
            )

    rules = [FilterRule(field="extend_data.aigcLabelType", operator=">", value=0)]
    repo = CleanerRepository(cleaner_postgres_db)
    first = await repo.scan_batch("tiktok", datetime(1970, 1, 1), 0, 1, filters=rules)
    second = await repo.scan_batch(
        "tiktok", first[-1].change_time, first[-1].id, 10, filters=rules
    )

    assert [row.content_id for row in first + second] == ["filtered-0", "filtered-8"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filter_value",
    ["2026-07-27T08:00:00Z", "2026-07-27T16:00:00+08:00"],
)
async def test_date_filter_normalizes_offsets_for_timestamp_column(
    cleaner_postgres_db, filter_value
):
    async with cleaner_postgres_db.asession_scope() as session:
        await session.execute(
            text(
                """
                INSERT INTO t_busi_content
                  (content_id, platform, pub_time, created_time, updated_time)
                VALUES ('date-match', 'tiktok', '2026-07-27 08:00:00',
                        '2026-07-27 09:00:00', '2026-07-27 09:00:00')
                """
            )
        )

    rules = [FilterRule(field="pub_time", operator="=", value=filter_value)]
    rows = await CleanerRepository(cleaner_postgres_db).scan_batch(
        "tiktok", datetime(1970, 1, 1), 0, 10, filters=rules
    )

    assert [row.content_id for row in rows] == ["date-match"]


def material(rank: int, now: datetime, views: int = 80000) -> MaterialRecord:
    return MaterialRecord(
        platform="tiktok",
        content_id="video-1",
        grade_rank=rank,
        grade_reason=f"rank-{rank}",
        grade_time=now,
        snap_view_count=views,
        snap_pub_time=now - timedelta(hours=72),
        snap_hours=72.0,
        clean_status="manual_review" if rank == -1 else "graded",
        expire_time=now + timedelta(days=14),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ranks", [(1, 3), (3, 1)])
async def test_upsert_only_promotes_grade_and_keeps_first_expiry(
    cleaner_postgres_db, ranks
):
    repo = CleanerRepository(cleaner_postgres_db)
    first_time = datetime(2026, 7, 27, 8, 0)
    second_time = first_time + timedelta(days=1)

    await repo.upsert_materials([material(ranks[0], first_time)])
    await repo.upsert_materials([material(ranks[1], second_time, views=100000)])

    async with cleaner_postgres_db.asession_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT grade_rank, grade_reason, snap_view_count, expire_time
                    FROM t_material_clean
                    WHERE platform = 'tiktok' AND content_id = 'video-1'
                    """
                )
            )
        ).mappings().one()
    assert row["grade_rank"] == 1
    assert row["snap_view_count"] == 100000
    assert row["expire_time"] == first_time + timedelta(days=14)
    expected_reason = "rank-1"
    assert row["grade_reason"] == expected_reason


@pytest.mark.asyncio
async def test_idempotent_upsert_keeps_one_row(cleaner_postgres_db):
    repo = CleanerRepository(cleaner_postgres_db)
    now = datetime(2026, 7, 27, 8, 0)

    await repo.upsert_materials([material(3, now)])
    await repo.upsert_materials([material(3, now)])

    async with cleaner_postgres_db.asession_scope() as session:
        count = await session.scalar(text("SELECT count(*) FROM t_material_clean"))
    assert count == 1


@pytest.mark.asyncio
async def test_purge_removes_only_expired_materials(cleaner_postgres_db):
    repo = CleanerRepository(cleaner_postgres_db)
    now = datetime(2026, 7, 27, 8, 0)
    expired = material(1, now - timedelta(days=15))
    active = MaterialRecord(
        **{
            **material(3, now).__dict__,
            "content_id": "video-2",
        }
    )
    await repo.upsert_materials([expired, active])

    assert await repo.purge_expired(now) == 1
    async with cleaner_postgres_db.asession_scope() as session:
        ids = (
            await session.execute(
                text("SELECT content_id FROM t_material_clean ORDER BY content_id")
            )
        ).scalars().all()
    assert ids == ["video-2"]
