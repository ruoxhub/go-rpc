import json
from pathlib import Path

import pytest

from models import TkCategory
from scripts.import_tk_shop_categories import flatten_category_tree


def test_tk_category_schema_has_business_key_and_parent_index():
    table = TkCategory.__table__

    assert table.schema == "public"
    assert table.c.category_id.unique is True
    assert table.c.parent_category_id.foreign_keys
    assert "idx_tk_category_parent_sort" in {index.name for index in table.indexes}


def test_flatten_category_tree_preserves_hierarchy_and_order():
    rows = flatten_category_tree(
        {
            "data": {
                "global.category.tree": [
                    {
                        "label": "一级",
                        "value": "1",
                        "children": [
                            {"label": "二级 A", "value": "2"},
                            {"label": "二级 B", "value": "3"},
                        ],
                    }
                ]
            }
        }
    )

    assert rows == [
        {"category_id": "1", "label": "一级", "parent_category_id": None, "level": 1, "sort_order": 0},
        {"category_id": "2", "label": "二级 A", "parent_category_id": "1", "level": 2, "sort_order": 0},
        {"category_id": "3", "label": "二级 B", "parent_category_id": "1", "level": 2, "sort_order": 1},
    ]


def test_flatten_project_category_data():
    data_path = Path(__file__).resolve().parents[2] / "data" / "tk_shop_category.json"
    if not data_path.is_file():
        pytest.skip(f"{data_path} not found in workspace")
    rows = flatten_category_tree(json.loads(data_path.read_text(encoding="utf-8")))

    assert rows
    assert {row["level"] for row in rows} == {1, 2, 3}
    assert len({row["category_id"] for row in rows}) == len(rows)


def test_flatten_rejects_duplicate_category_id():
    payload = {
        "data": {
            "global.category.tree": [
                {"label": "A", "value": "1"},
                {"label": "B", "value": "1"},
            ]
        }
    }

    with pytest.raises(ValueError, match="分类 ID 重复: 1"):
        flatten_category_tree(payload)
