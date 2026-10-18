"""Playwright 专用 FastAPI 入口，使用临时 SQLite 数据库。"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
for path in (APP_DIR, BACKEND_DIR.parent):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from fastapi import FastAPI  # noqa: E402

from api.crawler import router as crawler_router  # noqa: E402
from models.action import Action  # noqa: E402
from models.action_parser import ActionParserRevision  # noqa: E402
from models.keyword import BusiSearchKeyword  # noqa: E402
from models.platform import platformSource  # noqa: E402
from models.task import BusTask  # noqa: E402
from api.deps import get_db, get_llm_catalog, get_runtime_config_store  # noqa: E402
from runtime_config.models import SchedulerSettings  # noqa: E402
from storage import SQLAlchemyDB  # noqa: E402


class _FakeRuntimeConfigStore:
    async def get_scheduler(self) -> SchedulerSettings:
        return SchedulerSettings()


class _FakeLlmCatalog:
    async def get_model(self, _model_id: int):
        return None


def database_path() -> Path:
    raw_path = os.environ.get("CRAWLER_E2E_DB")
    if not raw_path:
        raise RuntimeError("CRAWLER_E2E_DB is required")
    return Path(raw_path).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    db = SQLAlchemyDB("", "", "", 0, ":memory:", amode=True, driver="sqlite")

    @event.listens_for(db.engine.sync_engine, "connect")
    def attach_public_schema(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")
        dbapi_connection.execute("ATTACH DATABASE ? AS public", (str(path),))

    await db.aconnect()
    async with db.engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: platformSource.metadata.create_all(
                sync_connection,
                tables=[
                    platformSource.__table__,
                    Action.__table__,
                    ActionParserRevision.__table__,
                    BusiSearchKeyword.__table__,
                    BusTask.__table__,
                ],
            ),
        )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_runtime_config_store] = lambda: _FakeRuntimeConfigStore()
    app.dependency_overrides[get_llm_catalog] = lambda: _FakeLlmCatalog()
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        await db.aclose()
        path.unlink(missing_ok=True)


app = FastAPI(title="Crawler Admin E2E", lifespan=lifespan)
app.include_router(crawler_router)
