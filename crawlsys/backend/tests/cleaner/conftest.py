import os
import uuid
from contextlib import asynccontextmanager

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


class TestDB:
    def __init__(self, engine):
        self.engine = engine

    @asynccontextmanager
    async def asession_scope(self):
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


@pytest_asyncio.fixture
async def cleaner_postgres_db():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        import pytest

        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("TEST_DATABASE_URL must use postgresql+asyncpg://")

    schema = f"cleaner_test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                CREATE TABLE t_busi_content (
                    id BIGSERIAL PRIMARY KEY,
                    content_id VARCHAR(64),
                    platform VARCHAR(50),
                    pub_time TIMESTAMP,
                    view_count BIGINT,
                    download_time TIMESTAMP,
                    title VARCHAR(512),
                    url VARCHAR(1024),
                    created_time TIMESTAMP,
                    updated_time TIMESTAMP,
                    extend TEXT
                )
                """
            )
        )
        await connection.execute(
            text(
                """
                CREATE TABLE t_material_clean (
                    id BIGSERIAL PRIMARY KEY,
                    datatype VARCHAR(10) NOT NULL DEFAULT 'clean',
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
                    expire_time TIMESTAMP NOT NULL,
                    created_time TIMESTAMP DEFAULT now(),
                    updated_time TIMESTAMP DEFAULT now(),
                    UNIQUE (platform, content_id)
                )
                """
            )
        )

    try:
        yield TestDB(engine)
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()
