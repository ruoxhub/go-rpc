"""One-time migration: add looping task fields to t_crawl_task.

Usage:
    cd crawler && python -m scripts.migrate_add_task_loop_fields
Idempotent: each column uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

NOTE: the same idempotent ALTER statements are also applied automatically at
startup by ``SQLAlchemyDB.amigrate_db()`` (called from main.main after
ainit_db). This script remains the manual / dev-only path for applying the
migration without booting the full scheduler. Keep the two SQL blocks in sync.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from core.config import SchedulerConfig
from storage import SQLAlchemyDB


async def run_migration(db) -> None:
    async with db.asession_scope() as session:
        await session.execute(text(
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS loop_enabled BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        await session.execute(text(
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS loop_interval_seconds INTEGER"
        ))
        await session.execute(text(
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP"
        ))


async def main() -> None:
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username, password=pg.password,
        host=pg.host, port=pg.port, database=pg.database,
        amode=True, driver="postgresql",
    )
    await db.aconnect()
    try:
        await run_migration(db)
        print("Done.")
    finally:
        await db.aclose()


if __name__ == "__main__":
    asyncio.run(main())
