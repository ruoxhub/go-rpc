import pytest
from pydantic import ValidationError
from models.task_config import (
    DatabaseSinkConfig,
    DatabaseSourceCompletionConfig,
    DatabaseSourceConfig,
    PaginationConfig,
    RedisStreamSinkConfig,
    RedisStreamSourceConfig,
    SinkConfig,
    SourceConfig,
    TaskConfig,
    VideoAnalysisTaskConfig,
    VideoCleanTaskConfig,
    VideoDownloadTaskConfig,
)


def test_empty_config_defaults():
    cfg = TaskConfig.model_validate({})
    assert cfg.executor == "rpc_crawl"
    assert cfg.source is None
    assert cfg.sink.mode == "auto"


def test_video_download_config_parses():
    cfg = TaskConfig.model_validate(
        {
            "executor": "video_download",
            "download": {"batch_size": 20, "min_grade": 2, "use_proxy": False},
        }
    )
    assert cfg.executor == "video_download"
    assert cfg.download.batch_size == 20
    assert cfg.download.min_grade == 2
    assert cfg.download.use_proxy is False


def test_download_retry_config_defaults_and_bounds():
    config = VideoDownloadTaskConfig()
    assert config.max_attempts == 5
    assert config.claim_timeout_seconds == 1800
    assert config.retry_base_seconds == 60
    assert config.retry_max_seconds == 3600
    with pytest.raises(ValidationError):
        VideoDownloadTaskConfig(max_attempts=0)
    with pytest.raises(ValidationError):
        VideoDownloadTaskConfig(retry_base_seconds=120, retry_max_seconds=60)


def test_unknown_executor_rejected():
    with pytest.raises(ValidationError):
        TaskConfig.model_validate({"executor": "shell_script"})


@pytest.mark.parametrize("legacy_executor", [None, "", "   "])
def test_legacy_empty_executor_defaults_to_rpc_crawl(legacy_executor):
    cfg = TaskConfig.model_validate({"executor": legacy_executor})
    assert cfg.executor == "rpc_crawl"


def test_executor_config_defaults():
    cfg = TaskConfig()
    assert cfg.pagination is None
    assert cfg.clean is None
    assert cfg.download is None
    assert cfg.analysis is None

    assert PaginationConfig() == PaginationConfig(
        cursor_param="cursor",
        initial_cursor=0,
        max_pages=0,
        response_cursor_keys=["nextCursor", "next_cursor", "maxCursor", "cursor"],
    )
    assert VideoCleanTaskConfig() == VideoCleanTaskConfig(platforms=[], batch_size=None)
    assert VideoDownloadTaskConfig() == VideoDownloadTaskConfig(batch_size=50, min_grade=3, use_proxy=True, rps=0)
    assert VideoAnalysisTaskConfig() == VideoAnalysisTaskConfig(
        batch_size=10, max_attempts=3, llm_model_id=None, review_route=None
    )


def test_analysis_model_override_round_trips_and_requires_positive_id():
    raw = {"executor": "video_analysis", "analysis": {"llm_model_id": 17}}
    assert TaskConfig.model_validate(raw).model_dump(exclude_defaults=True) == raw
    with pytest.raises(ValidationError):
        VideoAnalysisTaskConfig(llm_model_id=0)


@pytest.mark.parametrize("review_route", ["R", "G", None])
def test_analysis_review_route_round_trips_without_defaulting(review_route):
    config = VideoAnalysisTaskConfig(review_route=review_route)

    assert config.review_route == review_route
    assert VideoAnalysisTaskConfig.model_validate(
        config.model_dump()
    ).review_route == review_route


def test_analysis_review_route_rejects_unknown_values():
    with pytest.raises(ValidationError):
        VideoAnalysisTaskConfig(review_route="B")


@pytest.mark.parametrize(
    ("config_type", "field", "value"),
    [
        (PaginationConfig, "max_pages", -1),
        (VideoCleanTaskConfig, "batch_size", 0),
        (VideoDownloadTaskConfig, "batch_size", 0),
        (VideoDownloadTaskConfig, "batch_size", 501),
        (VideoDownloadTaskConfig, "min_grade", 0),
        (VideoDownloadTaskConfig, "min_grade", 4),
        (VideoDownloadTaskConfig, "rps", -0.1),
        (VideoAnalysisTaskConfig, "batch_size", 0),
        (VideoAnalysisTaskConfig, "batch_size", 101),
        (VideoAnalysisTaskConfig, "max_attempts", 0),
    ],
)
def test_executor_config_bounds(config_type, field, value):
    with pytest.raises(ValidationError):
        config_type(**{field: value})


def test_source_required_fields():
    with pytest.raises(ValidationError):
        SourceConfig()  # missing table/key_column
    s = SourceConfig(table="t", key_column="id")
    assert s.param_map == {}
    assert s.extra_columns == []


def test_sink_mode_literal():
    for m in ("standard", "direct", "none", "auto"):
        assert SinkConfig(mode=m).mode == m
    with pytest.raises(ValidationError):
        SinkConfig(mode="invalid")


def test_full_config_roundtrip():
    raw = {
        "source": {
            "table": "t_user",
            "where": "is_crawled = false",
            "key_column": "user_id",
            "param_map": {"uid": "user_id"},
            "extra_columns": ["mid"],
            # filter_by_platform default True omitted: exclude_defaults drops it
        },
        "sink": {
            "mode": "direct",
            "result_column": "profile_json",
            "mark_done_column": "is_crawled",
        },
    }
    cfg = TaskConfig.model_validate(raw)
    assert cfg.source.table == "t_user"
    assert cfg.source.filter_by_platform is True
    assert cfg.sink.result_column == "profile_json"
    # exclude_defaults so newly added order_by/limit defaults do not break old fixtures
    assert cfg.model_dump(exclude_none=True, exclude_defaults=True) == raw


def test_pagination_cursor_keys_roundtrip():
    raw = {
        "pagination": {
            "cursor_param": "offset",
            "initial_cursor": 10,
            "max_pages": 3,
            "response_cursor_keys": ["cursor", "maxCursor"],
        }
    }
    assert TaskConfig.model_validate(raw).model_dump(exclude_defaults=True) == raw



def test_none_source_is_valid():
    cfg = TaskConfig(source=None)
    assert cfg.source is None


def test_source_order_by_and_limit_defaults():
    s = SourceConfig(table="t", key_column="id")
    assert s.order_by == []
    assert s.limit == 50


def test_source_order_by_and_limit_roundtrip():
    raw = {
        "source": {
            "table": "t_busi_content",
            "key_column": "content_id",
            "param_map": {"content_id": "itemId"},
            "where": "pub_time >= now() - interval '7 days' AND content_id IS NOT NULL",
            "order_by": ["updated_time ASC", "id ASC"],
            "limit": 50,
            "filter_by_platform": True,
        },
        "sink": {"mode": "standard"},
    }
    cfg = TaskConfig.model_validate(raw)
    assert cfg.source.order_by == ["updated_time ASC", "id ASC"]
    assert cfg.source.limit == 50
    assert cfg.sink.mode == "standard"


@pytest.mark.parametrize("bad_limit", [0, 501, -1])
def test_source_limit_out_of_range_rejected(bad_limit):
    with pytest.raises(ValidationError):
        SourceConfig(table="t", key_column="id", limit=bad_limit)


def test_legacy_io_config_defaults_to_database_types():
    config = TaskConfig.model_validate({
        "source": {"table": "seed", "key_column": "id"},
        "sink": {"mode": "standard"},
    })
    assert config.source.type == "database"
    assert config.sink.type == "database"


def test_legacy_io_aliases_and_normalization_preserve_input():
    source = {"table": "seed", "key_column": "id"}
    sink = {"mode": "standard"}
    payload = {"source": source, "sink": sink}

    config = TaskConfig.model_validate(payload)

    assert SourceConfig is DatabaseSourceConfig
    assert SinkConfig is DatabaseSinkConfig
    assert payload == {"source": {"table": "seed", "key_column": "id"}, "sink": {"mode": "standard"}}
    assert payload["source"] is source
    assert payload["sink"] is sink
    assert config.source.type == "database"
    assert config.sink.type == "database"


def test_redis_stream_config_roundtrip():
    config = TaskConfig.model_validate({
        "source": {
            "type": "redis_stream",
            "stream": "crawler:{video-detail}:stream",
            "group": "video-detail",
            "dead_letter_stream": "crawler:{video-detail}:dlq",
        },
        "sink": {
            "type": "redis_stream",
            "stream": "crawler:{next}:stream",
            "param_map": {"content_id": "content_id"},
        },
    })
    assert config.model_dump()["source"]["max_deliveries"] == 5
    assert config.model_dump()["sink"]["dedupe_ttl_seconds"] == 86400


def test_publish_source_accepts_only_database_to_stream_without_pagination():
    config = TaskConfig.model_validate({
        "execution_mode": "publish_source",
        "source": {
            "table": "t_busi_search_keyword",
            "key_column": "id",
            "completion": {"column": "published"},
        },
        "sink": {
            "type": "redis_stream",
            "stream": "crawler:{search}:stream",
            "param_map": {"keyword": "keyword"},
        },
    })
    assert config.execution_mode == "publish_source"


@pytest.mark.parametrize(
    "stream",
    [
        "",
        "crawler:stream",
        "crawler:{}:stream",
        "crawler:{a}:{b}:stream",
        "crawler:{}:{a}:stream",
        "crawler:{a}:{}:stream",
        "crawler:{{a}}:stream",
    ],
)
def test_stream_name_requires_one_nonempty_hash_tag(stream):
    with pytest.raises(ValidationError):
        RedisStreamSinkConfig(
            stream=stream,
            param_map={"content_id": "content_id"},
        )


def test_source_and_dlq_must_share_hash_tag():
    with pytest.raises(ValidationError, match="hash tag"):
        RedisStreamSourceConfig(
            stream="crawler:{a}:stream",
            group="g",
            dead_letter_stream="crawler:{b}:dlq",
        )


def test_redis_stream_sink_rejects_empty_param_map():
    with pytest.raises(ValidationError):
        RedisStreamSinkConfig(
            stream="crawler:{detail}:stream",
            param_map={},
        )


@pytest.mark.parametrize("config_type", [RedisStreamSourceConfig, RedisStreamSinkConfig])
def test_redis_configs_reject_database_only_or_unknown_fields(config_type):
    payload = (
        {
            "stream": "crawler:{detail}:stream",
            "group": "detail",
            "dead_letter_stream": "crawler:{detail}:dlq",
            "table": "should_not_be_ignored",
        }
        if config_type is RedisStreamSourceConfig
        else {
            "stream": "crawler:{detail}:stream",
            "param_map": {"content_id": "content_id"},
            "mode": "standard",
        }
    )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        config_type(**payload)


@pytest.mark.parametrize("payload", [
    {
        "execution_mode": "publish_source",
        "source": {
            "type": "redis_stream",
            "stream": "crawler:{search}:stream",
            "group": "search",
            "dead_letter_stream": "crawler:{search}:dlq",
        },
        "sink": {"type": "redis_stream", "stream": "crawler:{next}:stream",
                 "param_map": {"keyword": "keyword"}},
    },
    {
        "execution_mode": "publish_source",
        "source": {"table": "keywords", "key_column": "id"},
        "sink": {"mode": "standard"},
    },
    {
        "execution_mode": "publish_source",
        "source": {
            "table": "keywords",
            "key_column": "id",
            "completion": {"column": "published"},
        },
        "sink": {"type": "redis_stream", "stream": "crawler:{search}:stream",
                 "param_map": {"keyword": "keyword"}},
        "pagination": {"cursor_param": "cursor"},
    },
])
def test_publish_source_rejects_invalid_pipeline_shapes(payload):
    with pytest.raises(ValidationError, match="publish_source"):
        TaskConfig.model_validate(payload)


def test_database_to_redis_requires_completion_for_invoke_action_too():
    with pytest.raises(ValidationError, match="completion"):
        TaskConfig.model_validate({
            "execution_mode": "invoke_action",
            "source": {"table": "keywords", "key_column": "id"},
            "sink": {
                "type": "redis_stream",
                "stream": "crawler:{search}:stream",
                "param_map": {"keyword": "keyword"},
            },
        })


def test_database_source_completion_rejects_empty_column_and_extra_fields():
    with pytest.raises(ValidationError):
        DatabaseSourceCompletionConfig(column="")
    with pytest.raises(ValidationError, match="extra_forbidden"):
        DatabaseSourceCompletionConfig(column="published", table="other")

