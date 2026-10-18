"""Sync the generated action catalog against persisted t_busi_action rows.

Supports diff reporting (--check / --dry-run) and database synchronization (--apply).
(See docs/superpowers/specs/2026-09-17-action-sync-mechanism-design.md).

Data flow:
    browser-rpc/content/<id>/platform.json + api.js JSDoc
      -> node browser-rpc/scripts/platforms.mjs sync
      -> scripts/generated/action-catalog.json   (generated SSOT)
      -> this script (--apply / --check)
      -> public.t_busi_action                   (persisted)

Usage:
    # Dry-run report (default)
    python scripts/sync_platform_actions.py --config config.toml

    # Check for drift (exit 1 if drift found, ideal for CI)
    python scripts/sync_platform_actions.py --config config.toml --check

    # Apply synchronization into database
    python scripts/sync_platform_actions.py --config config.toml --apply

    # Force overwrite even for manual-edited actions
    python scripts/sync_platform_actions.py --config config.toml --apply --force

    # Only sync or check a specific platform
    python scripts/sync_platform_actions.py --config config.toml --apply --platform bilibili

Exit codes:
    0  no drift (check mode) or sync successful (apply mode)
    1  drift found (check mode) or blocking error
    2  usage / IO error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = BACKEND_ROOT / "app"
for path in (APP_ROOT, BACKEND_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from sqlalchemy import text

from core.config import SchedulerConfig
from core.param_schema import normalize_action_param_schema
from storage import SQLAlchemyDB

from services.action_sync import (
    DEFAULT_CATALOG_PATH as _CATALOG_PATH,
    SELECT_PLATFORMS as _SELECT_PLATFORMS,
    _has_column,
    _load_db_rows,
    _schema_names,
    apply_sync,
    build_report,
    catalog_params_to_schema,
    load_catalog,
    load_unified_catalog,
    normalized_schema,
)


def _print_report(report: dict[str, Any], catalog: list[dict[str, Any]], verbose: bool) -> None:
    catalog_actions = sum(len(entry.get("actions", {})) for entry in catalog)
    catalog_with_params = sum(
        1
        for entry in catalog
        for action in entry.get("actions", {}).values()
        if action.get("params")
    )
    print(f"catalog: {len(catalog)} platforms / {catalog_actions} actions "
          f"({catalog_with_params} with params)")
    print(f"database: {report['db_action_count']} actions / "
          f"{report['db_platform_count']} platforms with bs_platform_code")
    print(f"missing: {len(report['missing'])}")
    print(f"conflicting: {len(report['conflicting'])}")
    print(f"writable (schema empty in db): {len(report['writable'])}")
    print(f"unvalidatable (schema rejected by normalize_action_param_schema): "
          f"{len(report['unvalidatable'])}")
    if report["unknown_group"]:
        print(
            f"catalog groups not present in t_busi_platform: "
            f"{len(report['unknown_group'])} "
            f"(e.g. {', '.join(report['unknown_group'][:8])})"
        )
    if not verbose:
        return
    for bucket in ("missing", "conflicting", "writable", "unvalidatable"):
        for item in report[bucket][:50]:
            print(f"  [{bucket}] {item}")


async def _run(
    config_path: str,
    catalog_path: Path,
    only_platform: str | None,
    verbose: bool,
    apply: bool,
    check: bool,
    force: bool,
) -> int:
    try:
        catalog = load_catalog(catalog_path)
    except (OSError, ValueError) as error:
        print(f"cannot read catalog {catalog_path}: {error}", file=sys.stderr)
        return 2

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
        db_actions, platform_map, has_schema_source = await _load_db_rows(db)
        report = build_report(catalog, db_actions, platform_map, only_platform=only_platform)
        _print_report(report, catalog, verbose)

        if apply:
            if report["unvalidatable"]:
                print(
                    f"ERROR: Cannot apply sync with {len(report['unvalidatable'])} unvalidatable schema(s). "
                    "Fix them in platform.json / api.js first.",
                    file=sys.stderr,
                )
                return 1

            stats = await apply_sync(
                db, report, has_schema_source=has_schema_source, force=force
            )
            print(
                f"\n[Apply Summary] inserted: {stats['inserted']}, "
                f"updated: {stats['updated']}, skipped (manual): {stats['skipped_manual']}"
            )
            return 0

    finally:
        await db.aclose()

    if check:
        blocking = (
            report["missing"] or report["conflicting"] or report["unvalidatable"]
        )
        return 1 if blocking else 0

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync generated action catalog with t_busi_action."
    )
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--catalog", default=str(_CATALOG_PATH))
    parser.add_argument("--platform", help="only sync/report this bs_platform_code")
    parser.add_argument("--verbose", action="store_true", help="show details of diff items")
    parser.add_argument("--apply", action="store_true", help="apply changes to database")
    parser.add_argument("--check", action="store_true", help="exit with code 1 if drift detected")
    parser.add_argument("--force", action="store_true", help="overwrite actions marked as manual")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(
            _run(
                args.config,
                Path(args.catalog),
                args.platform,
                args.verbose,
                args.apply,
                args.check,
                args.force,
            )
        )
    except Exception:
        print("sync_platform_actions failed", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
