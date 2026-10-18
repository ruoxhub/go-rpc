import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.repository import TaskRepo
from models.action import Action
from models.platform import platformSource
from models.task import BusTask, TaskPriority, TaskStatus
from storage.sql._async import AsyncSQLImpl


@pytest_asyncio.fixture
async def task_db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")

    schema = f"task_priority_test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    engine = None
    schema_created = False
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True
        engine = create_async_engine(
            url,
            execution_options={"schema_translate_map": {"public": schema}},
        )
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: BusTask.metadata.create_all(
                    sync_connection,
                    tables=[
                        platformSource.__table__,
                        Action.__table__,
                        BusTask.__table__,
                    ],
                )
            )
        yield AsyncSQLImpl(engine)
    finally:
        try:
            if engine is not None:
                await engine.dispose()
            if schema_created:
                async with admin_engine.begin() as connection:
                    await connection.execute(
                        text(f'DROP SCHEMA "{schema}" CASCADE')
                    )
        finally:
            await admin_engine.dispose()


class CommitBarrierDB:
    def __init__(self, engine, lock_held: asyncio.Event, release: asyncio.Event):
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


async def seed_pending_tasks(task_db, *tasks):
    await task_db.aadd(
        platformSource(bs_name="Test", bs_platform_code="test")
    )
    rows = [
        BusTask(platform="test", action=action, priority=priority)
        for action, priority in tasks
    ]
    await task_db.aadds(rows)
    return tuple(rows)


@pytest.mark.asyncio
async def test_patch_lock_makes_worker_skip_then_future_claim_uses_new_priority(task_db):
    patched, fallback = await seed_pending_tasks(
        task_db,
        ("patched", TaskPriority.NORMAL),
        ("fallback", TaskPriority.LOW),
    )
    lock_held = asyncio.Event()
    release = asyncio.Event()
    patch_repo = TaskRepo(CommitBarrierDB(task_db.engine, lock_held, release))
    patch_task = asyncio.create_task(
        patch_repo.update_priority(patched.task_id, TaskPriority.URGENT)
    )
    try:
        await asyncio.wait_for(lock_held.wait(), timeout=2)

        claimed = await asyncio.wait_for(
            TaskRepo(task_db).get_pending_tasks(limit=1),
            timeout=1,
        )
        assert [task.task_id for task in claimed] == [fallback.task_id]
    finally:
        release.set()

    updated = await asyncio.wait_for(patch_task, timeout=2)
    assert updated is not None
    assert updated.priority == TaskPriority.URGENT.db_value

    next_claim = await TaskRepo(task_db).get_pending_tasks(limit=1)
    assert [task.task_id for task in next_claim] == [patched.task_id]


@pytest.mark.asyncio
async def test_worker_lock_fixes_current_run_and_patch_waits_for_future_round(task_db):
    (task,) = await seed_pending_tasks(
        task_db,
        ("worker-first", TaskPriority.NORMAL),
    )
    lock_held = asyncio.Event()
    release = asyncio.Event()
    worker_repo = TaskRepo(CommitBarrierDB(task_db.engine, lock_held, release))
    worker_task = asyncio.create_task(worker_repo.get_pending_tasks(limit=1))
    await asyncio.wait_for(lock_held.wait(), timeout=2)

    patch_task = asyncio.create_task(
        TaskRepo(task_db).update_priority(task.task_id, TaskPriority.URGENT)
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(asyncio.shield(patch_task), timeout=0.2)

    release.set()
    claimed = await asyncio.wait_for(worker_task, timeout=2)
    updated = await asyncio.wait_for(patch_task, timeout=2)

    assert [item.task_id for item in claimed] == [task.task_id]
    assert claimed[0].priority == TaskPriority.NORMAL.db_value
    assert claimed[0].status == TaskStatus.RUNNING.value
    assert claimed[0].updated_at.tzinfo is None
    assert updated is not None
    assert updated.priority == TaskPriority.URGENT.db_value
    assert updated.status == TaskStatus.RUNNING.value
