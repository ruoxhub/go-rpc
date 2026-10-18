import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from services.video_analysis.batch import ModelSnapshot
from services.video_analysis.repository import VideoAnalysisRepository
from storage.exceptions import SQLOperationError
from storage.sql._async import AsyncSQLImpl


@pytest_asyncio.fixture
async def repository_db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")

    schema = f"video_analysis_test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    engine = None
    schema_created = False
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        engine = create_async_engine(
            url,
            connect_args={"server_settings": {"search_path": schema}},
        )
        async with engine.begin() as connection:
            statements = [
                """
                CREATE TABLE t_llm_model (
                    id INTEGER PRIMARY KEY
                )
                """,
                """
                CREATE TABLE t_material_clean (
                    id BIGSERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    content_id VARCHAR(64) NOT NULL,
                    grade_rank INTEGER NOT NULL,
                    grade_reason TEXT,
                    grade_time TIMESTAMP NOT NULL,
                    snap_view_count BIGINT,
                    snap_pub_time TIMESTAMP,
                    snap_hours DOUBLE PRECISION,
                    clean_status VARCHAR(16) NOT NULL DEFAULT 'graded',
                    is_delete SMALLINT NOT NULL DEFAULT 0,
                    is_analysis SMALLINT NOT NULL DEFAULT 0,
                    expire_time TIMESTAMP NOT NULL,
                    created_time TIMESTAMP NOT NULL DEFAULT now(),
                    updated_time TIMESTAMP NOT NULL DEFAULT now(),
                    UNIQUE (platform, content_id)
                )
                """,
                """
                CREATE TABLE t_busi_content (
                    id BIGSERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    content_id VARCHAR(64) NOT NULL,
                    is_download BOOLEAN NOT NULL
                )
                """,
                """
                CREATE TABLE t_video_analysis_result (
                    id BIGSERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    content_id VARCHAR(64) NOT NULL,
                    minio_bucket VARCHAR(255) NOT NULL,
                    minio_object_name VARCHAR(1024),
                    status VARCHAR(16) NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    llm_model_id INTEGER REFERENCES t_llm_model(id),
                    model VARCHAR(100) NOT NULL,
                    started_time TIMESTAMP NOT NULL,
                    finished_time TIMESTAMP,
                    analysis_result JSONB,
                    error_message TEXT,
                    created_time TIMESTAMP NOT NULL DEFAULT now(),
                    updated_time TIMESTAMP NOT NULL DEFAULT now(),
                    UNIQUE (platform, content_id)
                )
                """,
            ]
            for statement in statements:
                await connection.execute(text(statement))
            await connection.execute(text("INSERT INTO t_llm_model (id) VALUES (7)"))
        yield AsyncSQLImpl(engine)
    finally:
        try:
            if engine is not None:
                await engine.dispose()
            if schema_created:
                async with admin_engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await admin_engine.dispose()


async def seed(db, content_id="video-1", *, is_analysis=0):
    now = datetime(2026, 7, 30, 9, 0)
    async with db.asession_scope() as session:
        material_id = await session.scalar(
            text(
                """
                INSERT INTO t_material_clean
                    (platform, content_id, grade_rank, grade_time,
                     clean_status, expire_time, is_analysis)
                VALUES ('tiktok', :content_id, 1, :now,
                        'downloaded', :expire_time, :is_analysis)
                RETURNING id
                """
            ),
            {
                "content_id": content_id,
                "is_analysis": is_analysis,
                "now": now,
                "expire_time": now + timedelta(days=14),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO t_busi_content
                    (platform, content_id, is_download)
                VALUES ('tiktok', :content_id, true)
                """
            ),
            {"content_id": content_id},
        )
    return material_id


class CommitBarrierDB:
    def __init__(self, engine, lock_held, release):
        self.engine = engine
        self.lock_held = lock_held
        self.release = release

    @asynccontextmanager
    async def asession_scope(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                self.lock_held.set()
                await self.release.wait()
                await session.commit()
            except Exception:
                await session.rollback()
                raise


async def scalar(db, sql, params=None):
    async with db.asession_scope() as session:
        return await session.scalar(text(sql), params or {})


def claim(repo, now, *, max_attempts=3):
    return repo.claim_batch(
        batch_size=1,
        bucket="videos",
        model=ModelSnapshot(7, "provider/qwen-vl"),
        max_attempts=max_attempts,
        now=now,
    )


@pytest.mark.asyncio
async def test_concurrent_claim_is_exclusive_and_failed_job_retries(repository_db):
    await seed(repository_db)
    repo = VideoAnalysisRepository(repository_db)
    now = datetime(2026, 7, 30, 10, 0)
    lock_held = asyncio.Event()
    release = asyncio.Event()
    first_repo = VideoAnalysisRepository(
        CommitBarrierDB(repository_db.engine, lock_held, release)
    )
    first_task = asyncio.create_task(claim(first_repo, now))
    try:
        await asyncio.wait_for(lock_held.wait(), timeout=2)
        second_claim = await asyncio.wait_for(claim(repo, now), timeout=1)
        assert second_claim == []
    finally:
        release.set()
    first_job = (await first_task)[0]

    await repo.mark_failed(
        job=first_job,
        object_name=None,
        error_message="temporary failure",
        finished_at=now + timedelta(minutes=1),
    )
    retry = await claim(repo, now + timedelta(minutes=2))

    assert len(retry) == 1
    assert retry[0].attempt_count == 2
    assert await scalar(
        repository_db, "SELECT count(*) FROM t_video_analysis_result"
    ) == 1


@pytest.mark.asyncio
async def test_completion_rolls_back_result_when_material_update_fails(repository_db):
    await seed(repository_db)
    repo = VideoAnalysisRepository(repository_db)
    now = datetime(2026, 7, 30, 10, 0)
    job = (await claim(repo, now))[0]
    wrong_material_job = type(job)(
        material_id=job.material_id + 999,
        platform=job.platform,
        content_id=job.content_id,
        attempt_count=job.attempt_count,
    )

    with pytest.raises(SQLOperationError):
        await repo.mark_succeeded(
            job=wrong_material_job,
            object_name="should-rollback.mp4",
            result={"should": "rollback"},
            finished_at=now + timedelta(minutes=1),
        )

    async with repository_db.asession_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, analysis_result
                    FROM t_video_analysis_result
                    """
                )
            )
        ).one()
    assert row == ("processing", None)


@pytest.mark.asyncio
async def test_success_persists_complete_json_and_both_states(repository_db):
    material_id = await seed(repository_db)
    repo = VideoAnalysisRepository(repository_db)
    now = datetime(2026, 7, 30, 10, 0)
    job = (await claim(repo, now))[0]
    payload = {"summary": "完整", "nested": {"score": 9}, "items": [1, 2]}

    await repo.mark_succeeded(
        job=job,
        object_name="tiktok/video-1.mp4",
        result=payload,
        finished_at=now + timedelta(minutes=1),
    )

    async with repository_db.asession_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, analysis_result, minio_object_name,
                           llm_model_id, model
                    FROM t_video_analysis_result
                    """
                )
            )
        ).mappings().one()
    assert dict(row) == {
        "status": "succeeded",
        "analysis_result": payload,
        "minio_object_name": "tiktok/video-1.mp4",
        "llm_model_id": 7,
        "model": "provider/qwen-vl",
    }
    assert await scalar(
        repository_db,
        "SELECT is_analysis FROM t_material_clean WHERE id = :id",
        {"id": material_id},
    ) == 1


@pytest.mark.asyncio
async def test_max_attempts_blocks_claim_and_stale_reap_preserves_attempt(
    repository_db,
):
    material_id = await seed(repository_db)
    repo = VideoAnalysisRepository(repository_db)
    now = datetime(2026, 7, 30, 10, 0)
    job = (await claim(repo, now, max_attempts=1))[0]

    assert (
        await repo.reap_stale(
            cutoff=now + timedelta(seconds=1),
            finished_at=now + timedelta(minutes=1),
        )
        == 1
    )
    assert await claim(repo, now + timedelta(minutes=2), max_attempts=1) == []
    async with repository_db.asession_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, attempt_count
                    FROM t_video_analysis_result
                    WHERE platform = 'tiktok' AND content_id = 'video-1'
                    """
                )
            )
        ).one()
    assert row == ("failed", job.attempt_count)
    assert await scalar(
        repository_db,
        "SELECT is_analysis FROM t_material_clean WHERE id = :id",
        {"id": material_id},
    ) == 3


@pytest.mark.asyncio
async def test_old_attempt_cannot_complete_new_attempt_and_rolls_back(
    repository_db,
):
    material_id = await seed(repository_db)
    repo = VideoAnalysisRepository(repository_db)
    now = datetime(2026, 7, 30, 10, 0)
    old_job = (await claim(repo, now))[0]
    await repo.reap_stale(
        cutoff=now + timedelta(seconds=1),
        finished_at=now + timedelta(minutes=1),
    )
    new_job = (await claim(repo, now + timedelta(minutes=2)))[0]

    with pytest.raises(SQLOperationError):
        await repo.mark_succeeded(
            job=old_job,
            object_name="old.mp4",
            result={"winner": "old"},
            finished_at=now + timedelta(minutes=3),
        )

    async with repository_db.asession_scope() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, attempt_count, analysis_result
                    FROM t_video_analysis_result
                    """
                )
            )
        ).one()
    assert row == ("processing", 2, None)
    assert await scalar(
        repository_db,
        "SELECT is_analysis FROM t_material_clean WHERE id = :id",
        {"id": material_id},
    ) == 2

    await repo.mark_succeeded(
        job=new_job,
        object_name="new.mp4",
        result={"winner": "new"},
        finished_at=now + timedelta(minutes=4),
    )
    assert await scalar(
        repository_db, "SELECT status FROM t_video_analysis_result"
    ) == "succeeded"
    assert await scalar(
        repository_db,
        "SELECT is_analysis FROM t_material_clean WHERE id = :id",
        {"id": material_id},
    ) == 1
