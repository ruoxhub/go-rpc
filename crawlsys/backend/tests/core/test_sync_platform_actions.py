"""Tests for sync_platform_actions script and report generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
import pytest

# Add backend/scripts to sys.path if not present
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BACKEND_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_platform_actions as spa


def test_catalog_params_to_schema():
    params = {
        "keyword": {"type": "string", "required": True, "description": "Search keyword"},
        "page": {"type": "integer", "required": False, "default": 1},
    }
    schema_list = spa.catalog_params_to_schema(params)
    assert len(schema_list) == 2
    by_name = {item["name"]: item for item in schema_list}
    assert by_name["keyword"]["type"] == "string"
    assert by_name["keyword"]["required"] is True
    assert by_name["keyword"]["description"] == "Search keyword"
    assert by_name["page"]["type"] == "integer"
    assert by_name["page"]["required"] is False
    assert by_name["page"]["default"] == 1


def test_normalized_schema_validates_or_raises():
    valid_schema = [{"name": "uid", "type": "string", "required": True}]
    result = spa.normalized_schema(valid_schema)
    assert isinstance(result, dict)
    assert "properties" in result
    assert "uid" in result["properties"]

    invalid_schema = [{"name": "", "type": "string"}]
    with pytest.raises(Exception):
        spa.normalized_schema(invalid_schema)

    duplicate_schema = [{"name": "uid", "type": "string"}, {"name": "uid", "type": "int"}]
    with pytest.raises(Exception):
        spa.normalized_schema(duplicate_schema)


def test_schema_names_handles_list_and_dict():
    list_schema = [{"name": "foo", "type": "string"}, {"name": "bar"}]
    assert spa._schema_names(list_schema) == {"foo", "bar"}

    dict_schema = {"type": "object", "properties": {"k1": {}, "k2": {}}}
    assert spa._schema_names(dict_schema) == {"k1", "k2"}

    assert spa._schema_names(None) == set()



def test_build_report_missing_action():
    catalog = [
        {
            "group": "test_plat",
            "actions": {
                "search": {
                    "description": "Search posts",
                    "params": {"keyword": {"type": "string", "required": True}},
                }
            },
        }
    ]
    platform_map = {"test_plat": 10}
    db_actions = []

    report = spa.build_report(catalog, db_actions, platform_map)
    assert len(report["missing"]) == 1
    item = report["missing"][0]
    assert item["platform"] == "test_plat"
    assert item["action"] == "search"
    assert item["bs_id"] == 10
    assert item["has_schema"] is True
    assert len(report["writable"]) == 0
    assert len(report["conflicting"]) == 0
    assert len(report["unknown_group"]) == 0


def test_build_report_writable_empty_schema():
    catalog = [
        {
            "group": "test_plat",
            "actions": {
                "search": {
                    "description": "Search posts",
                    "params": {"keyword": {"type": "string", "required": True}},
                }
            },
        }
    ]
    platform_map = {"test_plat": 10}
    db_actions = [
        {
            "ba_id": 101,
            "platform_code": "test_plat",
            "action_name": "search",
            "params_schema": None,
            "schema_source": "synced",
            "bs_id": 10,
            "desc": "Old desc",
        }
    ]

    report = spa.build_report(catalog, db_actions, platform_map)
    assert len(report["missing"]) == 0
    assert len(report["writable"]) == 1
    assert report["writable"][0]["ba_id"] == 101
    assert report["writable"][0]["action"] == "search"
    assert len(report["conflicting"]) == 0


def test_build_report_conflicting_schema():
    catalog = [
        {
            "group": "test_plat",
            "actions": {
                "search": {
                    "description": "Search posts",
                    "params": {
                        "keyword": {"type": "string", "required": True},
                        "page": {"type": "integer"},
                    },
                }
            },
        }
    ]
    platform_map = {"test_plat": 10}
    # DB has only "keyword"
    stored_schema = json.dumps([{"name": "keyword", "type": "string"}])
    db_actions = [
        {
            "ba_id": 101,
            "platform_code": "test_plat",
            "action_name": "search",
            "params_schema": stored_schema,
            "schema_source": "manual",
            "bs_id": 10,
            "desc": "Old desc",
        }
    ]

    report = spa.build_report(catalog, db_actions, platform_map)
    assert len(report["missing"]) == 0
    assert len(report["writable"]) == 0
    assert len(report["conflicting"]) == 1
    item = report["conflicting"][0]
    assert item["action"] == "search"
    assert item["source"] == "manual"
    assert item["reason"] == "parameter names differ"


def test_build_report_unknown_group():
    catalog = [
        {
            "group": "non_existent_plat",
            "actions": {"detail": {}},
        }
    ]
    platform_map = {"known_plat": 1}
    db_actions = []

    report = spa.build_report(catalog, db_actions, platform_map)
    assert report["unknown_group"] == ["non_existent_plat"]
    assert len(report["missing"]) == 0


def test_build_report_unvalidatable_schema():
    catalog = [
        {
            "group": "test_plat",
            "actions": {
                "search": {
                    "description": "Invalid param name",
                    "params": {"": {"type": "string"}},
                }
            },
        }
    ]
    platform_map = {"test_plat": 10}
    db_actions = []

    report = spa.build_report(catalog, db_actions, platform_map)
    assert len(report["unvalidatable"]) == 1
    assert report["unvalidatable"][0]["platform"] == "test_plat"
    assert report["unvalidatable"][0]["action"] == "search"
    assert "InvalidActionParamSchema" in report["unvalidatable"][0]["reason"]
    assert len(report["missing"]) == 0


def test_build_report_only_platform_filter():
    catalog = [
        {
            "group": "plat_1",
            "actions": {"search": {}},
        },
        {
            "group": "plat_2",
            "actions": {"search": {}},
        },
    ]
    platform_map = {"plat_1": 1, "plat_2": 2}
    db_actions = []

    report = spa.build_report(catalog, db_actions, platform_map, only_platform="plat_1")
    assert len(report["missing"]) == 1
    assert report["missing"][0]["platform"] == "plat_1"



def test_build_report_idempotent():
    """When DB matches catalog exactly, report should have 0 missing/writable/conflicting."""
    catalog = [
        {
            "group": "test_plat",
            "actions": {
                "search": {
                    "description": "Search posts",
                    "params": {"keyword": {"type": "string", "required": True}},
                }
            },
        }
    ]
    platform_map = {"test_plat": 10}
    stored_schema = json.dumps([{"name": "keyword", "type": "string", "required": True}])
    db_actions = [
        {
            "ba_id": 101,
            "platform_code": "test_plat",
            "action_name": "search",
            "params_schema": stored_schema,
            "schema_source": "synced",
            "bs_id": 10,
            "desc": "Search posts",
        }
    ]

    report = spa.build_report(catalog, db_actions, platform_map)
    assert len(report["missing"]) == 0
    assert len(report["writable"]) == 0
    assert len(report["conflicting"]) == 0
    assert len(report["unvalidatable"]) == 0


@pytest.mark.asyncio
async def test_apply_sync_inserts_and_updates():
    mock_session = AsyncMock()
    mock_db = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_db.asession_scope.return_value = AsyncContextManager()

    report = {
        "missing": [
            {
                "platform": "test_plat",
                "bs_id": 10,
                "action": "search",
                "description": "Search desc",
                "schema": [{"name": "q", "type": "string"}],
            }
        ],
        "writable": [
            {
                "ba_id": 201,
                "action": "detail",
                "description": "Detail desc",
                "schema": [{"name": "id", "type": "string"}],
            }
        ],
        "conflicting": [
            {
                "ba_id": 301,
                "action": "update",
                "description": "Update desc",
                "schema": [{"name": "data", "type": "string"}],
                "source": "manual",
            },
            {
                "ba_id": 302,
                "action": "delete",
                "description": "Delete desc",
                "schema": [{"name": "id", "type": "string"}],
                "source": "synced",
            },
        ],
    }

    # 1. Without force: manual conflicting item is skipped
    stats = await spa.apply_sync(mock_db, report, has_schema_source=True, force=False)
    assert stats["inserted"] == 1
    assert stats["updated"] == 2  # 1 writable + 1 synced conflict
    assert stats["skipped_manual"] == 1

    # 2. With force: manual conflicting item is overwritten
    stats_forced = await spa.apply_sync(mock_db, report, has_schema_source=True, force=True)
    assert stats_forced["inserted"] == 1
    assert stats_forced["updated"] == 3  # 1 writable + 2 conflicts
    assert stats_forced["skipped_manual"] == 0


@pytest.mark.asyncio
async def test_apply_sync_compat_mode_when_columns_missing():
    mock_session = AsyncMock()
    mock_db = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_db.asession_scope.return_value = AsyncContextManager()

    report = {
        "missing": [
            {
                "platform": "test_plat",
                "bs_id": 10,
                "action": "search",
                "description": "Search desc",
                "schema": [{"name": "q", "type": "string"}],
            }
        ],
        "writable": [],
        "conflicting": [],
    }

    stats = await spa.apply_sync(mock_db, report, has_schema_source=False, force=False)
    assert stats["inserted"] == 1
    executed_sql = str(mock_session.execute.call_args[0][0])
    assert "ba_schema_source" not in executed_sql


@pytest.mark.asyncio
async def test_has_column_returns_boolean():
    mock_session = AsyncMock()
    mock_db = MagicMock()

    class AsyncContextManager:
        async def __aenter__(self):
            return mock_session
        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_db.asession_scope.return_value = AsyncContextManager()

    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_session.execute.return_value = mock_result

    exists = await spa._has_column(mock_db, "t_busi_action", "ba_schema_source")
    assert exists is True

    mock_result.scalar.return_value = None
    not_exists = await spa._has_column(mock_db, "t_busi_action", "ba_schema_source")
    assert not_exists is False


def test_cli_argument_parsing():
    parser = spa.build_parser()
    args = parser.parse_args(["--apply", "--force", "--platform", "bilibili", "--verbose"])
    assert args.apply is True
    assert args.force is True
    assert args.platform == "bilibili"
    assert args.verbose is True
    assert args.check is False

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0


@pytest.mark.asyncio
async def test_run_check_mode_returns_1_on_drift(monkeypatch, tmp_path):
    catalog_file = tmp_path / "test_catalog.json"
    catalog_file.write_text(json.dumps([{"group": "plat", "actions": {"act": {}}}]), encoding="utf-8")

    mock_db = MagicMock()
    mock_db.aconnect = AsyncMock()
    mock_db.aclose = AsyncMock()
    monkeypatch.setattr(spa, "SQLAlchemyDB", lambda **kwargs: mock_db)
    monkeypatch.setattr(spa, "_load_db_rows", AsyncMock(return_value=([], {"plat": 1}, True)))
    monkeypatch.setattr(spa.SchedulerConfig, "from_toml", MagicMock())

    # 1. check 模式下有 missing -> 退出码 1
    code = await spa._run(
        config_path="dummy.toml",
        catalog_path=catalog_file,
        only_platform=None,
        verbose=False,
        apply=False,
        check=True,
        force=False,
    )
    assert code == 1

    # 2. check 模式下无 missing -> 退出码 0
    monkeypatch.setattr(
        spa,
        "build_report",
        MagicMock(return_value={
            "missing": [], "conflicting": [], "writable": [],
            "unknown_group": [], "unvalidatable": [],
            "db_action_count": 1, "db_platform_count": 1,
        }),
    )
    clean_code = await spa._run(
        config_path="dummy.toml",
        catalog_path=catalog_file,
        only_platform=None,
        verbose=False,
        apply=False,
        check=True,
        force=False,
    )
    assert clean_code == 0

    # 3. apply 模式在存在 unvalidatable 时阻断 -> 退出码 1
    monkeypatch.setattr(
        spa,
        "build_report",
        MagicMock(return_value={
            "missing": [], "conflicting": [], "writable": [],
            "unknown_group": [], "unvalidatable": [{"platform": "plat", "action": "act", "reason": "err"}],
            "db_action_count": 0, "db_platform_count": 1,
        }),
    )
    apply_code = await spa._run(
        config_path="dummy.toml",
        catalog_path=catalog_file,
        only_platform=None,
        verbose=False,
        apply=True,
        check=False,
        force=False,
    )
    assert apply_code == 1

    # 4. catalog 文件不存在 -> 退出码 2
    err_code = await spa._run(
        config_path="dummy.toml",
        catalog_path=tmp_path / "non_existent.json",
        only_platform=None,
        verbose=False,
        apply=False,
        check=False,
        force=False,
    )
    assert err_code == 2


