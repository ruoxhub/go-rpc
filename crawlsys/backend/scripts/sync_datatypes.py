"""Synchronize registered ORM and DTO models into t_sys_datatype.

Usage:
    uv run python scripts/sync_datatypes.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Match the official backend entrypoint
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in sys.path:
    sys.path.append(_APP_DIR)

from common.logging import get_logger
from core.config import SchedulerConfig
from core.repository import DatatypeRepo
from storage import SQLAlchemyDB

logger = get_logger(__file__)


async def main() -> None:
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql

    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    await db.aconnect()
    try:
        repo = DatatypeRepo(db)
        count, keys = await repo.sync_from_code()
        logger.info(f"Successfully synced {count} datatypes into t_sys_datatype: {', '.join(keys)}")
        print(f"Successfully synced {count} datatypes: {', '.join(keys)}")
    finally:
        await db.aclose()


if __name__ == "__main__":
    asyncio.run(main())
