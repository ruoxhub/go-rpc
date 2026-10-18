import pytest
from scripts.migrate_task_config import parse_params_columns, build_config


def test_parse_params_columns_empty():
    assert parse_params_columns(None, "id") == ({}, [])
    assert parse_params_columns("", "id") == ({}, [])


def test_parse_params_columns_simple():
    pm, extras = parse_params_columns("uid, mid, name", "uid")
    assert pm == {"uid": "uid", "mid": "mid", "name": "name"}
    assert extras == ["mid", "name"]


def test_parse_params_columns_with_alias():
    pm, extras = parse_params_columns("uid as user_id, mid", "uid")
    assert pm == {"uid": "user_id", "mid": "mid"}
    assert extras == ["mid"]


def test_parse_params_columns_rejects_bad_identifier():
    with pytest.raises(ValueError):
        parse_params_columns("user-id, name", "id")
    with pytest.raises(ValueError):
        parse_params_columns("user; DROP TABLE", "id")


def test_build_config_no_find_work():
    row = {"find_work": None, "result_column": None,
           "post_update_column": None, "post_update_table": None}
    cfg = build_config(row)
    assert cfg == {"source": None, "sink": {"mode": "auto"}}


def test_build_config_full():
    row = {
        "find_work": {
            "ref_table": "t_user",
            "ref_where": "is_crawled = false",
            "params_columns": "uid as user_id, mid",
            "entity_column": "uid",
        },
        "result_column": "profile_json",
        "post_update_column": "is_crawled",
        "post_update_table": "t_user",
    }
    cfg = build_config(row)
    assert cfg["source"]["table"] == "t_user"
    assert cfg["source"]["key_column"] == "uid"
    assert cfg["source"]["param_map"] == {"uid": "user_id", "mid": "mid"}
    assert cfg["source"]["extra_columns"] == ["mid"]
    assert cfg["source"]["where"] == "is_crawled = false"
    assert cfg["sink"]["mode"] == "auto"
    assert cfg["sink"]["result_column"] == "profile_json"
    assert cfg["sink"]["mark_done_column"] == "is_crawled"
    assert cfg["sink"]["mark_done_table"] == "t_user"


def test_build_config_find_work_missing_keys():
    row = {"find_work": {"ref_table": "t"},  # no entity_column
           "result_column": None, "post_update_column": None, "post_update_table": None}
    cfg = build_config(row)
    assert cfg["source"] is None
    assert cfg["sink"] == {"mode": "auto"}
