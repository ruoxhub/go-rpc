"""MCP 适配层共享测试夹具。"""

from contextlib import asynccontextmanager

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.base import Base
from models.content import Content
from models.user import User


class TestDatabase:
    def __init__(self, sessions, statements):
        self._sessions = sessions
        self.statements = statements

    @asynccontextmanager
    async def asession_scope(self):
        async with self._sessions() as session:
            async with session.begin():
                yield session


@pytest_asyncio.fixture
async def content_db(tmp_path):
    public_db = tmp_path / "public.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'content.db'}")
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public(dbapi_connection, _connection_record):
        dbapi_connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[Content.__table__],
            )
        )

    yield TestDatabase(async_sessionmaker(engine, expire_on_commit=False), statements)
    await engine.dispose()


@pytest_asyncio.fixture
async def user_db(tmp_path):
    public_db = tmp_path / "user-public.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'user.db'}")
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "connect")
    def attach_public(dbapi_connection, _connection_record):
        dbapi_connection.execute("ATTACH DATABASE ? AS public", (str(public_db),))

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[User.__table__],
            )
        )

    yield TestDatabase(async_sessionmaker(engine, expire_on_commit=False), statements)
    await engine.dispose()
