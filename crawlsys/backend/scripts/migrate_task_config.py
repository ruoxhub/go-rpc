#!/usr/bin/env python3
"""One-shot migration: BusTask -> config JSON + platform FK.

Usage:
  python scripts/migrate_task_config.py --dsn <postgresql://...> [--dry-run]

Steps:
  1. Add config (JSONB) and platform_code (transition column)
  2. Backfill platform_code (auto-detect bs_name or bs_platform_code match)
  3. Backfill config (JSON assembly from legacy columns)
  4. Rename legacy columns to _legacy, add FK constraint
"""
import argparse
import asyncio
import json
import re
import sys
from typing import Optional

import asyncpg


# ---------- Helpers ----------

_COL_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_EXPR_RE = re.compile(r"^[a-zA-Z0-9_.:'()\- >]+$")


def parse_params_columns(raw: Optional[str], key_column: Optional[str]) -> tuple[dict, list]:
    """'uid as user_id, mid, name' -> ({"uid":"user_id","mid":"mid","name":"name"}, ["mid","name"])
    Tolerates expressions like "extend::json->>'aid' as aid" for migration.
    """
    if not raw:
        return {}, []
    param_map: dict[str, str] = {}
    extras: list[str] = []
    for token in (t.strip() for t in raw.split(",") if t.strip()):
        token = re.sub(r"^\s*DISTINCT\s+", "", token, flags=re.IGNORECASE).strip()
        if not token:
            continue
        if " as " in token.lower():
            parts = re.split(r"\s+as\s+", token, flags=re.IGNORECASE)
            col, alias = parts[0].strip(), parts[1].strip()
        else:
            col = alias = token
        
        if not _COL_RE.match(alias):
            raise ValueError(f"Invalid column alias: {alias!r}")
        if not _EXPR_RE.match(col):
            raise ValueError(f"Invalid SQL expression: {col!r}")

        param_map[col] = alias
        if key_column and alias != key_column and col != key_column:
            extras.append(col)
    return param_map, extras


def build_config(row: dict) -> Optional[dict]:
    """Convert a legacy BusTask row into TaskConfig JSON."""
    find_work = row.get("find_work")
    result_column = row.get("result_column")
    post_update_column = row.get("post_update_column")
    post_update_table = row.get("post_update_table")

    # Normalize find_work: may be str (JSON text), dict, or None
    if isinstance(find_work, str):
        try:
            find_work = json.loads(find_work)
            if find_work == "null" or find_work is None:
                find_work = None
        except Exception:
            find_work = None
    if isinstance(find_work, str) and find_work == "null":
        find_work = None

    source = None
    if find_work and isinstance(find_work, dict):
        ref_table = find_work.get("ref_table")
        key_column = find_work.get("entity_column")
        if ref_table and key_column:
            param_map, extras = parse_params_columns(find_work.get("params_columns"), key_column)
            source = {
                "table": ref_table,
                "where": find_work.get("ref_where"),
                "key_column": key_column,
                "param_map": param_map,
                "extra_columns": extras,
            }

    sink = {"mode": "auto"}
    if result_column:
        sink["result_column"] = result_column
    if post_update_column:
        sink["mark_done_column"] = post_update_column
    if post_update_table:
        sink["mark_done_table"] = post_update_table

    return {"source": source, "sink": sink}


# ---------- Main flow ----------

async def migrate(dsn: str, dry_run: bool) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        # Step 0: audit
        # Be tolerant for resume (platform may have been renamed to platform_legacy)
        audit_col = "platform"
        try:
            await conn.fetchval("SELECT platform FROM public.t_crawl_task LIMIT 1")
        except Exception:
            audit_col = "platform_legacy"
        audit = await conn.fetch(f"""
            SELECT {audit_col} AS platform, COUNT(*) AS n
            FROM public.t_crawl_task
            GROUP BY {audit_col}
            ORDER BY n DESC
        """)
        print("[audit] current BusTask.platform distribution:")
        for r in audit:
            print(f"  {r['platform']!r} : {r['n']}")

        platforms = await conn.fetch("""
            SELECT bs_name, bs_platform_code FROM public.t_busi_platform
        """)
        name_to_code = {r["bs_name"]: r["bs_platform_code"] for r in platforms if r["bs_platform_code"]}
        code_set = {c for c in name_to_code.values() if c}
        print(f"[audit] known bs_platform_code set: {sorted(code_set)}")

        # Step 1: add columns
        print("[1/4] adding config (JSONB) and platform_code (VARCHAR) columns ...")
        if not dry_run:
            await conn.execute("""
                ALTER TABLE public.t_crawl_task
                    ADD COLUMN IF NOT EXISTS config JSONB,
                    ADD COLUMN IF NOT EXISTS platform_code VARCHAR(100)
            """)

        # Step 2: backfill platform_code
        print("[2/4] backfilling platform_code ...")
        # Support resume: platform may have been renamed to platform_legacy already
        col = "platform"
        try:
            await conn.fetchval("SELECT platform FROM public.t_crawl_task LIMIT 1")
        except Exception:
            col = "platform_legacy"
        rows = await conn.fetch(f"SELECT task_id, {col} AS platform FROM public.t_crawl_task")
        unmapped = set()
        for r in rows:
            old = r["platform"]
            if old in code_set:
                new_code = old
            elif old in name_to_code:
                new_code = name_to_code[old]
            else:
                unmapped.add(old)
                continue
            if not dry_run:
                await conn.execute(
                    "UPDATE public.t_crawl_task SET platform_code = $1 WHERE task_id = $2",
                    new_code, r["task_id"],
                )
        if unmapped:
            print(f"[warn] unmapped platform values (will leave platform_code NULL): {sorted(unmapped)}")

        # Step 3: backfill config
        print("[3/4] backfilling config JSON ...")
        # Support resume: after renames the columns may be *_legacy
        def _col(name: str) -> str:
            return name
        # Probe which set of columns exist
        has_legacy = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='t_crawl_task' AND column_name='find_work_legacy'"
        )
        if has_legacy:
            src_find = "find_work_legacy"
            src_res = "result_column_legacy"
            src_puc = "post_update_column_legacy"
            src_put = "post_update_table_legacy"
        else:
            src_find = "find_work"
            src_res = "result_column"
            src_puc = "post_update_column"
            src_put = "post_update_table"

        rows = await conn.fetch(f"""
            SELECT task_id, {src_find} AS find_work, {src_res} AS result_column,
                   {src_puc} AS post_update_column, {src_put} AS post_update_table
            FROM public.t_crawl_task
        """)
        for r in rows:
            cfg = build_config(dict(r))
            if not dry_run:
                # Use json text + ::jsonb cast for reliable object storage in JSONB (works across asyncpg versions)
                await conn.execute(
                    "UPDATE public.t_crawl_task SET config = $1::jsonb WHERE task_id = $2",
                    json.dumps(cfg), r["task_id"],
                )

        # Step 4: swap columns
        print("[4/4] swapping columns (rename legacy + FK) ...")
        if not dry_run:
            async def _col_exists(name: str) -> bool:
                return bool(await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='t_crawl_task' AND column_name=$1
                    """,
                    name,
                ))

            # Rename original 'platform' (the name one) to _legacy ONLY if the migration-introduced
            # platform_code does not exist anymore (i.e. we are still in pre-swap state).
            # After platform_code has been renamed to 'platform', we must not touch the new 'platform'.
            if await _col_exists("platform") and await _col_exists("platform_code"):
                # Both exist: 'platform' here is the *old* one, platform_code is the temp new
                await conn.execute('ALTER TABLE public.t_crawl_task RENAME COLUMN "platform" TO "platform_legacy"')
                print("    renamed platform -> platform_legacy")
            elif await _col_exists("platform") and not await _col_exists("platform_code"):
                # Only 'platform' exists. Could be:
                # - very old state, or
                # - already final (platform_code already swapped in). Do nothing to 'platform'.
                # We detect final state by existence of platform_legacy + platform + no old source cols
                pass
            else:
                print("    (skip) platform -> platform_legacy (already done or not applicable)")

            for old, new in [
                ("find_work", "find_work_legacy"),
                ("result_column", "result_column_legacy"),
                ("post_update_column", "post_update_column_legacy"),
                ("post_update_table", "post_update_table_legacy"),
                ("platform_code", "platform"),
            ]:
                if await _col_exists(old):
                    await conn.execute(f'ALTER TABLE public.t_crawl_task RENAME COLUMN "{old}" TO "{new}"')
                    print(f"    renamed {old} -> {new}")
                else:
                    print(f"    (skip) {old} does not exist")

            # Ensure target column has uniqueness (required for FK on non-PK column)
            # bs_platform_code is the logical business key
            uq_exists = await conn.fetchval(
                """
                SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema='public' AND tc.table_name='t_busi_platform'
                  AND ccu.column_name='bs_platform_code'
                  AND tc.constraint_type IN ('UNIQUE', 'PRIMARY KEY')
                """
            )
            if not uq_exists:
                await conn.execute("""
                    ALTER TABLE public.t_busi_platform
                    ADD CONSTRAINT uq_bs_platform_code UNIQUE (bs_platform_code)
                """)
                print("    added UNIQUE on t_busi_platform.bs_platform_code")

            # Add FK if not present
            fk_exists = await conn.fetchval(
                """
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema='public' AND table_name='t_crawl_task'
                  AND constraint_name='fk_task_platform'
                """
            )
            if not fk_exists:
                await conn.execute("""
                    ALTER TABLE public.t_crawl_task
                    ADD CONSTRAINT fk_task_platform
                    FOREIGN KEY (platform) REFERENCES public.t_busi_platform(bs_platform_code)
                """)
                print("    added FK fk_task_platform")
            else:
                print("    (skip) FK already exists")

            # Set NOT NULL if column exists and is nullable
            is_nullable = await conn.fetchval(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema='public' AND table_name='t_crawl_task' AND column_name='platform'
                """
            )
            if is_nullable == "YES":
                await conn.execute("ALTER TABLE public.t_crawl_task ALTER COLUMN platform SET NOT NULL")
                print("    set platform NOT NULL")
            elif is_nullable == "NO":
                print("    (skip) platform already NOT NULL")
        print("done." + (" (dry-run, no changes applied)" if dry_run else ""))
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, help="postgresql://user:pass@host/db")
    parser.add_argument("--dry-run", action="store_true", help="print actions without applying")
    args = parser.parse_args()
    asyncio.run(migrate(args.dsn, args.dry_run))
