from __future__ import annotations

from models.task_config import RedisStreamSinkConfig, TaskConfig
from parser.definition import ParserDefinition


class SinkCompatibilityError(ValueError):
    pass


def validate_sink_compatibility(
    definition: ParserDefinition,
    task_config: TaskConfig,
) -> None:
    if task_config.execution_mode == "publish_source":
        return

    sink = task_config.sink
    if not isinstance(sink, RedisStreamSinkConfig) and sink.mode == "none":
        return
    if definition.output.mode == "model":
        if isinstance(sink, RedisStreamSinkConfig) or sink.mode in {"standard", "auto"}:
            return
    elif (
        not isinstance(sink, RedisStreamSinkConfig)
        and sink.mode in {"direct", "auto"}
        and sink.result_column
    ):
        return
    raise SinkCompatibilityError("parser output is incompatible with task sink")


__all__ = ["SinkCompatibilityError", "validate_sink_compatibility"]
