"""One-time migration: 为 t_busi_task_logs 添加 btl_platformid 列。

Usage:
    cd crawler && python -m scripts.migrate_add_btl_platform_id
Idempotent — ALTER TABLE IF NOT EXISTS 语法保证可重复执行。
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
            "ALTER TABLE public.t_busi_task_logs "
            "ADD COLUMN IF NOT EXISTS btl_platformid INTEGER"
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
    await db.ainit_db()
    await run_migration(db)
    print("Done.")
    await db.aclose()


if __name__ == "__main__":
    asyncio.run(main())