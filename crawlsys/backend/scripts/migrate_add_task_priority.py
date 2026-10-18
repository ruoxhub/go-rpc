"""Idempotent migration: add five-level priority to t_crawl_task."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sqlalchemy import text

from core.config import SchedulerConfig
from storage import SQLAlchemyDB


MIGRATION_STATEMENTS = [
    (
        "ALTER TABLE public.t_crawl_task "
        "ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 2"
    ),
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'ck_task_priority_range'
              AND conrelid = 'public.t_crawl_task'::regclass
        ) THEN
            ALTER TABLE public.t_crawl_task
                ADD CONSTRAINT ck_task_priority_range
                CHECK (priority BETWEEN 0 AND 4);
        END IF;
    END
    $$
    """,
]


async def run_migration(db) -> None:
    async with db.asession_scope() as session:
        for statement in MIGRATION_STATEMENTS:
            await session.execute(text(statement))


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
        await run_migration(db)
        print("Done.")
    finally:
        await db.aclose()


if __name__ == "__main__":
    asyncio.run(main())
