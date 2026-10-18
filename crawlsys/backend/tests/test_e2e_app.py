"""Playwright 专用应用的数据库隔离约束测试。"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.deps import get_db
from tests.e2e_app import app


@pytest.mark.asyncio
async def test_e2e_app_enables_sqlite_foreign_keys_and_enforces_them(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("CRAWLER_E2E_DB", str(tmp_path / "crawler.sqlite3"))

    async with app.router.lifespan_context(app):
        db = app.dependency_overrides[get_db]()
        async with db.engine.connect() as connection:
            assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
            with pytest.raises(IntegrityError):
                await connection.execute(
                    text(
                        "INSERT INTO public.t_busi_action "
                        "(bs_id, ba_action, ba_enabled) "
                        "VALUES (999999, 'MissingPlatform', true)"
                    )
                )
