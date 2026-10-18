"""将 data/tk_shop_category.json 幂等导入 public.tk_category。"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_APP_DIR = str(_BACKEND_DIR / "app")
if _APP_DIR not in sys.path:
    sys.path.append(_APP_DIR)

from core.config import SchedulerConfig
from models import TkCategory
from storage import SQLAlchemyDB


def flatten_category_tree(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """按父节点优先顺序将分类树展开为数据库行。"""
    try:
        roots = payload["data"]["global.category.tree"]
    except (KeyError, TypeError) as exc:
        raise ValueError("JSON 缺少 data.global.category.tree") from exc
    if not isinstance(roots, list):
        raise ValueError("data.global.category.tree 必须是数组")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(nodes: list[Any], parent_id: str | None, level: int) -> None:
        for sort_order, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"第 {level} 层分类节点必须是对象")
            category_id = str(node.get("value", "")).strip()
            label = str(node.get("label", "")).strip()
            if not category_id or not label:
                raise ValueError(f"分类节点缺少 value 或 label: {node!r}")
            if category_id in seen:
                raise ValueError(f"分类 ID 重复: {category_id}")
            seen.add(category_id)
            rows.append(
                {
                    "category_id": category_id,
                    "label": label,
                    "parent_category_id": parent_id,
                    "level": level,
                    "sort_order": sort_order,
                }
            )
            children = node.get("children") or []
            if not isinstance(children, list):
                raise ValueError(f"分类 {category_id} 的 children 必须是数组")
            visit(children, category_id, level + 1)

    visit(roots, None, 1)
    return rows


async def import_categories(config_path: Path, data_path: Path) -> int:
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    rows = flatten_category_tree(payload)
    config = SchedulerConfig.from_toml(str(config_path))
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
        await db.ainit_db()
        statement = insert(TkCategory).on_conflict_do_update(
            index_elements=[TkCategory.category_id],
            set_={
                "label": insert(TkCategory).excluded.label,
                "parent_category_id": insert(TkCategory).excluded.parent_category_id,
                "level": insert(TkCategory).excluded.level,
                "sort_order": insert(TkCategory).excluded.sort_order,
            },
        )
        async with db.asession_scope() as session:
            await session.execute(statement, rows)
        return len(rows)
    finally:
        await db.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 TikTok Shop 分类标签")
    parser.add_argument("--config", type=Path, default=_BACKEND_DIR / "config.toml")
    parser.add_argument(
        "--file", type=Path, default=_BACKEND_DIR / "data" / "tk_shop_category.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    count = asyncio.run(import_categories(args.config, args.file))
    print(f"已导入 {count} 条 TikTok Shop 分类标签")


if __name__ == "__main__":
    main()
