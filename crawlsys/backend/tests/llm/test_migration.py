from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm.catalog import CatalogConflictError, LlmCatalog
from llm.migration import (
    LLM_MIGRATION_MARKER_KEY,
    RuntimeConfigReferenceChecker,
    _acquire_migration_lock,
    _advisory_lock_sql,
    _task_reference_sql,
    migrate_legacy_llm_settings,
)
from models.base import Base
from models.llm_provider import LlmModel, LlmProvider
from runtime_config.models import LlmSettings
from runtime_config.store import LLM_KEY
from runtime_config.store import LEGACY_LLM_REQUEST_PATH_KEY


class Database:
    def __init__(self, sessions):
        self.sessions = sessions

    @asynccontextmanager
    async def asession_scope(self):
        async with self.sessions() as session:
            async with session.begin():
                yield session


class Redis:
    def __init__(self, values=None, fail_key=None):
        self.values = values or {}
        self.fail_key = fail_key

    async def astrget(self, key):
        return self.values.get(key)

    async def astrset(self, key, value, **kwargs):
        if key == self.fail_key:
            raise RuntimeError("redis write failed")
        if kwargs.get("nx") and key in self.values:
            return None
        self.values[key] = value
        return True


@pytest_asyncio.fixture
async def db(tmp_path):
    public_db = tmp_path / "public.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'main.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public(connection, _):
        connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(
            sync, tables=[LlmProvider.__table__, LlmModel.__table__]
        ))
    value = Database(async_sessionmaker(engine, expire_on_commit=False))
    yield value
    await engine.dispose()


def legacy_payload():
    return json.dumps({
        "format": "openai", "model": "gpt-4o-mini", "api_key": "secret",
        "base_url": "https://legacy.test/v1", "request_path": "responses",
        "max_tokens": 321, "temperature": 0.4, "enable_thinking": True,
    })


@pytest.mark.asyncio
async def test_legacy_migration_creates_one_provider_and_model_idempotently(db):
    redis = Redis({LLM_KEY: legacy_payload()})
    await migrate_legacy_llm_settings(db, redis)
    await migrate_legacy_llm_settings(db, redis)

    settings = LlmSettings.model_validate_json(redis.values[LLM_KEY])
    assert settings.max_tokens == 321
    assert settings.temperature == 0.4
    assert settings.enable_thinking is True
    assert settings.default_transcription_model_id is None
    async with db.asession_scope() as session:
        assert len((await session.scalars(LlmProvider.__table__.select())).all()) == 1
        assert len((await session.scalars(LlmModel.__table__.select())).all()) == 1
    assert redis.values[LLM_MIGRATION_MARKER_KEY] == "1"
    assert redis.values[LEGACY_LLM_REQUEST_PATH_KEY] == "responses"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("format_name", "request_path", "protocol", "prefix"),
    [
        ("openai", "chat", "openai-completion", "openai"),
        ("openai", "responses", "openai-responses", "responses/openai"),
        ("anthropic", "chat", "claude", "anthropic"),
        ("openai-completion", "chat", "openai-completion", "openai"),
        ("claude", "chat", "claude", "anthropic"),
        ("gemini", "chat", "gemini", "gemini"),
        ("deepseek", "chat", "deepseek", "deepseek"),
        ("openai-responses", "chat", "openai-responses", "responses/openai"),
    ],
)
async def test_legacy_seed_maps_provider_format(
    db, format_name, request_path, protocol, prefix
):
    payload = json.loads(legacy_payload())
    payload.update(format=format_name, request_path=request_path)
    redis = Redis({LLM_KEY: json.dumps(payload)})

    await migrate_legacy_llm_settings(db, redis)

    async with db.asession_scope() as session:
        provider = (await session.scalars(select(LlmProvider))).one()
        model = (await session.scalars(select(LlmModel))).one()
    assert provider.protocol.value == protocol
    assert provider.litellm_prefix == prefix
    assert model.litellm_model == f"{prefix}/{payload['model']}"


@pytest.mark.asyncio
async def test_migration_reuses_equivalent_existing_provider(db):
    async with db.asession_scope() as session:
        session.add(LlmProvider(
            name="Existing", litellm_prefix="responses/openai",
            protocol="openai-responses", base_url="https://legacy.test/v1",
            api_key="secret",
        ))
    redis = Redis({LLM_KEY: legacy_payload()})

    await migrate_legacy_llm_settings(db, redis)

    async with db.asession_scope() as session:
        providers = list(await session.scalars(select(LlmProvider)))
    assert len(providers) == 1
    assert providers[0].api_key == "secret"


@pytest.mark.asyncio
async def test_migration_prefers_exact_key_over_earlier_empty_key_candidate(db):
    async with db.asession_scope() as session:
        session.add_all([
            LlmProvider(
                name="Empty key", litellm_prefix="responses/openai",
                protocol="openai-responses", base_url="https://legacy.test/v1",
                api_key="",
            ),
            LlmProvider(
                name="Exact key", litellm_prefix="responses/openai",
                protocol="openai-responses", base_url="https://legacy.test/v1",
                api_key="secret",
            ),
        ])
    redis = Redis({LLM_KEY: legacy_payload()})

    await migrate_legacy_llm_settings(db, redis)

    async with db.asession_scope() as session:
        providers = list(await session.scalars(select(LlmProvider)))
        model = (await session.scalars(select(LlmModel))).one()
    exact = next(item for item in providers if item.name == "Exact key")
    empty = next(item for item in providers if item.name == "Empty key")
    assert model.provider_id == exact.id
    assert empty.api_key == ""


@pytest.mark.asyncio
async def test_migration_does_not_reuse_equivalent_endpoint_with_different_key(db):
    async with db.asession_scope() as session:
        session.add(LlmProvider(
            name="Legacy runtime provider", litellm_prefix="responses/openai",
            protocol="openai-responses", base_url="https://legacy.test/v1",
            api_key="different-secret",
        ))
    redis = Redis({LLM_KEY: legacy_payload()})
    await migrate_legacy_llm_settings(db, redis)
    async with db.asession_scope() as session:
        providers = list(await session.scalars(select(LlmProvider)))
    assert len(providers) == 2
    assert all("secret" not in provider.name for provider in providers)


@pytest.mark.asyncio
async def test_migration_fills_empty_key_and_ignores_fixed_name_collision(db):
    async with db.asession_scope() as session:
        session.add(LlmProvider(
            name="Existing", litellm_prefix="responses/openai",
            protocol="openai-responses", base_url="https://legacy.test/v1",
            api_key="",
        ))
    redis = Redis({LLM_KEY: legacy_payload()})
    await migrate_legacy_llm_settings(db, redis)
    async with db.asession_scope() as session:
        providers = list(await session.scalars(select(LlmProvider)))
    reused = next(item for item in providers if item.name == "Existing")
    assert reused.api_key == "secret"
    assert len(providers) == 1


def test_migration_uses_advisory_lock_and_safe_text_task_reference_sql():
    advisory_sql = _advisory_lock_sql().upper()
    reference_sql = _task_reference_sql().upper()
    assert "PG_ADVISORY_XACT_LOCK" in advisory_sql
    assert "CONFIG -> 'ANALYSIS' ->> 'LLM_MODEL_ID'" in reference_sql
    assert "CAST(CONFIG" not in reference_sql
    assert "TEXT[]" in reference_sql


@pytest.mark.asyncio
async def test_task_reference_query_uses_text_ids_so_malformed_json_is_safe():
    class Result:
        def first(self):
            return None

    class Session:
        async def execute(self, statement, params):
            self.statement = str(statement)
            self.params = params
            return Result()

    session = Session()

    class TaskDatabase:
        @asynccontextmanager
        async def asession_scope(self):
            yield session

    checker = RuntimeConfigReferenceChecker(
        TaskDatabase(), Redis(), task_reference_checker=None
    )
    assert await checker._query_task_references([7, 9]) == []
    assert session.params == {"ids": ["7", "9"]}
    assert "CAST(config" not in session.statement


@pytest.mark.asyncio
async def test_advisory_lock_executes_only_for_postgresql():
    class Session:
        def __init__(self, dialect):
            self.bind = type("Bind", (), {"dialect": type("Dialect", (), {"name": dialect})()})()
            self.statements = []

        def get_bind(self):
            return self.bind

        async def execute(self, statement):
            self.statements.append(str(statement))

    postgres = Session("postgresql")
    sqlite = Session("sqlite")
    await _acquire_migration_lock(postgres)
    await _acquire_migration_lock(sqlite)
    assert "pg_advisory_xact_lock" in postgres.statements[0]
    assert sqlite.statements == []


@pytest.mark.asyncio
async def test_migration_does_not_mark_complete_when_settings_write_fails(db):
    redis = Redis({LLM_KEY: legacy_payload()}, fail_key=LLM_KEY)
    with pytest.raises(RuntimeError, match="redis write failed"):
        await migrate_legacy_llm_settings(db, redis)
    assert LLM_MIGRATION_MARKER_KEY not in redis.values


@pytest.mark.asyncio
async def test_completed_migration_short_circuits(db):
    redis = Redis({LLM_KEY: "invalid", LLM_MIGRATION_MARKER_KEY: "1"})
    await migrate_legacy_llm_settings(db, redis)
    assert redis.values[LLM_KEY] == "invalid"


@pytest.mark.asyncio
async def test_completed_migration_initializes_missing_request_path_from_seed(db):
    redis = Redis({LLM_MIGRATION_MARKER_KEY: "1"})
    seed = type("Seed", (), {"values": {"request_path": "responses"}})()

    await migrate_legacy_llm_settings(db, redis, seed)

    assert redis.values[LEGACY_LLM_REQUEST_PATH_KEY] == "responses"


@pytest.mark.asyncio
async def test_reference_checker_blocks_provider_used_by_default_model(db):
    redis = Redis({LLM_KEY: legacy_payload()})
    await migrate_legacy_llm_settings(db, redis)
    checker = RuntimeConfigReferenceChecker(db, redis, task_reference_checker=lambda _: [])
    catalog = LlmCatalog(db, reference_checker=checker)
    provider_id = (await catalog.list_providers())[0].id

    with pytest.raises(CatalogConflictError, match="default_analysis_model_id"):
        await catalog.ensure_provider_deletable(provider_id)
