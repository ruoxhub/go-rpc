from __future__ import annotations

import asyncio
import os
from typing import cast
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Table, delete, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from models.action import Action
from models.action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from models.platform import platformSource
from models.task import BusTask
from models.task_config import SinkConfig, TaskConfig
from parser.definition import definition_sha256, validate_parser_definition
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionParserRepository
from storage import SQLAlchemyDB


MODEL_DEFINITION = {
    "schema_version": 1,
    "output": {"mode": "model", "datatype": "content"},
    "fields": [
        {"target": "/content_id", "source": "/id"},
        {"target": "/platform", "value": "test"},
    ],
}
JSON_DEFINITION = {
    "schema_version": 1,
    "output": {"mode": "json"},
    "fields": [{"target": "/payload", "source": ""}],
}


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


async def _seed_action(db, *, params_schema='{"type":"object"}'):
    async with db.asession_scope() as session:
        platform = platformSource(
            bs_name="test",
            bs_platform_code=f"test-{uuid4().hex}",
        )
        session.add(platform)
        await session.flush()
        action = Action(
            bs_id=platform.bs_id,
            ba_action="detail",
            ba_params_schema=params_schema,
        )
        session.add(action)
        await session.flush()
        return action


async def _seed_revision(
    db,
    action,
    *,
    revision_no=1,
    status="draft",
    definition=MODEL_DEFINITION,
    validation_report=None,
    lock_version=1,
    source_sample_id=None,
):
    parsed = validate_parser_definition(definition)
    async with db.asession_scope() as session:
        revision = ActionParserRevision(
            ba_id=action.ba_id,
            revision_no=revision_no,
            status=status,
            definition=parsed.model_dump(mode="json", exclude_unset=True),
            definition_sha256=definition_sha256(parsed),
            source="manual",
            source_sample_id=source_sample_id,
            validation_report=validation_report,
            lock_version=lock_version,
        )
        session.add(revision)
        await session.flush()
        return revision


async def _seed_sample(db, action, *, response_sha256="a" * 64):
    async with db.asession_scope() as session:
        sample = ActionParserSample(
            ba_id=action.ba_id,
            request_params_redacted={},
            request_params_hmac_sha256="b" * 64,
            request_hmac_key_version="v1",
            raw_object_key=f"raw/{uuid4().hex}",
            redacted_object_key=f"redacted/{uuid4().hex}",
            response_sha256=response_sha256,
            response_bytes=2,
            sanitizer_version="v1",
            rpc_duration_ms=1,
        )
        session.add(sample)
        await session.flush()
        return sample


def _successful_report(revision, sample_ids):
    return {
        "passed": True,
        "definition_sha256": revision.definition_sha256,
        "sample_ids": sample_ids,
    }


@pytest.mark.asyncio
async def test_load_runtime_uses_params_and_published_definition(db):
    action = await _seed_action(db)
    revision = await _seed_revision(db, action, status="published")

    runtime = await ActionParserRepository(db).load_runtime(
        action.ba_id, include_parser=True
    )

    assert runtime.parser_revision_id == revision.revision_id
    assert runtime.parser_definition is not None
    assert runtime.parser_definition.output.mode == "model"
    assert runtime.params_schema == {"type": "object"}


@pytest.mark.asyncio
async def test_invalid_published_definition_fails_closed_without_definition_leak(db):
    action = await _seed_action(db)
    async with db.asession_scope() as session:
        revision = ActionParserRevision(
            ba_id=action.ba_id,
            revision_no=1,
            status="published",
            definition={"secret": "do-not-leak"},
            definition_sha256="c" * 64,
            source="manual",
        )
        session.add(revision)
        await session.flush()

    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).load_runtime(action.ba_id, include_parser=True)

    assert caught.value.code == "parser_definition_invalid"
    assert caught.value.details == {
        "ba_id": action.ba_id,
        "revision_id": revision.revision_id,
    }
    assert "do-not-leak" not in str(caught.value)


@pytest.mark.asyncio
async def test_publish_source_loads_params_without_validating_parser(db):
    action = await _seed_action(db)
    async with db.asession_scope() as session:
        session.add(
            ActionParserRevision(
                ba_id=action.ba_id,
                revision_no=1,
                status="published",
                definition={"secret": "broken"},
                definition_sha256="c" * 64,
                source="manual",
            )
        )

    runtime = await ActionParserRepository(db).load_runtime(
        action.ba_id, include_parser=False
    )

    assert runtime.params_schema == {"type": "object"}
    assert runtime.parser_revision_id is None
    assert runtime.parser_definition is None


@pytest.mark.asyncio
async def test_create_draft_is_unique_and_uses_next_revision_number(db):
    action = await _seed_action(db)
    await _seed_revision(db, action, status="archived", revision_no=4)
    repo = ActionParserRepository(db)

    draft = await repo.create_draft(action.ba_id, definition=MODEL_DEFINITION)

    assert draft.status == "draft"
    assert draft.revision_no == 5
    with pytest.raises(ParserConfigurationError) as caught:
        await repo.create_draft(action.ba_id, definition=MODEL_DEFINITION)
    assert caught.value.code == "draft_already_exists"


@pytest.mark.asyncio
async def test_patch_with_stale_lock_clears_nothing(db):
    action = await _seed_action(db)
    sample = await _seed_sample(db, action)
    draft = await _seed_revision(
        db,
        action,
        source_sample_id=sample.sample_id,
        validation_report={"success": True},
        lock_version=3,
    )
    async with db.asession_scope() as session:
        session.add(
            ActionParserRevisionSample(
                revision_id=draft.revision_id,
                sample_id=sample.sample_id,
                sample_sha256=sample.response_sha256,
            )
        )

    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).patch_draft(
            draft.revision_id,
            expected_lock_version=2,
            definition=JSON_DEFINITION,
            source="manual",
            source_sample_id=None,
            generation_metadata=None,
        )

    assert caught.value.code == "revision_conflict"
    async with db.asession_scope() as session:
        stored = await session.get(ActionParserRevision, draft.revision_id)
        joins = (
            await session.execute(
                select(ActionParserRevisionSample).where(
                    ActionParserRevisionSample.revision_id == draft.revision_id
                )
            )
        ).scalars().all()
        assert stored.lock_version == 3
        assert stored.validation_report == {"success": True}
        assert len(joins) == 1


@pytest.mark.asyncio
async def test_patch_increments_lock_and_clears_preview_associations(db):
    action = await _seed_action(db)
    sample = await _seed_sample(db, action)
    draft = await _seed_revision(
        db,
        action,
        source_sample_id=sample.sample_id,
        validation_report={"success": True},
    )
    async with db.asession_scope() as session:
        session.add(
            ActionParserRevisionSample(
                revision_id=draft.revision_id,
                sample_id=sample.sample_id,
                sample_sha256=sample.response_sha256,
            )
        )

    updated = await ActionParserRepository(db).patch_draft(
        draft.revision_id,
        expected_lock_version=1,
        definition=JSON_DEFINITION,
        source="manual",
        source_sample_id=None,
        generation_metadata=None,
    )

    assert updated.lock_version == 2
    assert updated.validation_report is None
    assert updated.source_sample_id is None
    assert await ActionParserRepository(db).list_validation_samples(
        draft.revision_id
    ) == []


@pytest.mark.asyncio
async def test_save_preview_atomically_replaces_samples_and_rejects_stale_hash(db):
    action = await _seed_action(db)
    draft = await _seed_revision(db, action)
    first = await _seed_sample(db, action, response_sha256="1" * 64)
    second = await _seed_sample(db, action, response_sha256="2" * 64)
    repo = ActionParserRepository(db)

    await repo.save_preview(
        draft.revision_id,
        expected_lock_version=1,
        expected_definition_sha256=draft.definition_sha256,
        validation_report=_successful_report(draft, [first.sample_id]),
        sample_hashes={first.sample_id: first.response_sha256},
    )
    await repo.save_preview(
        draft.revision_id,
        expected_lock_version=1,
        expected_definition_sha256=draft.definition_sha256,
        validation_report=_successful_report(draft, [second.sample_id]),
        sample_hashes={second.sample_id: second.response_sha256},
    )

    assert await repo.list_validation_samples(draft.revision_id) == [second.sample_id]
    with pytest.raises(ParserConfigurationError) as caught:
        await repo.save_preview(
            draft.revision_id,
            expected_lock_version=1,
            expected_definition_sha256=draft.definition_sha256,
            validation_report=_successful_report(draft, [first.sample_id]),
            sample_hashes={first.sample_id: "0" * 64},
        )
    assert caught.value.code == "revision_conflict"
    assert await repo.list_validation_samples(draft.revision_id) == [second.sample_id]


@pytest.mark.asyncio
async def test_save_preview_rejects_empty_sample_set(db):
    action = await _seed_action(db)
    draft = await _seed_revision(db, action)

    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).save_preview(
            draft.revision_id,
            expected_lock_version=1,
            expected_definition_sha256=draft.definition_sha256,
            validation_report=_successful_report(draft, []),
            sample_hashes={},
        )

    assert caught.value.code == "revision_conflict"


@pytest.mark.asyncio
async def test_publish_archives_previous_revision_and_pins_validated_draft(db):
    action = await _seed_action(db)
    old = await _seed_revision(db, action, status="published", revision_no=1)
    draft = await _seed_revision(db, action, revision_no=2)
    sample = await _seed_sample(db, action)
    repo = ActionParserRepository(db)
    await repo.save_preview(
        draft.revision_id,
        expected_lock_version=1,
        expected_definition_sha256=draft.definition_sha256,
        validation_report=_successful_report(draft, [sample.sample_id]),
        sample_hashes={sample.sample_id: sample.response_sha256},
    )

    published = await repo.publish(draft.revision_id)

    async with db.asession_scope() as session:
        previous = await session.get(ActionParserRevision, old.revision_id)
        assert previous.status == "archived"
    assert published.status == "published"
    assert published.published_at is not None


@pytest.mark.asyncio
async def test_publish_rejects_incompatible_task_without_changing_statuses(db):
    action = await _seed_action(db)
    draft = await _seed_revision(db, action, definition=JSON_DEFINITION)
    sample = await _seed_sample(db, action)
    async with db.asession_scope() as session:
        platform_code = await session.scalar(
            select(platformSource.bs_platform_code).where(
                platformSource.bs_id == action.bs_id
            )
        )
    assert platform_code is not None
    async with db.asession_scope() as session:
        session.add(
            BusTask(
                platform=platform_code,
                action="detail",
                ba_id=action.ba_id,
                config=TaskConfig(sink=SinkConfig(mode="standard")),
            )
        )
    repo = ActionParserRepository(db)
    await repo.save_preview(
        draft.revision_id,
        expected_lock_version=1,
        expected_definition_sha256=draft.definition_sha256,
        validation_report=_successful_report(draft, [sample.sample_id]),
        sample_hashes={sample.sample_id: sample.response_sha256},
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await repo.publish(draft.revision_id)

    assert caught.value.code == "sink_incompatible"
    async with db.asession_scope() as session:
        assert (await session.get(ActionParserRevision, draft.revision_id)).status == "draft"


@pytest.mark.asyncio
async def test_archive_only_accepts_current_published_and_does_not_parse_definition(db):
    action = await _seed_action(db)
    async with db.asession_scope() as session:
        revision = ActionParserRevision(
            ba_id=action.ba_id,
            revision_no=1,
            status="published",
            definition={"secret": "broken"},
            definition_sha256="c" * 64,
            source="manual",
        )
        session.add(revision)
        await session.flush()

    archived = await ActionParserRepository(db).archive(
        action.ba_id, revision.revision_id
    )

    assert archived.status == "archived"
    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).archive(action.ba_id, revision.revision_id)
    assert caught.value.code == "invalid_revision_transition"


@pytest.mark.asyncio
async def test_delete_only_accepts_draft(db):
    action = await _seed_action(db)
    draft = await _seed_revision(db, action)
    await ActionParserRepository(db).delete_draft(draft.revision_id)
    async with db.asession_scope() as session:
        assert await session.get(ActionParserRevision, draft.revision_id) is None

    published = await _seed_revision(db, action, status="published", revision_no=2)
    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).delete_draft(published.revision_id)
    assert caught.value.code == "invalid_revision_transition"


@pytest.mark.asyncio
async def test_restore_creates_unvalidated_new_draft_without_sample_joins(db):
    action = await _seed_action(db)
    archived = await _seed_revision(
        db,
        action,
        status="archived",
        validation_report={"success": True},
    )

    restored = await ActionParserRepository(db).restore_as_draft(
        archived.revision_id
    )

    assert restored.status == "draft"
    assert restored.revision_no > archived.revision_no
    assert restored.validation_report is None
    assert restored.restored_from_revision_id == archived.revision_id
    assert await ActionParserRepository(db).list_validation_samples(
        restored.revision_id
    ) == []


@pytest.mark.asyncio
async def test_restored_draft_with_forged_empty_preview_cannot_publish(db):
    action = await _seed_action(db)
    archived = await _seed_revision(db, action, status="archived")
    restored = await ActionParserRepository(db).restore_as_draft(
        archived.revision_id
    )
    async with db.asession_scope() as session:
        stored = await session.get(ActionParserRevision, restored.revision_id)
        assert stored is not None
        stored.validation_report = _successful_report(restored, [])

    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).publish(restored.revision_id)

    assert caught.value.code == "invalid_revision_transition"


@pytest.mark.asyncio
async def test_restore_requires_archived_revision_and_no_existing_draft(db):
    action = await _seed_action(db)
    archived = await _seed_revision(db, action, status="archived")
    await _seed_revision(db, action, revision_no=2)

    with pytest.raises(ParserConfigurationError) as caught:
        await ActionParserRepository(db).restore_as_draft(archived.revision_id)
    assert caught.value.code == "invalid_revision_transition"


@pytest.mark.asyncio
async def test_sample_reference_counts_include_source_and_validation_joins(db):
    action = await _seed_action(db)
    sample = await _seed_sample(db, action)
    draft = await _seed_revision(db, action, source_sample_id=sample.sample_id)
    async with db.asession_scope() as session:
        session.add(
            ActionParserRevisionSample(
                revision_id=draft.revision_id,
                sample_id=sample.sample_id,
                sample_sha256=sample.response_sha256,
            )
        )

    assert await ActionParserRepository(db).count_sample_references(
        sample.sample_id
    ) == (1, 1)


@pytest.mark.asyncio
async def test_restore_waits_for_create_action_lock_and_rechecks_transition(monkeypatch):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL concurrency test")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")

    parsed_url = make_url(url)
    postgres_db = SQLAlchemyDB(
        parsed_url.username or "",
        parsed_url.password or "",
        parsed_url.host or "",
        parsed_url.port or 5432,
        parsed_url.database or "",
        amode=True,
        driver="postgresql",
    )
    engine = postgres_db.engine
    assert isinstance(engine, AsyncEngine)
    action = await _seed_action(postgres_db)
    archived = await _seed_revision(postgres_db, action, status="archived")
    create_repo = ActionParserRepository(postgres_db)
    restore_repo = ActionParserRepository(postgres_db)
    action_locked = asyncio.Event()
    release_create = asyncio.Event()
    original_lock = create_repo._lock_action

    async def paused_lock(session: AsyncSession, ba_id: int):
        locked = await original_lock(session, ba_id)
        action_locked.set()
        await release_create.wait()
        return locked

    monkeypatch.setattr(create_repo, "_lock_action", paused_lock)
    create_task: asyncio.Task[ActionParserRevision] | None = None
    restore_task: asyncio.Task[ActionParserRevision] | None = None
    try:
        create_task = asyncio.create_task(
            create_repo.create_draft(action.ba_id, definition=MODEL_DEFINITION)
        )
        await asyncio.wait_for(action_locked.wait(), timeout=5)
        restore_task = asyncio.create_task(
            restore_repo.restore_as_draft(archived.revision_id)
        )
        await asyncio.sleep(0.1)
        assert not restore_task.done()
        release_create.set()
        await create_task
        with pytest.raises(ParserConfigurationError) as caught:
            await restore_task
        assert caught.value.code == "invalid_revision_transition"
    finally:
        release_create.set()
        tasks = [task for task in (create_task, restore_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with postgres_db.asession_scope() as session:
            revision_ids = select(ActionParserRevision.revision_id).where(
                ActionParserRevision.ba_id == action.ba_id
            )
            await session.execute(
                delete(ActionParserRevisionSample).where(
                    ActionParserRevisionSample.revision_id.in_(revision_ids)
                )
            )
            await session.execute(
                delete(ActionParserRevision).where(
                    ActionParserRevision.ba_id == action.ba_id
                )
            )
            await session.execute(
                delete(ActionParserSample).where(
                    ActionParserSample.ba_id == action.ba_id
                )
            )
            await session.execute(delete(BusTask).where(BusTask.ba_id == action.ba_id))
            await session.execute(delete(Action).where(Action.ba_id == action.ba_id))
            await session.execute(
                delete(platformSource).where(platformSource.bs_id == action.bs_id)
            )
        await postgres_db.aclose()
