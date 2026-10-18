"""Action synchronization service.

Aggregates Action declarations across:
1. browser-rpc (via scripts/generated/action-catalog.json or content/<id>)
2. python-rpc (via python-rpc/platforms/<id>)
and applies idempotent, safe updates into PostgreSQL public.t_busi_action.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from core.param_schema import normalize_action_param_schema
from storage import SQLAlchemyDB

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CATALOG_PATH = REPO_ROOT / "scripts" / "generated" / "action-catalog.json"
DEFAULT_PYTHON_RPC_DIR = REPO_ROOT / "python-rpc" / "platforms"

SELECT_PLATFORMS = """
SELECT bs_id, bs_platform_code FROM public.t_busi_platform
WHERE bs_platform_code IS NOT NULL
ORDER BY bs_platform_code
"""


def parse_python_platform(pdir: Path) -> dict[str, dict[str, Any]]:
    """Extract action definitions and docstrings from a python-rpc platform directory using AST."""
    init_file = pdir / "__init__.py"
    if not init_file.exists():
        return {}
    try:
        init_tree = ast.parse(init_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    action_to_func: dict[str, str | None] = {}
    for node in init_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ACTIONS":
                    if isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                func_name = None
                                if isinstance(v, ast.Attribute):
                                    func_name = v.attr
                                elif isinstance(v, ast.Name):
                                    func_name = v.id
                                action_to_func[k.value] = func_name

    api_file = pdir / "api.py"
    docstrings: dict[str, str] = {}
    if api_file.exists():
        try:
            api_tree = ast.parse(api_file.read_text(encoding="utf-8"))
            for node in api_tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node)
                    if doc:
                        docstrings[node.name] = doc
        except Exception:
            pass

    actions_meta: dict[str, dict[str, Any]] = {}
    for action_name, func_name in action_to_func.items():
        doc = docstrings.get(func_name, "") if func_name else ""
        summary = ""
        params_meta: dict[str, Any] = {}
        if doc:
            lines = [line.strip() for line in doc.splitlines() if line.strip()]
            if lines:
                summary = lines[0]
            in_params = False
            for line in lines[1:]:
                if re.match(r"^(参数|Parameters?)\s*[:：]", line):
                    in_params = True
                    continue
                if in_params and re.match(r"^(返回|Returns?)\s*[:：]", line):
                    break
                if in_params:
                    m = re.match(
                        r"^[-\*]\s*([a-zA-Z0-9_]+)(?:\s*/\s*[a-zA-Z0-9_]+)*\s*[:：]\s*(.*)",
                        line,
                    )
                    if m:
                        pname = m.group(1)
                        pdesc = m.group(2)
                        required = "必填" in pdesc or "required" in pdesc.lower()
                        ptype = "string"
                        if any(k in pdesc.lower() for k in ("int", "整数", "页码", "数量", "count", "limit")):
                            ptype = "number"
                        elif "bool" in pdesc.lower() or "是否" in pdesc:
                            ptype = "boolean"
                        params_meta[pname] = {
                            "type": ptype,
                            "required": required,
                            "description": pdesc,
                            "source": "python_docstring",
                        }
        actions_meta[action_name] = {
            "mode": "unary",
            "description": summary or f"{pdir.name} {action_name}",
            "params": params_meta,
            "example": {},
        }
    return actions_meta


def scan_python_rpc_platforms(python_rpc_dir: Path) -> dict[str, dict[str, Any]]:
    """Scan all platform directories under python-rpc/platforms."""
    if not python_rpc_dir.is_dir():
        return {}
    results: dict[str, dict[str, Any]] = {}
    for pdir in sorted(python_rpc_dir.iterdir()):
        if not pdir.is_dir() or pdir.name.startswith(("_", ".")):
            continue
        actions = parse_python_platform(pdir)
        if actions:
            results[pdir.name] = {
                "id": pdir.name,
                "group": pdir.name,
                "actions": actions,
            }
    return results


def load_catalog(path: Path) -> list[dict[str, Any]]:
    """Load browser-rpc generated catalog."""
    with path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    if not isinstance(catalog, list):
        raise ValueError("action catalog must be a list")
    return catalog


def load_unified_catalog(
    catalog_path: Path | None = None,
    python_rpc_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge browser-rpc action-catalog.json and python-rpc platforms into a single catalog."""
    c_path = catalog_path or DEFAULT_CATALOG_PATH
    py_dir = python_rpc_dir or DEFAULT_PYTHON_RPC_DIR

    base_catalog = []
    if c_path.is_file():
        base_catalog = load_catalog(c_path)
    by_group: dict[str, dict[str, Any]] = {}
    for item in base_catalog:
        grp = item.get("group") or item.get("id")
        if grp:
            by_group[grp] = item

    py_platforms = scan_python_rpc_platforms(py_dir)
    for group, py_item in py_platforms.items():
        if group not in by_group:
            by_group[group] = py_item
        else:
            existing_actions = by_group[group].setdefault("actions", {})
            for act_name, act_meta in py_item["actions"].items():
                if act_name not in existing_actions:
                    existing_actions[act_name] = act_meta
                else:
                    curr_desc = existing_actions[act_name].get("description") or ""
                    py_desc = act_meta.get("description") or ""
                    if (not curr_desc or curr_desc.endswith(f" {act_name}")) and py_desc:
                        existing_actions[act_name]["description"] = py_desc

    return [by_group[g] for g in sorted(by_group.keys())]


def catalog_params_to_schema(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert catalog params into legacy list shape for t_busi_action."""
    items = []
    for name in sorted(params):
        definition = params[name]
        items.append(
            {
                "name": name,
                "type": definition.get("type", "string"),
                "required": bool(definition.get("required")),
                "default": definition.get("default"),
                "description": definition.get("description", ""),
            }
        )
    return items


def normalized_schema(schema: Any) -> dict[str, Any] | bool | None:
    """Validate and round-trip schema via normalize_action_param_schema."""
    return normalize_action_param_schema(schema)


def _schema_names(schema: Any) -> set[str]:
    if isinstance(schema, list):
        return {
            item["name"] for item in schema if isinstance(item, dict) and "name" in item
        }
    if isinstance(schema, dict):
        return set(schema.get("properties", {}))
    return set()


async def _has_column(db: SQLAlchemyDB, table_name: str, column_name: str) -> bool:
    """Check if a column exists in public schema."""
    query = text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table_name AND column_name = :column_name"
    )
    async with db.asession_scope() as session:
        result = await session.execute(query, {"table_name": table_name, "column_name": column_name})
        return result.scalar() is not None


async def _load_db_rows(db: SQLAlchemyDB) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    has_schema_source = await _has_column(db, "t_busi_action", "ba_schema_source")

    select_actions = (
        "SELECT a.ba_id, p.bs_platform_code, a.ba_action, a.ba_params_schema, "
        f"{'a.ba_schema_source' if has_schema_source else 'NULL as ba_schema_source'}, "
        "p.bs_id, a.ba_desc "
        "FROM public.t_busi_action a "
        "JOIN public.t_busi_platform p ON p.bs_id = a.bs_id "
        "ORDER BY p.bs_platform_code, a.ba_action"
    )

    async with db.asession_scope() as session:
        action_rows = list((await session.execute(text(select_actions))).fetchall())
        platform_rows = list((await session.execute(text(SELECT_PLATFORMS))).fetchall())

    platform_map = {row[1]: row[0] for row in platform_rows if row[1]}
    db_actions = [
        {
            "ba_id": row[0],
            "platform_code": row[1],
            "action_name": row[2],
            "params_schema": row[3],
            "schema_source": row[4],
            "bs_id": row[5],
            "desc": row[6],
        }
        for row in action_rows
    ]
    return db_actions, platform_map, has_schema_source


def build_report(
    catalog: list[dict[str, Any]],
    db_actions: list[dict[str, Any]],
    platform_map: dict[str, int],
    *,
    only_platform: str | None = None,
) -> dict[str, Any]:
    """Pure in-memory diff. Returns missing / conflicting / writable buckets."""
    known_codes = set(platform_map.keys())
    db_by_platform: dict[str, dict[str, dict[str, Any]]] = {}
    for item in db_actions:
        code = item["platform_code"]
        if code:
            db_by_platform.setdefault(code, {})[item["action_name"]] = item

    missing: list[dict[str, Any]] = []
    conflicting: list[dict[str, Any]] = []
    writable: list[dict[str, Any]] = []
    unknown_group: list[str] = []
    unvalidatable: list[dict[str, Any]] = []

    for entry in catalog:
        group = entry.get("group") or entry.get("id")
        if only_platform and group != only_platform:
            continue
        if group not in known_codes:
            unknown_group.append(group)
            continue
        bs_id = platform_map[group]
        known = db_by_platform.get(group, {})
        actions_dict = entry.get("actions", {})
        for action_name in sorted(actions_dict):
            action = actions_dict[action_name]
            raw_params = action.get("params", {})
            schema_list = catalog_params_to_schema(raw_params) if raw_params else None
            desc = action.get("description")

            if schema_list:
                try:
                    normalized_schema(schema_list)
                except Exception as error:
                    unvalidatable.append(
                        {
                            "platform": group,
                            "action": action_name,
                            "reason": f"{type(error).__name__}: {error}",
                        }
                    )
                    continue

            if action_name not in known:
                missing.append(
                    {
                        "platform": group,
                        "bs_id": bs_id,
                        "action": action_name,
                        "description": desc,
                        "schema": schema_list,
                        "has_schema": bool(schema_list),
                    }
                )
                continue

            stored_item = known[action_name]
            ba_id = stored_item["ba_id"]
            stored = stored_item["params_schema"]
            stored_source = stored_item.get("schema_source") or "synced"

            if not schema_list:
                continue

            if stored is None:
                writable.append(
                    {
                        "platform": group,
                        "bs_id": bs_id,
                        "ba_id": ba_id,
                        "action": action_name,
                        "description": desc,
                        "schema": schema_list,
                        "reason": "empty",
                    }
                )
                continue

            try:
                decoded = json.loads(stored)
            except (json.JSONDecodeError, TypeError):
                conflicting.append(
                    {
                        "platform": group,
                        "bs_id": bs_id,
                        "ba_id": ba_id,
                        "action": action_name,
                        "description": desc,
                        "schema": schema_list,
                        "source": stored_source,
                        "reason": "stored schema is not valid JSON",
                    }
                )
                continue

            if _schema_names(decoded) != _schema_names(schema_list):
                conflicting.append(
                    {
                        "platform": group,
                        "bs_id": bs_id,
                        "ba_id": ba_id,
                        "action": action_name,
                        "description": desc,
                        "schema": schema_list,
                        "source": stored_source,
                        "reason": "parameter names differ",
                        "stored": sorted(_schema_names(decoded)),
                        "catalog": sorted(_schema_names(schema_list)),
                    }
                )

    return {
        "missing": missing,
        "conflicting": conflicting,
        "writable": writable,
        "unknown_group": sorted(set(unknown_group)),
        "unvalidatable": unvalidatable,
        "db_action_count": len(db_actions),
        "db_platform_count": len(known_codes),
    }


async def apply_sync(
    db: SQLAlchemyDB,
    report: dict[str, Any],
    *,
    has_schema_source: bool,
    force: bool = False,
) -> dict[str, Any]:
    """Apply sync changes into database in a single transaction."""
    stats = {"inserted": 0, "updated": 0, "skipped_manual": 0}
    details: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    insert_sql_full = text(
        "INSERT INTO public.t_busi_action "
        "(bs_id, ba_action, ba_desc, ba_params_schema, ba_enabled, ba_sample_safe, ba_schema_source, ba_synced_at) "
        "VALUES (:bs_id, :ba_action, :ba_desc, :ba_params_schema, true, false, 'synced', :ba_synced_at)"
    )
    insert_sql_compat = text(
        "INSERT INTO public.t_busi_action "
        "(bs_id, ba_action, ba_desc, ba_params_schema, ba_enabled, ba_sample_safe) "
        "VALUES (:bs_id, :ba_action, :ba_desc, :ba_params_schema, true, false)"
    )

    update_sql_full = text(
        "UPDATE public.t_busi_action "
        "SET ba_params_schema = :ba_params_schema, "
        "    ba_desc = COALESCE(:ba_desc, ba_desc), "
        "    ba_schema_source = 'synced', "
        "    ba_synced_at = :ba_synced_at "
        "WHERE ba_id = :ba_id"
    )
    update_sql_compat = text(
        "UPDATE public.t_busi_action "
        "SET ba_params_schema = :ba_params_schema, "
        "    ba_desc = COALESCE(:ba_desc, ba_desc) "
        "WHERE ba_id = :ba_id"
    )

    insert_stmt = insert_sql_full if has_schema_source else insert_sql_compat
    update_stmt = update_sql_full if has_schema_source else update_sql_compat

    async with db.asession_scope() as session:
        # 1. Handle missing (INSERT)
        for item in report["missing"]:
            schema_json = json.dumps(item["schema"], ensure_ascii=False) if item["schema"] else None
            params = {
                "bs_id": item["bs_id"],
                "ba_action": item["action"],
                "ba_desc": item["description"],
                "ba_params_schema": schema_json,
                "ba_synced_at": now,
            }
            await session.execute(insert_stmt, params)
            stats["inserted"] += 1
            details.append(
                {
                    "platform": item.get("platform", ""),
                    "action": item.get("action", ""),
                    "status": "inserted",
                    "reason": None,
                }
            )

        # 2. Handle writable (UPDATE empty schema)
        for item in report["writable"]:
            schema_json = json.dumps(item["schema"], ensure_ascii=False) if item["schema"] else None
            params = {
                "ba_id": item["ba_id"],
                "ba_desc": item["description"],
                "ba_params_schema": schema_json,
                "ba_synced_at": now,
            }
            await session.execute(update_stmt, params)
            stats["updated"] += 1
            details.append(
                {
                    "platform": item.get("platform", ""),
                    "action": item.get("action", ""),
                    "status": "updated",
                    "reason": "empty_schema_filled",
                }
            )

        # 3. Handle conflicting
        for item in report["conflicting"]:
            source = item.get("source")
            if source == "manual" and not force:
                stats["skipped_manual"] += 1
                details.append(
                    {
                        "platform": item.get("platform", ""),
                        "action": item.get("action", ""),
                        "status": "skipped_manual",
                        "reason": "protected manual schema",
                    }
                )
                continue
            schema_json = json.dumps(item["schema"], ensure_ascii=False) if item["schema"] else None
            params = {
                "ba_id": item["ba_id"],
                "ba_desc": item["description"],
                "ba_params_schema": schema_json,
                "ba_synced_at": now,
            }
            await session.execute(update_stmt, params)
            stats["updated"] += 1
            details.append(
                {
                    "platform": item.get("platform", ""),
                    "action": item.get("action", ""),
                    "status": "updated",
                    "reason": "schema_updated",
                }
            )

    stats["details"] = details
    return stats


async def sync_actions(
    db: SQLAlchemyDB,
    *,
    platform_id: int | None = None,
    force: bool = False,
    catalog_path: Path | None = None,
    python_rpc_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute action synchronization for all or a specific platform."""
    catalog = load_unified_catalog(catalog_path=catalog_path, python_rpc_dir=python_rpc_dir)
    db_actions, platform_map, has_schema_source = await _load_db_rows(db)

    target_code: str | None = None
    if platform_id is not None:
        for code, pid in platform_map.items():
            if pid == platform_id:
                target_code = code
                break
        if target_code is None:
            raise ValueError(f"平台 ID {platform_id} 不存在或未配置有效平台代码")

    report = build_report(
        catalog,
        db_actions,
        platform_map,
        only_platform=target_code,
    )

    stats = await apply_sync(
        db,
        report,
        has_schema_source=has_schema_source,
        force=force,
    )

    return {
        "inserted_count": stats["inserted"],
        "updated_count": stats["updated"],
        "skipped_manual_count": stats["skipped_manual"],
        "total_synced": stats["inserted"] + stats["updated"],
        "unknown_groups": report.get("unknown_group", []),
        "details": stats.get("details", []),
    }
