import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cleaner.download_repository import VideoDownloadRepository


NOW = datetime(2026, 8, 9, 12, 0)


@pytest_asyncio.fixture
async def postgres_repo(cleaner_postgres_db):
    async with cleaner_postgres_db.asession_scope() as session:
        await session.execute(text("""
            ALTER TABLE t_busi_content
            ADD COLUMN pic TEXT,
            ADD COLUMN is_download BOOLEAN NOT NULL DEFAULT false
        """))
        await session.execute(text("""
            ALTER TABLE t_material_clean
            ADD COLUMN download_claim_token VARCHAR(64),
            ADD COLUMN download_claimed_at TIMESTAMP,
            ADD COLUMN download_attempt_count INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN download_next_retry_at TIMESTAMP,
            ADD COLUMN download_last_error TEXT
        """))
    return VideoDownloadRepository(cleaner_postgres_db)


async def seed(repo, content_id: str, *, extend: str | None = None):
    extend = extend or (
        '{"video_url":"https://cdn/video.mp4",'
        '"music_url":"https://cdn/music.mp3",'
        '"pic_url":"https://cdn/cover.jpg"}'
    )
    async with repo._db.asession_scope() as session:
        material_id = await session.scalar(text("""
            INSERT INTO t_material_clean
                (platform, content_id, grade_rank, grade_time, clean_status, expire_time)
            VALUES ('tiktok', :content_id, 1, :now, 'graded', :expire_time)
            RETURNING id
        """), {
            "content_id": content_id,
            "now": NOW,
            "expire_time": NOW + timedelta(days=14),
        })
        await session.execute(text("""
            INSERT INTO t_busi_content
                (platform, content_id, extend, pic, is_download)
            VALUES ('tiktok', :content_id, :extend, NULL, false)
        """), {"content_id": content_id, "extend": extend})
    return material_id


def claim(repo, token: str, *, now=NOW, stale_before=None, max_attempts=5, size=1):
    return repo.claim_batch(
        min_grade=3,
        batch_size=size,
        platform=None,
        offset=0,
        claim_token=token,
        now=now,
        stale_before=stale_before or now - timedelta(minutes=30),
        max_attempts=max_attempts,
    )


class CommitBarrierDB:
    def __init__(self, engine, transaction_ready, release):
        self.engine = engine
        self.transaction_ready = transaction_ready
        self.release = release

    @asynccontextmanager
    async def asession_scope(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                self.transaction_ready.set()
                await self.release.wait()
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@pytest.mark.asyncio
async def test_concurrent_claims_are_disjoint(postgres_repo):
    for index in range(4):
        await seed(postgres_repo, f"video-{index}")

    transaction_ready = asyncio.Event()
    release = asyncio.Event()
    first_repo = VideoDownloadRepository(CommitBarrierDB(
        postgres_repo._db.engine, transaction_ready, release
    ))
    first_task = asyncio.create_task(claim(first_repo, "batch-a", size=2))
    try:
        await asyncio.wait_for(transaction_ready.wait(), timeout=2)
        second = await asyncio.wait_for(
            claim(postgres_repo, "batch-b", size=2), timeout=1
        )
    finally:
        release.set()
    first = await first_task

    assert len(first) == len(second) == 2
    assert {job.material_id for job in first}.isdisjoint(
        {job.material_id for job in second}
    )


@pytest.mark.asyncio
async def test_stale_owner_cannot_finish_reclaimed_job(postgres_repo):
    await seed(postgres_repo, "video-1")
    old_job = (await claim(
        postgres_repo,
        "old-owner",
        now=NOW - timedelta(hours=1),
        stale_before=NOW - timedelta(hours=2),
    ))[0]

    new_job = (await claim(
        postgres_repo,
        "new-owner",
        stale_before=NOW - timedelta(minutes=30),
    ))[0]

    assert new_job.claim_token == "new-owner"
    assert new_job.attempt_count == 2
    assert await postgres_repo.mark_succeeded(old_job) is False
    assert await postgres_repo.mark_failed(
        old_job, "late failure", NOW, max_attempts=5
    ) is False
    assert await postgres_repo.release_claim(old_job) is False
    assert await postgres_repo.mark_succeeded(new_job) is True
    async with postgres_repo._db.asession_scope() as session:
        material = (await session.execute(text("""
            SELECT clean_status, download_claim_token, download_claimed_at
            FROM t_material_clean WHERE id = :id
        """), {"id": new_job.material_id})).one()
        content_downloaded = await session.scalar(text("""
            SELECT is_download FROM t_busi_content
            WHERE platform = :platform AND content_id = :content_id
        """), {"platform": new_job.platform, "content_id": new_job.content_id})
    assert material == ("downloaded", None, None)
    assert content_downloaded is True


@pytest.mark.asyncio
async def test_failed_job_waits_until_next_retry(postgres_repo):
    await seed(postgres_repo, "video-1")
    job = (await claim(postgres_repo, "first"))[0]
    retry_at = NOW + timedelta(minutes=5)

    assert await postgres_repo.mark_failed(
        job, "timeout", retry_at, max_attempts=5
    ) is True
    async with postgres_repo._db.asession_scope() as session:
        failed = (await session.execute(text("""
            SELECT download_claim_token, download_claimed_at,
                   download_attempt_count, download_next_retry_at,
                   download_last_error
            FROM t_material_clean WHERE id = :id
        """), {"id": job.material_id})).one()
    assert failed == (None, None, 1, retry_at, "timeout")
    assert await claim(postgres_repo, "early", now=NOW) == []
    retried = await claim(postgres_repo, "retry", now=retry_at)
    assert retried[0].attempt_count == 2


@pytest.mark.asyncio
async def test_active_lease_is_not_reclaimed_and_permanent_failure_exhausts_attempts(
    postgres_repo,
):
    await seed(postgres_repo, "video-1")
    job = (await claim(postgres_repo, "owner"))[0]

    assert await claim(postgres_repo, "other", now=NOW + timedelta(minutes=1)) == []
    assert await postgres_repo.mark_failed(
        job, "invalid input", None, max_attempts=5, permanent=True
    ) is True
    async with postgres_repo._db.asession_scope() as session:
        attempt_count, retry_at = (await session.execute(text("""
            SELECT download_attempt_count, download_next_retry_at
            FROM t_material_clean WHERE id = :id
        """), {"id": job.material_id})).one()
    assert (attempt_count, retry_at) == (5, None)
    assert await claim(
        postgres_repo,
        "future",
        now=NOW + timedelta(days=1),
        max_attempts=5,
    ) == []


@pytest.mark.asyncio
async def test_invalid_input_is_claimed_and_can_be_released(postgres_repo):
    await seed(postgres_repo, "video-1", extend="not-json")

    job = (await claim(postgres_repo, "owner"))[0]

    assert job.candidate is None
    assert job.input_error is not None
    assert await postgres_repo.release_claim(job) is True
    async with postgres_repo._db.asession_scope() as session:
        released = (await session.execute(text("""
            SELECT download_claim_token, download_claimed_at,
                   download_attempt_count
            FROM t_material_clean WHERE id = :id
        """), {"id": job.material_id})).one()
    assert released == (None, None, 1)
    assert (await claim(postgres_repo, "next"))[0].attempt_count == 2
