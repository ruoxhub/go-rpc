from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm.catalog import (
    CatalogConflictError,
    CatalogNotFoundError,
    DiscoveredModel,
    LlmCatalog,
    SyncCounts,
)
from models.base import Base
from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol
from storage.exceptions import SQLOperationError


class Database:
    def __init__(self, sessions):
        self.sessions = sessions

    @asynccontextmanager
    async def asession_scope(self):
        async with self.sessions() as session:
            async with session.begin():
                yield session


class ConvertingDatabase(Database):
    @asynccontextmanager
    async def asession_scope(self):
        try:
            async with super().asession_scope() as session:
                yield session
        except Exception as error:
            raise SQLOperationError("converted", cause=error) from error


class FakeReferenceChecker:
    def __init__(self, references: list[str] | None = None):
        self.references = references or []

    async def list_references(self, provider_id: int) -> list[str]:
        assert provider_id > 0
        return self.references


@pytest_asyncio.fixture
async def db(tmp_path):
    public_db = tmp_path / "public.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'main.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public(dbapi_connection, _connection_record):
        dbapi_connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[LlmProvider.__table__, LlmModel.__table__],
            )
        )

    test_db = Database(async_sessionmaker(engine, expire_on_commit=False))
    yield test_db
    await engine.dispose()


async def add_provider(db, *, name="OpenAI", prefix="openai"):
    async with db.asession_scope() as session:
        provider = LlmProvider(
            name=name,
            litellm_prefix=prefix,
            protocol=ProviderProtocol.OPENAI_COMPLETION,
            api_key="secret",
        )
        session.add(provider)
        await session.flush()
        return provider.id


@pytest.mark.asyncio
async def test_get_models_uses_one_session_for_batch(db):
    provider_id = await add_provider(db)
    async with db.asession_scope() as session:
        session.add_all([
            LlmModel(
                id=7, provider_id=provider_id, remote_model_id="analysis",
                litellm_model="openai/analysis", display_name="Analysis",
            ),
            LlmModel(
                id=8, provider_id=provider_id, remote_model_id="transcription",
                litellm_model="openai/transcription", display_name="Transcription",
            ),
        ])

    class CountingDatabase:
        calls = 0

        @asynccontextmanager
        async def asession_scope(self):
            self.calls += 1
            async with db.asession_scope() as session:
                yield session

    counting_db = CountingDatabase()
    catalog = LlmCatalog(counting_db, reference_checker=FakeReferenceChecker())

    result = await catalog.get_models([7, 8])

    assert set(result) == {7, 8}
    assert counting_db.calls == 1


@pytest.mark.asyncio
async def test_replace_marks_missing_models_unavailable_and_builds_litellm_name(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())

    assert await catalog.replace_discovered_models(
        provider_id, [DiscoveredModel("old", "Old")]
    ) == SyncCounts(created=1, updated=0, unavailable=0)
    counts = await catalog.replace_discovered_models(
        provider_id, [DiscoveredModel("new", "New")]
    )

    assert counts == SyncCounts(created=1, updated=0, unavailable=1)
    models = await catalog.list_models(provider_id)
    assert [(model.remote_model_id, model.remote_available) for model in models] == [
        ("new", True),
        ("old", False),
    ]
    assert models[0].litellm_model == "openai/new"
    provider = await catalog.require_provider(provider_id)
    assert provider.last_sync_status == "success"
    assert isinstance(provider.last_sync_at, datetime)
    assert provider.last_sync_error is None


@pytest.mark.asyncio
async def test_catalog_derives_prefix_and_rewrites_models_on_format_change(db):
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    provider = await catalog.create_provider(
        name="Main",
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        base_url="https://api.example.com",
        api_key="secret",
    )
    await catalog.replace_discovered_models(
        provider.id, [DiscoveredModel("model-a", "Model A")]
    )

    updated = await catalog.update_provider(
        provider.id, protocol=ProviderProtocol.OPENAI_RESPONSES
    )
    models = await catalog.list_models(provider.id)

    assert updated.litellm_prefix == "responses/openai"
    assert models[0].litellm_model == "responses/openai/model-a"


@pytest.mark.asyncio
async def test_rediscovery_updates_remote_fields_without_overwriting_enabled(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    await catalog.replace_discovered_models(
        provider_id, [DiscoveredModel("gpt", "Old name")]
    )
    async with db.asession_scope() as session:
        model = await session.get(LlmModel, 1)
        model.enabled = False
        model.remote_available = False
        previous_discovery = model.last_discovered_at

    counts = await catalog.replace_discovered_models(
        provider_id, [DiscoveredModel("gpt", "New name")]
    )

    assert counts == SyncCounts(created=0, updated=1, unavailable=0)
    model, provider = await catalog.get_model(1)
    assert provider.id == provider_id
    assert model.display_name == "New name"
    assert model.enabled is False
    assert model.remote_available is True
    assert isinstance(model.last_discovered_at, datetime)
    assert model.last_discovered_at != previous_discovery


@pytest.mark.asyncio
async def test_provider_and_model_queries_and_usable_filter(db):
    first_id = await add_provider(db, name="First", prefix="first")
    second_id = await add_provider(db, name="Second", prefix="second")
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    await catalog.replace_discovered_models(
        first_id,
        [DiscoveredModel("usable", "Usable"), DiscoveredModel("disabled", "Disabled")],
    )
    async with db.asession_scope() as session:
        disabled = await session.get(LlmModel, 2)
        disabled.enabled = False

    assert (await catalog.get_provider(first_id)).name == "First"
    assert [item.id for item in await catalog.list_providers()] == [first_id, second_id]
    model, provider = await catalog.get_model(1)
    assert model.remote_model_id == "usable"
    assert provider.id == first_id
    assert [item.remote_model_id for item in await catalog.list_models(first_id)] == [
        "disabled",
        "usable",
    ]
    assert [
        item.remote_model_id
        for item in await catalog.list_models(first_id, usable_only=True)
    ] == ["usable"]


@pytest.mark.asyncio
async def test_updated_provider_stays_readable_after_session_close(db):
    """updated_at 由数据库生成，离开会话后必须仍可读，否则 500 DetachedInstanceError。"""
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    provider = await catalog.create_provider(
        name="Main", protocol=ProviderProtocol.OPENAI_COMPLETION, api_key="secret",
    )

    updated = await catalog.update_provider(provider.id, name="Renamed")

    assert updated.name == "Renamed"
    assert isinstance(updated.updated_at, datetime)


@pytest.mark.asyncio
async def test_discovered_timestamps_are_naive_for_timestamp_without_time_zone(db):
    """t_llm_* 的时间列不带时区；写 aware datetime 会让 asyncpg 直接报错。"""
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    provider_id = await add_provider(db)

    await catalog.replace_discovered_models(
        provider_id, [DiscoveredModel("gpt", "GPT")]
    )
    await catalog.record_sync_failure(provider_id, "HTTP status 500")

    model = (await catalog.list_models(provider_id))[0]
    provider = await catalog.require_provider(provider_id)
    assert model.last_discovered_at.tzinfo is None
    assert provider.last_sync_at.tzinfo is None
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())

    assert await catalog.get_provider(999) is None
    with pytest.raises(CatalogNotFoundError, match="999"):
        await catalog.require_provider(999)
    with pytest.raises(CatalogNotFoundError, match="999"):
        await catalog.replace_discovered_models(999, [])


@pytest.mark.asyncio
async def test_missing_provider_error_is_raised_after_converting_session_scope(db):
    catalog = LlmCatalog(
        ConvertingDatabase(db.sessions),
        reference_checker=FakeReferenceChecker(),
    )

    with pytest.raises(CatalogNotFoundError, match="999"):
        await catalog.replace_discovered_models(999, [])


class EmptyScalarResult:
    def one_or_none(self):
        return None


class RecordingSession:
    def __init__(self):
        self.statements = []

    async def scalars(self, statement):
        self.statements.append(statement)
        return EmptyScalarResult()


class RecordingDatabase:
    def __init__(self):
        self.session = RecordingSession()

    @asynccontextmanager
    async def asession_scope(self):
        yield self.session


@pytest.mark.asyncio
async def test_replace_locks_only_the_selected_provider_row():
    db = RecordingDatabase()
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())

    with pytest.raises(CatalogNotFoundError):
        await catalog.replace_discovered_models(7, [])

    sql = str(
        db.session.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    assert "WHERE PUBLIC.T_LLM_PROVIDER.ID = 7" in " ".join(sql.split())
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_ensure_provider_deletable_reports_all_model_references(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(
        db,
        reference_checker=FakeReferenceChecker(
            [
                "default_analysis_model_id",
                "default_transcription_model_id",
                "task.config.llm_model_id",
            ]
        ),
    )

    with pytest.raises(CatalogConflictError) as exc_info:
        await catalog.ensure_provider_deletable(provider_id)

    message = str(exc_info.value)
    assert "default_analysis_model_id" in message
    assert "default_transcription_model_id" in message
    assert "task.config.llm_model_id" in message


@pytest.mark.asyncio
async def test_provider_without_references_is_deletable(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())

    await catalog.ensure_provider_deletable(provider_id)


@pytest.mark.asyncio
async def test_record_sync_success_sets_status_and_clears_error(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    await catalog.record_sync_failure(provider_id, "HTTP status 500")

    await catalog.record_sync_success(provider_id)

    provider = await catalog.require_provider(provider_id)
    assert provider.last_sync_status == "success"
    assert isinstance(provider.last_sync_at, datetime)
    assert provider.last_sync_error is None


@pytest.mark.asyncio
async def test_record_sync_failure_sets_sanitized_summary(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())

    await catalog.record_sync_failure(provider_id, "HTTP status 401")

    provider = await catalog.require_provider(provider_id)
    assert provider.last_sync_status == "failed"
    assert isinstance(provider.last_sync_at, datetime)
    assert provider.last_sync_error == "HTTP status 401"


def test_reference_checker_is_required():
    with pytest.raises(TypeError, match="reference_checker"):
        LlmCatalog(object())


@pytest.mark.asyncio
async def test_catalog_crud_toggle_and_explicit_model_delete(db):
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    provider = await catalog.create_provider(
        name="Custom", protocol=ProviderProtocol.OPENAI_COMPLETION,
        base_url="https://example.com", api_key="top-secret",
    )
    updated = await catalog.update_provider(provider.id, name="Renamed", enabled=False)
    assert (updated.name, updated.enabled, updated.api_key) == ("Renamed", False, "top-secret")
    await catalog.replace_discovered_models(provider.id, [DiscoveredModel("chat", "Chat")])
    model = (await catalog.list_models(provider.id))[0]
    assert (await catalog.set_model_enabled(model.id, False)).enabled is False
    await catalog.delete_provider(provider.id)
    assert await catalog.get_provider(provider.id) is None
    assert await catalog.get_model(model.id) is None


@pytest.mark.asyncio
async def test_delete_provider_checks_references(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker(["runtime default"]))
    with pytest.raises(CatalogConflictError):
        await catalog.delete_provider(provider_id)
    assert await catalog.get_provider(provider_id) is not None


@pytest.mark.asyncio
async def test_reference_guard_rejects_unusable_model(db):
    provider_id = await add_provider(db)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    await catalog.replace_discovered_models(provider_id, [DiscoveredModel("chat", "Chat")])
    model = (await catalog.list_models(provider_id))[0]
    await catalog.set_model_enabled(model.id, False)

    with pytest.raises(CatalogConflictError, match="not usable"):
        async with catalog.reference_guard([model.id]):
            pass


class GuardRecordingSession:
    def __init__(self, provider):
        self.provider = provider
        self.statements = []
    async def scalars(self, statement):
        self.statements.append(statement)
        return type("Rows", (), {"one_or_none": lambda _: self.provider})()
    async def execute(self, statement): self.statements.append(statement)
    async def delete(self, value): pass

class GuardRecordingDatabase:
    def __init__(self, provider): self.session = GuardRecordingSession(provider)
    @asynccontextmanager
    async def asession_scope(self): yield self.session

@pytest.mark.asyncio
async def test_delete_locks_provider_before_reference_check():
    provider = LlmProvider(id=7, name="x", litellm_prefix="x", protocol=ProviderProtocol.OPENAI_COMPLETION, api_key="secret")
    db = GuardRecordingDatabase(provider)
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    await catalog.delete_provider(7)
    sql = str(db.session.statements[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).upper()
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_reference_guard_locks_models_and_providers_in_stable_order():
    provider = LlmProvider(id=7, name="x", litellm_prefix="x", protocol=ProviderProtocol.OPENAI_COMPLETION, api_key="secret", enabled=True)
    model = LlmModel(id=9, provider_id=7, remote_model_id="m", litellm_model="x/m", display_name="M", enabled=True, remote_available=True)
    class Session:
        def __init__(self): self.statement = None
        async def execute(self, statement):
            self.statement = statement
            return type("Rows", (), {"all": lambda _: [(model, provider)]})()
    class DB:
        def __init__(self): self.session = Session()
        @asynccontextmanager
        async def asession_scope(self): yield self.session
    db = DB()
    catalog = LlmCatalog(db, reference_checker=FakeReferenceChecker())
    async with catalog.reference_guard([9]):
        pass
    sql = str(db.session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).upper()
    assert "FOR UPDATE" in sql
    assert "ORDER BY PUBLIC.T_LLM_PROVIDER.ID, PUBLIC.T_LLM_MODEL.ID" in " ".join(sql.split())
