import pytest

from models.task_config import (
    DatabaseSourceCompletionConfig,
    DatabaseSourceConfig,
    RedisStreamSinkConfig,
    SinkConfig,
    TaskConfig,
)
from parser.compatibility import SinkCompatibilityError, validate_sink_compatibility
from parser.definition import validate_parser_definition


@pytest.fixture
def model_definition():
    return validate_parser_definition(
        {
            "schema_version": 1,
            "output": {"mode": "model", "datatype": "content"},
            "fields": [
                {"target": "/content_id", "source": "/id"},
                {"target": "/platform", "value": "test"},
            ],
        }
    )


@pytest.fixture
def json_definition():
    return validate_parser_definition(
        {
            "schema_version": 1,
            "output": {"mode": "json"},
            "fields": [{"target": "/payload", "source": ""}],
        }
    )


def test_model_supports_standard_auto_and_redis(model_definition):
    validate_sink_compatibility(
        model_definition,
        TaskConfig(sink=SinkConfig(mode="standard")),
    )
    validate_sink_compatibility(
        model_definition,
        TaskConfig(sink=SinkConfig(mode="auto")),
    )
    validate_sink_compatibility(
        model_definition,
        TaskConfig(
            sink=RedisStreamSinkConfig(
                stream="crawler:{x}:stream",
                param_map={"content_id": "id"},
            )
        ),
    )


def test_model_rejects_direct_database_mode(model_definition):
    config = TaskConfig(sink=SinkConfig(mode="direct", result_column="payload"))
    with pytest.raises(SinkCompatibilityError):
        validate_sink_compatibility(model_definition, config)


def test_json_requires_direct_result_column_for_database(json_definition):
    with pytest.raises(SinkCompatibilityError):
        validate_sink_compatibility(
            json_definition,
            TaskConfig(sink=SinkConfig(mode="standard")),
        )
    with pytest.raises(SinkCompatibilityError):
        validate_sink_compatibility(
            json_definition,
            TaskConfig(sink=SinkConfig(mode="direct")),
        )
    validate_sink_compatibility(
        json_definition,
        TaskConfig(sink=SinkConfig(mode="direct", result_column="payload")),
    )


def test_json_auto_requires_result_column_and_rejects_redis(json_definition):
    with pytest.raises(SinkCompatibilityError):
        validate_sink_compatibility(
            json_definition,
            TaskConfig(sink=SinkConfig(mode="auto")),
        )
    validate_sink_compatibility(
        json_definition,
        TaskConfig(sink=SinkConfig(mode="auto", result_column="payload")),
    )
    with pytest.raises(SinkCompatibilityError):
        validate_sink_compatibility(
            json_definition,
            TaskConfig(
                sink=RedisStreamSinkConfig(
                    stream="crawler:{x}:stream",
                    param_map={"payload": "payload"},
                )
            ),
        )


@pytest.mark.parametrize("definition_fixture", ["model_definition", "json_definition"])
def test_none_accepts_both_outputs(request, definition_fixture):
    validate_sink_compatibility(
        request.getfixturevalue(definition_fixture),
        TaskConfig(sink=SinkConfig(mode="none")),
    )


def test_publish_source_bypasses_parser_compatibility(json_definition):
    validate_sink_compatibility(
        json_definition,
        TaskConfig(
            execution_mode="publish_source",
            source=DatabaseSourceConfig(
                table="source",
                key_column="id",
                completion=DatabaseSourceCompletionConfig(column="published"),
            ),
            sink=RedisStreamSinkConfig(
                stream="crawler:{x}:stream",
                param_map={"payload": "payload"},
            ),
        ),
    )
