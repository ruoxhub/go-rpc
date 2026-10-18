"""Unit tests for ActionSyncService and unified catalog aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from services.action_sync import (
    apply_sync,
    build_report,
    load_unified_catalog,
    parse_python_platform,
    scan_python_rpc_platforms,
    sync_actions,
)


def test_parse_python_platform_with_ast(tmp_path: Path):
    plat_dir = tmp_path / "mock_plat"
    plat_dir.mkdir()
    (plat_dir / "__init__.py").write_text(
        "from . import api\nACTIONS = {'testAction': api.test_func}\n",
        encoding="utf-8",
    )
    (plat_dir / "api.py").write_text(
        'def test_func(params=None):\n    """测试接口功能说明。\n\n    参数：\n    - keyword: 搜索词（必填）\n    - page: 页码（默认 1）\n    """\n    return {}\n',
        encoding="utf-8",
    )

    actions = parse_python_platform(plat_dir)
    assert "testAction" in actions
    act = actions["testAction"]
    assert act["description"] == "测试接口功能说明。"
    assert "keyword" in act["params"]
    assert act["params"]["keyword"]["required"] is True
    assert "page" in act["params"]
    assert act["params"]["page"]["type"] == "number"


def test_load_unified_catalog_merges_browser_and_python(tmp_path: Path):
    catalog_path = tmp_path / "action-catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "id": "bilibili",
                    "group": "bilibili",
                    "actions": {
                        "getUserInfo": {
                            "mode": "unary",
                            "description": "获取用户信息",
                            "params": {
                                "user_id": {
                                    "type": "string",
                                    "required": True,
                                    "description": "用户 MID",
                                }
                            },
                            "example": {},
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    py_dir = tmp_path / "python_platforms"
    py_dir.mkdir()
    pypi_dir = py_dir / "pypi"
    pypi_dir.mkdir()
    (pypi_dir / "__init__.py").write_text(
        "from . import api\nACTIONS = {'getPackage': api.getPackage}\n",
        encoding="utf-8",
    )
    (pypi_dir / "api.py").write_text(
        'def getPackage(params=None):\n    """获取包详情\n\n    参数：\n    - name: 包名（必填）\n    """\n    return {}\n',
        encoding="utf-8",
    )

    unified = load_unified_catalog(catalog_path=catalog_path, python_rpc_dir=py_dir)
    by_group = {item["group"]: item for item in unified}

    assert "bilibili" in by_group
    assert "getUserInfo" in by_group["bilibili"]["actions"]

    assert "pypi" in by_group
    assert "getPackage" in by_group["pypi"]["actions"]


@pytest.mark.asyncio
async def test_sync_actions_workflow_with_mock_db(tmp_path: Path):
    catalog_path = tmp_path / "action-catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "id": "bilibili",
                    "group": "bilibili",
                    "actions": {
                        "getUserInfo": {
                            "description": "获取用户信息",
                            "params": {"user_id": {"type": "string", "required": True}},
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    mock_session = AsyncMock()
    mock_db = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_db.asession_scope.return_value = AsyncContextManager()

    # Mock execute returns:
    # 1. _has_column -> scalar = True
    # 2. _load_db_rows (actions) -> fetchall = []
    # 3. _load_db_rows (platforms) -> fetchall = [(1, "bilibili")]
    # 4. apply_sync (insert) -> execute
    res_col = MagicMock()
    res_col.scalar.return_value = True

    res_actions = MagicMock()
    res_actions.fetchall.return_value = []

    res_platforms = MagicMock()
    res_platforms.fetchall.return_value = [(1, "bilibili")]

    mock_session.execute.side_effect = [
        res_col,
        res_actions,
        res_platforms,
        None,  # insert statement
    ]

    result = await sync_actions(
        mock_db,
        platform_id=1,
        force=False,
        catalog_path=catalog_path,
        python_rpc_dir=tmp_path / "empty_py",
    )

    assert result["inserted_count"] == 1
    assert result["updated_count"] == 0
    assert result["total_synced"] == 1
    assert len(result["details"]) == 1
    assert result["details"][0]["action"] == "getUserInfo"
    assert result["details"][0]["status"] == "inserted"
