"""One-time migration: drop parser_mode and parser_func columns from t_crawl_task.

Usage:
    cd crawler && python -m scripts.drop_parser_columns
Idempotent — safe to run multiple times.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from core.config import SchedulerConfig
from storage import SQLAlchemyDB


async def migrate():
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username, password=pg.password,
        host=pg.host, port=pg.port, database=pg.database,
        amode=True, driver="postgresql",
    )
    await db.aconnect()

    async with db.asession_scope() as session:
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 't_crawl_task' "
            "AND column_name IN ('parser_mode', 'parser_func')"
        ))
        existing = {row[0] for row in result.fetchall()}

        if not existing:
            print("Columns already dropped, nothing to do.")
            await db.aclose()
            return

        print(f"Dropping columns: {existing}")

        if "parser_mode" in existing:
            await session.execute(text(
                "ALTER TABLE public.t_crawl_task DROP COLUMN parser_mode"
            ))
            print("  Dropped parser_mode")

        if "parser_func" in existing:
            await session.execute(text(
                "ALTER TABLE public.t_crawl_task DROP COLUMN parser_func"
            ))
            print("  Dropped parser_func")

    print("Migration complete.")
    await db.aclose()


if __name__ == "__main__":
    asyncio.run(migrate())
