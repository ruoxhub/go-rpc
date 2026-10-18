import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.migrate_add_task_priority import MIGRATION_STATEMENTS
from storage.sql._async import AsyncSQLImpl


class FakeURL:
    def __init__(self, backend: str):
        self.backend = backend

    def get_backend_name(self) -> str:
        return self.backend


def make_impl(backend: str):
    impl = object.__new__(AsyncSQLImpl)
    impl.engine = SimpleNamespace(url=FakeURL(backend))
    session = SimpleNamespace(execute=AsyncMock())

    @asynccontextmanager
    async def session_scope():
        yield session

    impl.asession_scope = session_scope
    return impl, session


@pytest.mark.asyncio
async def test_postgresql_migrations_include_task_and_material_columns():
    impl, session = make_impl("postgresql")

    await impl.amigrate_db()

    statements = [
        str(call.args[0]).strip() for call in session.execute.await_args_list
    ]
    migration_sql = (
        Path(__file__).parents[2]
        / "scripts"
        / "migrate_llm_provider_formats.sql"
    ).read_text(encoding="utf-8")
    assert len(statements) >= 9
    assert migration_sql.strip() in statements
    combined = "\n".join(statements)
    assert "t_crawl_task" in combined
    assert "loop_enabled BOOLEAN NOT NULL DEFAULT FALSE" in combined
    assert "loop_interval_seconds INTEGER" in combined
    assert "next_run_at TIMESTAMP" in combined
    assert (
        "t_crawl_task ADD COLUMN IF NOT EXISTS priority "
        "SMALLINT NOT NULL DEFAULT 2"
    ) in combined
    assert "ck_task_priority_range" in combined
    assert "priority BETWEEN 0 AND 4" in combined
    normalized_runtime = " ".join(combined.split())
    for statement in MIGRATION_STATEMENTS:
        assert " ".join(statement.split()) in normalized_runtime
    assert (
        "t_material_clean ADD COLUMN IF NOT EXISTS is_analysis "
        "SMALLINT NOT NULL DEFAULT 0"
    ) in combined
    assert "COMMENT ON COLUMN public.t_material_clean.is_analysis" in combined
    assert (
        "t_video_analysis_result ADD COLUMN IF NOT EXISTS llm_model_id INTEGER"
        in combined
    )
    assert "t_video_analysis_result ALTER COLUMN model TYPE VARCHAR(500)" in combined
    assert "fk_video_analysis_llm_model" in combined
    assert "idx_video_analysis_llm_model_id" in combined
    assert "openai-completion" in combined
    assert "openai-responses" in combined
    assert "native_anthropic" in combined
    assert "provider_protocol_enum" in combined
    assert "litellm_model" in combined
    assert all(
        description in combined
        for description in ("0=未分析", "1=分析成功", "2=分析中", "3=分析失败")
    )


def test_llm_provider_format_migration_is_idempotent_and_preserves_ids():
    sql = (
        Path(__file__).parents[2]
        / "scripts"
        / "migrate_llm_provider_formats.sql"
    ).read_text(encoding="utf-8")
    assert "DROP CONSTRAINT IF EXISTS provider_protocol_enum" in sql
    assert "UPDATE public.t_llm_provider" in sql
    assert "UPDATE public.t_llm_model" in sql
    assert "DELETE" not in sql.upper()
    assert "provider_protocol_enum" in sql


@pytest.mark.asyncio
async def test_llm_provider_format_migration_executes_twice_on_old_postgresql_data():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")

    schema = f"llm_provider_migration_{uuid.uuid4().hex}"
    engine = create_async_engine(url)
    migration_sql = (
        Path(__file__).parents[2]
        / "scripts"
        / "migrate_llm_provider_formats.sql"
    ).read_text(encoding="utf-8").replace("public.", f"{schema}.")

    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"""
                CREATE TABLE {schema}.t_llm_provider (
                    id INTEGER PRIMARY KEY,
                    protocol VARCHAR(32) NOT NULL,
                    litellm_prefix VARCHAR(100) NOT NULL,
                    CONSTRAINT provider_protocol_enum CHECK (
                        protocol IN (
                            'openai_compatible', 'native_gemini',
                            'native_anthropic'
                        )
                    )
                )
            """))
            await connection.execute(text(f"""
                CREATE TABLE {schema}.t_llm_model (
                    id INTEGER PRIMARY KEY,
                    provider_id INTEGER NOT NULL REFERENCES
                        {schema}.t_llm_provider(id),
                    remote_model_id VARCHAR(255) NOT NULL,
                    litellm_model VARCHAR(500) NOT NULL
                )
            """))
            await connection.execute(text(f"""
                INSERT INTO {schema}.t_llm_provider
                    (id, protocol, litellm_prefix)
                VALUES
                    (11, 'openai_compatible', 'legacy-openai'),
                    (12, 'native_anthropic', 'legacy-anthropic'),
                    (13, 'native_gemini', 'legacy-gemini')
            """))
            await connection.execute(text(f"""
                INSERT INTO {schema}.t_llm_model
                    (id, provider_id, remote_model_id, litellm_model)
                VALUES
                    (21, 11, 'model-openai', 'legacy/model-openai'),
                    (22, 12, 'model-claude', 'legacy/model-claude'),
                    (23, 13, 'model-gemini', 'legacy/model-gemini')
            """))

            async def snapshot():
                providers = (await connection.execute(text(f"""
                    SELECT id, protocol, litellm_prefix
                    FROM {schema}.t_llm_provider ORDER BY id
                """))).all()
                models = (await connection.execute(text(f"""
                    SELECT id, provider_id, litellm_model
                    FROM {schema}.t_llm_model ORDER BY id
                """))).all()
                return providers, models

            await connection.execute(text(migration_sql))
            first = await snapshot()
            await connection.execute(text(migration_sql))
            second = await snapshot()

            assert first == second
            assert first[0] == [
                (11, "openai-completion", "openai"),
                (12, "claude", "anthropic"),
                (13, "gemini", "gemini"),
            ]
            assert first[1] == [
                (21, 11, "openai/model-openai"),
                (22, 12, "anthropic/model-claude"),
                (23, 13, "gemini/model-gemini"),
            ]
            check_definition = await connection.scalar(text(f"""
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'provider_protocol_enum'
                  AND conrelid = '{schema}.t_llm_provider'::regclass
            """))
            assert check_definition is not None
            assert all(
                value in check_definition
                for value in (
                    "openai-completion", "claude", "gemini",
                    "deepseek", "openai-responses",
                )
            )
            assert await connection.scalar(text(f"""
                SELECT count(*)
                FROM pg_constraint
                WHERE contype = 'f'
                  AND conrelid = '{schema}.t_llm_model'::regclass
                  AND confrelid = '{schema}.t_llm_provider'::regclass
            """)) == 1

            savepoint = await connection.begin_nested()
            with pytest.raises(IntegrityError):
                await connection.execute(text(f"""
                    INSERT INTO {schema}.t_llm_provider
                        (id, protocol, litellm_prefix)
                    VALUES (99, 'unsupported', 'unsupported')
                """))
            await savepoint.rollback()
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        await engine.dispose()


@pytest.mark.asyncio
async def test_media_worker_state_migrations_are_idempotent_and_match_script():
    impl, session = make_impl("postgresql")

    await impl.amigrate_db()

    runtime_sql = "\n".join(
        str(call.args[0]).strip() for call in session.execute.await_args_list
    )
    script_sql = (
        Path(__file__).parents[2] / "scripts" / "add_media_worker_state.sql"
    ).read_text(encoding="utf-8")
    expected_names = {
        "t_video_clean_cursor",
        "uq_video_clean_cursor_consumer_platform",
        "download_claim_token",
        "download_claimed_at",
        "download_attempt_count",
        "download_next_retry_at",
        "download_last_error",
        "idx_mc_download_claim",
    }
    for sql in (runtime_sql, script_sql):
        assert expected_names <= {name for name in expected_names if name in sql}
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "ADD COLUMN IF NOT EXISTS" in sql
        assert "CREATE UNIQUE INDEX IF NOT EXISTS" in sql
        assert "CREATE INDEX IF NOT EXISTS" in sql


@pytest.mark.asyncio
async def test_non_postgresql_skips_migrations():
    impl, session = make_impl("sqlite")

    await impl.amigrate_db()

    session.execute.assert_not_awaited()
