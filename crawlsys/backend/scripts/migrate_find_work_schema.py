"""Schema migration: 将 t_crawl_task 的 4 个 find_work 相关列合并为 JSON 列。

变更:
    - 新增 public.t_crawl_task.find_work JSONB
    - 把 ref_table / ref_where / params_columns / entity_column 打包写入 find_work
    - 删除 4 个旧列

回滚 (未自动提供):
    - 新增 4 列, 从 find_work 抽出, 删除 find_work

幂等: 已存在 find_work 列则跳过 add; 已不存在旧列则跳过 drop。

用法:
    cd crawler && python -m scripts.migrate_find_work_schema
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from core.config import SchedulerConfig
from storage import SQLAlchemyDB


LEGACY_COLS = ("ref_table", "ref_where", "params_columns", "entity_column")


async def _column_exists(session, column: str) -> bool:
    sql = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 't_crawl_task' "
        "AND column_name = :col"
    )
    result = await session.execute(sql, {"col": column})
    return result.scalar_one_or_none() is not None


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
        has_find_work = await _column_exists(session, "find_work")
        legacy_present = {
            c: await _column_exists(session, c) for c in LEGACY_COLS
        }

        if not has_find_work:
            await session.execute(
                text("ALTER TABLE public.t_crawl_task ADD COLUMN find_work JSONB")
            )
            print("  + added column find_work JSONB")
        else:
            print("  = column find_work already exists")

        if any(legacy_present.values()):
            build_obj = "jsonb_strip_nulls(jsonb_build_object(" + ", ".join(
                f"'{c}', {c}" for c in LEGACY_COLS
            ) + "))"
            await session.execute(
                text(
                    f"UPDATE public.t_crawl_task "
                    f"SET find_work = {build_obj} "
                    f"WHERE find_work IS NULL AND ("
                    + " OR ".join(f"{c} IS NOT NULL" for c in LEGACY_COLS)
                    + ")"
                )
            )
            print("  + backfilled find_work from legacy columns")

        for c in LEGACY_COLS:
            if legacy_present[c]:
                await session.execute(
                    text(f"ALTER TABLE public.t_crawl_task DROP COLUMN {c}")
                )
                print(f"  - dropped column {c}")

    print("Migration complete.")
    await db.aclose()


if __name__ == "__main__":
    asyncio.run(migrate())
