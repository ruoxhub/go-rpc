from __future__ import annotations

import asyncio
import os
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Table, delete, event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from models.action import Action
from models.action_parser import ActionParserRevision, ActionParserRevisionSample, ActionParserSample
from models.platform import platformSource
from models.task import BusTask
from services.parser_configuration.repository import ActionParserRepository
from services.parser_configuration.errors import ParserConfigurationError
from storage import SQLAlchemyDB


@pytest_asyncio.fixture
async def db(tmp_path):
    database = SQLAlchemyDB("", "", "", 0, ":memory:", amode=True, driver="sqlite")
    engine = database.engine
    assert isinstance(engine, AsyncEngine)
    public_db = tmp_path / "public.sqlite3"

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public_schema(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    await database.aconnect()
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Action.metadata.create_all(
                sync_connection,
                tables=[
                    cast(Table, platformSource.__table__),
                    cast(Table, Action.__table__),
                    cast(Table, BusTask.__table__),
                    cast(Table, ActionParserSample.__table__),
                    cast(Table, ActionParserRevision.__table__),
                    cast(Table, ActionParserRevisionSample.__table__),
                ],
            )
        )
    try:
        yield database
    finally:
        await database.aclose()


async def seed_action(db):
    async with db.asession_scope() as session:
        platform = platformSource(bs_name="test", bs_platform_code=f"test-{uuid4().hex}")
        session.add(platform)
        await session.flush()
        action = Action(
            bs_id=platform.bs_id,
            ba_action="detail",
            ba_params_schema='{"type":"object"}',
            ba_sample_safe=True,
        )
        session.add(action)
        await session.flush()
        return action, platform


def new_sample(ba_id, *, suffix="one"):
    return ActionParserSample(
        ba_id=ba_id,
        request_params_redacted={"token": "<redacted:token>"},
        request_params_hmac_sha256="b" * 64,
        request_hmac_key_version="v1",
        raw_object_key=f"raw/{suffix}",
        redacted_object_key=f"redacted/{suffix}",
        response_sha256="a" * 64,
        response_bytes=2,
        sanitizer_version="v1",
        rpc_duration_ms=1,
    )


@pytest.mark.asyncio
async def test_action_context_and_sample_crud_are_scoped_by_action(db):
    action, platform = await seed_action(db)
    repository = ActionParserRepository(db)
    context = await repository.require_action_context(action.ba_id)
    assert (context.platform, context.action, context.sample_safe) == (
        platform.bs_platform_code,
        "detail",
        True,
    )

    sample = await repository.create_sample(new_sample(action.ba_id))
    assert await repository.get_sample(action.ba_id, sample.sample_id) is not None
    assert [item.sample_id for item in await repository.list_samples(action.ba_id, 0, 10)] == [sample.sample_id]
    assert await repository.sample_reference_count(sample.sample_id) == 0
    await repository.delete_sample_metadata(action.ba_id, sample.sample_id)
    assert await repository.list_samples(action.ba_id, 0, 10) == []


@pytest.mark.asyncio
async def test_delete_sample_keeps_metadata_when_object_delete_fails(db):
    action, _platform = await seed_action(db)
    repository = ActionParserRepository(db)
    sample = await repository.create_sample(new_sample(action.ba_id))

    async def fail_delete(_sample):
        raise ParserConfigurationError("sample_storage_failed", "stable failure")

    with pytest.raises(ParserConfigurationError) as caught:
        await repository.delete_sample(
            action.ba_id, sample.sample_id, delete_objects=fail_delete
        )
    assert caught.value.code == "sample_storage_failed"
    assert await repository.get_sample(action.ba_id, sample.sample_id) is not None


@pytest.mark.asyncio
async def test_restore_rejects_revision_from_another_action_without_creating_draft(db):
    first, _first_platform = await seed_action(db)
    second, _second_platform = await seed_action(db)
    repository = ActionParserRepository(db)
    async with db.asession_scope() as session:
        archived = ActionParserRevision(
            ba_id=second.ba_id,
            revision_no=1,
            status="archived",
            definition={"schema_version": 1, "output": {"mode": "json"}, "fields": [{"target": "/id", "source": "/id"}]},
            definition_sha256="c" * 64,
            source="manual",
        )
        session.add(archived)
        await session.flush()
        archived_id = archived.revision_id

    with pytest.raises(ParserConfigurationError) as caught:
        await repository.restore_as_draft(archived_id, ba_id=first.ba_id)
    assert caught.value.code == "invalid_revision_transition"
    async with db.asession_scope() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ActionParserRevision)
            .where(ActionParserRevision.ba_id == second.ba_id)
        )
    assert count == 1


@pytest.mark.asyncio
async def test_require_samples_preserves_requested_order_and_rejects_foreign_samples(db):
    action, platform = await seed_action(db)
    other, _other_platform = await seed_action(db)
    repository = ActionParserRepository(db)
    first = await repository.create_sample(new_sample(action.ba_id, suffix="first"))
    second = await repository.create_sample(new_sample(action.ba_id, suffix="second"))
    foreign = await repository.create_sample(new_sample(other.ba_id, suffix="foreign"))
    result = await repository.require_samples(action.ba_id, [second.sample_id, first.sample_id])
    assert [item.sample_id for item in result] == [second.sample_id, first.sample_id]
    with pytest.raises(Exception) as caught:
        await repository.require_samples(action.ba_id, [foreign.sample_id])
    assert getattr(caught.value, "code", None) == "sample_not_found"


@pytest.mark.asyncio
async def test_delete_action_configuration_clears_references_before_rows(db):
    action, platform = await seed_action(db)
    repository = ActionParserRepository(db)
    sample = await repository.create_sample(new_sample(action.ba_id))
    async with db.asession_scope() as session:
        revision = ActionParserRevision(
            ba_id=action.ba_id,
            revision_no=1,
            status="draft",
            definition={"schema_version": 1, "output": {"mode": "json"}, "fields": [{"target": "/id", "source": "/id"}]},
            definition_sha256="c" * 64,
            source="manual",
            source_sample_id=sample.sample_id,
        )
        session.add(revision)
        await session.flush()
        session.add(ActionParserRevisionSample(revision_id=revision.revision_id, sample_id=sample.sample_id, sample_sha256=sample.response_sha256))
        task = BusTask(
            ba_id=action.ba_id,
            platform=platform.bs_platform_code,
            action="detail",
        )
        session.add(task)

    deleted_objects = []

    async def delete_objects(item):
        deleted_objects.append((item.raw_object_key, item.redacted_object_key))

    await repository.delete_action_configuration(
        action.ba_id, delete_objects=delete_objects
    )

    async with db.asession_scope() as session:
        assert deleted_objects == [(sample.raw_object_key, sample.redacted_object_key)]
        assert await session.get(Action, action.ba_id) is None
        assert await session.get(ActionParserSample, sample.sample_id) is None
        assert (await session.execute(select(BusTask.ba_id))).scalar_one() is None


def postgres_db_or_skip():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL concurrency test")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")
    parsed = make_url(url)
    return SQLAlchemyDB(
        parsed.username or "",
        parsed.password or "",
        parsed.host or "",
        parsed.port or 5432,
        parsed.database or "",
        amode=True,
        driver="postgresql",
    )


@pytest.mark.asyncio
async def test_postgres_delete_sample_blocks_concurrent_preview_until_metadata_is_deleted():
    postgres_db = postgres_db_or_skip()
    action, _platform = await seed_action(postgres_db)
    repository = ActionParserRepository(postgres_db)
    sample = await repository.create_sample(new_sample(action.ba_id, suffix=uuid4().hex))
    definition = {"schema_version": 1, "output": {"mode": "json"}, "fields": [{"target": "/id", "source": "/id"}]}
    revision = await repository.create_draft(action.ba_id, definition=definition)
    deleting = asyncio.Event()
    release_delete = asyncio.Event()

    async def paused_delete(_sample):
        deleting.set()
        await release_delete.wait()

    delete_task = asyncio.create_task(
        repository.delete_sample(
            action.ba_id, sample.sample_id, delete_objects=paused_delete
        )
    )
    save_task = None
    try:
        await asyncio.wait_for(deleting.wait(), timeout=5)
        report = {
            "passed": True,
            "definition_sha256": revision.definition_sha256,
            "sample_ids": [sample.sample_id],
        }
        save_task = asyncio.create_task(
            repository.save_preview(
                revision.revision_id,
                expected_lock_version=revision.lock_version,
                expected_definition_sha256=revision.definition_sha256,
                validation_report=report,
                sample_hashes={sample.sample_id: sample.response_sha256},
            )
        )
        await asyncio.sleep(0.1)
        assert not save_task.done()
        release_delete.set()
        await delete_task
        with pytest.raises(ParserConfigurationError) as caught:
            await save_task
        assert caught.value.code == "revision_conflict"
    finally:
        release_delete.set()
        tasks = [task for task in (delete_task, save_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            await asyncio.gather(task, return_exceptions=True)
        await repository.delete_action_configuration(
            action.ba_id, delete_objects=lambda _sample: asyncio.sleep(0)
        )
        async with postgres_db.asession_scope() as session:
            await session.execute(
                delete(platformSource).where(platformSource.bs_id == action.bs_id)
            )
        await postgres_db.aclose()


@pytest.mark.asyncio
async def test_postgres_action_cleanup_blocks_concurrent_sample_creation():
    postgres_db = postgres_db_or_skip()
    action, _platform = await seed_action(postgres_db)
    cleanup_repo = ActionParserRepository(postgres_db)
    create_repo = ActionParserRepository(postgres_db)
    await cleanup_repo.create_sample(new_sample(action.ba_id, suffix=uuid4().hex))
    deleting = asyncio.Event()
    release_delete = asyncio.Event()

    async def paused_delete(_sample):
        deleting.set()
        await release_delete.wait()

    cleanup_task = asyncio.create_task(
        cleanup_repo.delete_action_configuration(
            action.ba_id, delete_objects=paused_delete
        )
    )
    create_task = None
    try:
        await asyncio.wait_for(deleting.wait(), timeout=5)
        create_task = asyncio.create_task(
            create_repo.create_sample(new_sample(action.ba_id, suffix=uuid4().hex))
        )
        await asyncio.sleep(0.1)
        assert not create_task.done()
        release_delete.set()
        await cleanup_task
        with pytest.raises(ParserConfigurationError) as caught:
            await create_task
        assert caught.value.code == "action_not_found"
    finally:
        release_delete.set()
        tasks = [task for task in (cleanup_task, create_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            await asyncio.gather(task, return_exceptions=True)
        async with postgres_db.asession_scope() as session:
            await session.execute(
                delete(platformSource).where(platformSource.bs_id == action.bs_id)
            )
        await postgres_db.aclose()
