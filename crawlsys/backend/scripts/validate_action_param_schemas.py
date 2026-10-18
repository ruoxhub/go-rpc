"""Read-only preflight for persisted Action parameter schemas."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = BACKEND_ROOT / "app"
for path in (APP_ROOT, BACKEND_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from sqlalchemy import text

from core.config import SchedulerConfig
from core.param_schema import InvalidActionParamSchema, normalize_action_param_schema
from storage import SQLAlchemyDB


_SELECT_ACTION_SCHEMAS = (
    "SELECT ba_id, ba_params_schema FROM public.t_busi_action ORDER BY ba_id"
)


async def _load_action_schemas(db) -> list[tuple[int, str | None]]:
    async with db.asession_scope() as session:
        result = await session.execute(text(_SELECT_ACTION_SCHEMAS))
        return list(result.fetchall())


def _invalid_ids(rows: list[tuple[int, str | None]]) -> list[int]:
    invalid = []
    for ba_id, stored_schema in rows:
        try:
            decoded = None if stored_schema is None else json.loads(stored_schema)
            normalize_action_param_schema(decoded)
        except (json.JSONDecodeError, InvalidActionParamSchema, TypeError):
            invalid.append(ba_id)
    return sorted(invalid)


async def find_invalid_action_schemas(db) -> list[int]:
    return _invalid_ids(await _load_action_schemas(db))


async def run(db) -> int:
    rows = await _load_action_schemas(db)
    invalid_ids = _invalid_ids(rows)
    if invalid_ids:
        for ba_id in invalid_ids:
            print(f"ba_id={ba_id}")
        return 1
    print(f"validated {len(rows)} action schemas")
    return 0


async def _run_from_config(config_path: str) -> int:
    config = SchedulerConfig.from_toml(config_path)
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
        return await run(db)
    finally:
        await db.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate persisted Action parameter schemas without modifying them."
    )
    parser.add_argument("--config", default="config.toml")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_from_config(args.config))
    except Exception:
        print("action schema validation failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
