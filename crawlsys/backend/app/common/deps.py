"""Shared dependencies for web routes — DB instance and lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager

from storage import SQLAlchemyDB
from core.config import SchedulerConfig

_db: SQLAlchemyDB | None = None
_config: SchedulerConfig | None = None


def get_db() -> SQLAlchemyDB:
    assert _db is not None, "Database not initialized"
    return _db


def get_config() -> SchedulerConfig:
    assert _config is not None, "Config not initialized"
    return _config


def set_config(config: SchedulerConfig) -> None:
    global _config
    _config = config


@asynccontextmanager
async def lifespan(app):
    """Initialize DB connection on startup, close on shutdown.

    Runs inside the web server's own event loop (separate thread from the
    scheduler worker), so this DB instance is local to the web thread.
    """
    global _db

    config = get_config()
    pg = config.postgresql
    _db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    await _db.aconnect()
    await _db.ainit_db()

    yield

    await _db.aclose()
    _db = None
