import json

import pytest
from models.task_config import TaskConfig, TaskConfigType


def test_bind_param_none():
    t = TaskConfigType()
    assert t.process_bind_param(None, None) is None


def test_bind_param_from_pydantic():
    t = TaskConfigType()
    cfg = TaskConfig.model_validate({"source": {"table": "t", "key_column": "id"}})
    out = t.process_bind_param(cfg, None)
    # dialect=None 时返回 dict（适配 JSONB），或兼容旧字符串
    loaded = json.loads(out) if isinstance(out, str) else out
    assert loaded == {"source": {"type": "database", "table": "t", "key_column": "id"}}


def test_bind_param_does_not_serialize_omitted_default_sink():
    config_type = TaskConfigType()
    config = TaskConfig.model_validate({"source": {"table": "t", "key_column": "id"}})

    bound = config_type.process_bind_param(config, None)

    assert "sink" not in bound


def test_bind_param_preserves_explicit_database_sink_discriminator():
    config_type = TaskConfigType()
    config = TaskConfig.model_validate({"sink": {"mode": "direct"}})

    bound = config_type.process_bind_param(config, None)

    assert bound == {"sink": {"type": "database", "mode": "direct"}}


def test_bind_param_from_dict():
    t = TaskConfigType()
    out = t.process_bind_param({"sink": {"mode": "direct"}}, None)
    loaded = json.loads(out) if isinstance(out, str) else out
    assert loaded == {"sink": {"mode": "direct"}}


def test_result_value_none():
    t = TaskConfigType()
    assert t.process_result_value(None, None) is None


def test_result_value_from_string():
    t = TaskConfigType()
    raw = json.dumps({"source": {"table": "t", "key_column": "id"}, "sink": {"mode": "standard"}})
    cfg = t.process_result_value(raw, None)
    assert cfg.source.table == "t"
    assert cfg.sink.mode == "standard"


def test_result_value_from_dict():
    t = TaskConfigType()
    cfg = t.process_result_value({"sink": {"mode": "none"}}, None)
    assert cfg.executor == "rpc_crawl"
    assert cfg.sink.mode == "none"


@pytest.mark.parametrize("legacy_executor", [None, "", "   "])
def test_result_value_normalizes_legacy_empty_executor(legacy_executor):
    t = TaskConfigType()
    cfg = t.process_result_value({"executor": legacy_executor}, None)
    assert cfg.executor == "rpc_crawl"


def test_video_download_json_roundtrip():
    t = TaskConfigType()
    cfg = TaskConfig.model_validate(
        {
            "executor": "video_download",
            "download": {"batch_size": 20, "min_grade": 2, "use_proxy": False},
        }
    )
    bound = t.process_bind_param(cfg, None)
    restored = t.process_result_value(bound, None)
    assert restored == cfg


def test_bind_param_invalid_type():
    t = TaskConfigType()
    with pytest.raises(TypeError, match="got str"):
        t.process_bind_param("bad", None)


class _FakeDialect:
    def __init__(self, name: str):
        self.name = name


def test_bind_param_returns_dict_for_json_dialects():
    """验证关键修复：对 PostgreSQL JSONB 返回原生 dict，避免 ::VARCHAR 错误。"""
    t = TaskConfigType()
    cfg = TaskConfig.model_validate({"source": {"table": "t_busi", "key_column": "id"}})

    for name in ("postgresql", "mysql", "sqlite"):
        d = _FakeDialect(name)
        out = t.process_bind_param(cfg, d)
        assert isinstance(out, dict), f"{name} should return dict for native JSON column"
        assert out["source"]["table"] == "t_busi"

    # Text fallback 仍返回 str
    d_text = _FakeDialect("mssql")
    out_text = t.process_bind_param(cfg, d_text)
    assert isinstance(out_text, str)
    assert "t_busi" in out_text


@pytest.mark.parametrize("payload", [
    {
        "source": {
            "type": "redis_stream",
            "stream": "crawler:{detail}:stream",
            "group": "detail",
            "dead_letter_stream": "crawler:{detail}:dlq",
        },
        "sink": {
            "type": "redis_stream",
            "stream": "crawler:{next}:stream",
            "param_map": {"content_id": "content_id"},
        },
    },
    {
        "execution_mode": "publish_source",
        "source": {
            "type": "database",
            "table": "t_busi_search_keyword",
            "key_column": "id",
            "completion": {"column": "published"},
        },
        "sink": {
            "type": "redis_stream",
            "stream": "crawler:{search}:stream",
            "param_map": {"keyword": "keyword"},
        },
    },
])
def test_io_discriminators_survive_task_config_type_bind_and_result(payload):
    config_type = TaskConfigType()
    expected = TaskConfig.model_validate(payload)
    bound = config_type.process_bind_param(expected, None)
    assert bound["source"]["type"] == expected.source.type
    assert bound["sink"]["type"] == expected.sink.type
    restored = config_type.process_result_value(bound, None)
    assert restored == expected


def test_redis_bind_keeps_defaults_compressed_while_preserving_discriminators():
    config_type = TaskConfigType()
    config = TaskConfig.model_validate({
        "source": {
            "type": "redis_stream",
            "stream": "crawler:{detail}:stream",
            "group": "detail",
            "dead_letter_stream": "crawler:{detail}:dlq",
        },
        "sink": {
            "type": "redis_stream",
            "stream": "crawler:{next}:stream",
            "param_map": {"content_id": "content_id"},
        },
    })

    bound = config_type.process_bind_param(config, None)

    assert bound["source"] == {
        "type": "redis_stream",
        "stream": "crawler:{detail}:stream",
        "group": "detail",
        "dead_letter_stream": "crawler:{detail}:dlq",
    }
    assert bound["sink"] == {
        "type": "redis_stream",
        "stream": "crawler:{next}:stream",
        "param_map": {"content_id": "content_id"},
    }
    assert "execution_mode" not in bound
