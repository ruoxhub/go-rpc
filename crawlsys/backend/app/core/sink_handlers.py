"""Route parsed crawler results to database or Redis Stream sinks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from sqlalchemy import text

from common.logging import get_logger
from core.constants import DATATYPE_TO_MODEL
from core.param_schema import (
    ActionParamsValidationError,
    InvalidActionParamSchema,
    validate_action_params,
)
from core.sql_safety import ident
from models.task_config import (
    DatabaseSinkConfig,
    DatabaseSourceConfig,
    RedisStreamSinkConfig,
)
from parser import general_parser
from parser.definition import ParserDefinition
from parser.exceptions import (
    ConfiguredParserError,
    ParserCallConfigurationError,
    ParserExecutionError,
    ParserNotFoundError,
)
from parser.sanitizer import canonical_json_bytes
from pipeline.preprocessor import clean_nul_bytes

logger = get_logger(__file__)
_ALLOWED_LOG_FIELDS = frozenset(
    {
        "ba_id", "platform", "action", "source_records", "valid_records",
        "parser_source", "parser_revision_id",
    }
)


def _safe_log_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in _ALLOWED_LOG_FIELDS}


def _log_event(level: str, message: str, fields: dict[str, Any]) -> None:
    safe_fields = _safe_log_fields(fields)
    target = logger.bind(**safe_fields) if hasattr(logger, "bind") else logger
    kwargs = {} if hasattr(logger, "bind") else {"extra": safe_fields}
    getattr(target, level)(message, **kwargs)


@dataclass(frozen=True, slots=True)
class SinkResult:
    processed: int = 0
    produced: int = 0
    deduplicated: int = 0
    skipped: int = 0

    def __add__(self, other: "SinkResult") -> "SinkResult":
        return SinkResult(
            processed=self.processed + other.processed,
            produced=self.produced + other.produced,
            deduplicated=self.deduplicated + other.deduplicated,
            skipped=self.skipped + other.skipped,
        )


class SinkValidationError(ValueError):
    """A deterministic sink error safe to expose to work-item classification."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _parse_records(
    parser: Any,
    task: Any,
    raw: dict,
    definition: ParserDefinition | None,
) -> list[dict[str, Any]]:
    try:
        return list(
            parser.parse(
                task.platform,
                raw,
                task.action,
                definition=definition,
                as_dto=False,
            )
        )
    except (ConfiguredParserError, ParserCallConfigurationError) as error:
        raise SinkValidationError(error.code) from None
    except ParserNotFoundError:
        raise SinkValidationError("parser_not_found") from None
    except ParserExecutionError:
        raise SinkValidationError("parser_execution_failed") from None


class SinkHandler(Protocol):
    async def handle(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig,
        raw: dict,
        item: Any,
        parser_definition: ParserDefinition | None,
    ) -> SinkResult: ...


class StandardSinkHandler:
    """Parse records, convert registered models, and run the database pipeline."""

    def __init__(self, *, parser: Any, pipeline: Any, persist_results: bool):
        self._parser = parser
        self._pipeline = pipeline
        self._persist_results = persist_results

    async def handle(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig,
        raw: dict,
        item: Any,
        parser_definition: ParserDefinition | None,
    ) -> SinkResult:
        parsed = _parse_records(self._parser, task, raw, parser_definition)
        if not parsed:
            _log_event(
                "warning",
                "Crawler sink parser returned no records",
                {"platform": task.platform, "action": task.action, "source_records": 0},
            )
            return SinkResult()
        result = SinkResult(processed=len(parsed))
        if not self._persist_results:
            return result
        models = []
        for record in parsed:
            model_class = DATATYPE_TO_MODEL.get(record.get("datatype"))
            if model_class is not None:
                if not record.get("platform") and getattr(task, "platform", None) and hasattr(model_class, "platform"):
                    record = {**record, "platform": task.platform}
                try:
                    model = model_class(**record)
                except (TypeError, ValueError):
                    raise SinkValidationError("model_construction_failed") from None
                models.append(model)
        if not models:
            _log_event(
                "warning",
                "Crawler sink parser produced no models",
                {
                    "platform": task.platform,
                    "action": task.action,
                    "source_records": len(parsed),
                    "valid_records": 0,
                },
            )
            return result
        await self._pipeline.process_items(models)
        return result


class DirectSinkHandler:
    """Parse one direct result and update its configured database column."""

    def __init__(self, *, db: Any, parser: Any, persist_results: bool):
        self._db = db
        self._parser = parser
        self._persist_results = persist_results

    async def handle(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig,
        raw: dict,
        item: Any,
        parser_definition: ParserDefinition | None,
    ) -> SinkResult:
        if not item.entity_id:
            return SinkResult()
        if not sink.result_column:
            raise SinkValidationError("direct_requires_result_column")
        if source is None:
            raise SinkValidationError("direct_requires_source_key")
        parsed = _parse_records(self._parser, task, raw, parser_definition)
        if not parsed:
            return SinkResult()
        if len(parsed) != 1:
            raise SinkValidationError("direct_requires_single_record")
        result = SinkResult(processed=1)
        if not self._persist_results:
            return result

        table = ident(sink.mark_done_table or source.table, "table")
        column = ident(sink.result_column, "result_column")
        key = ident(source.key_column, "key_column")
        statement = f"UPDATE {table} SET {column} = :val WHERE {key} = :eid"
        cleaned_record = clean_nul_bytes(parsed[0])
        async with self._db.asession_scope() as session:
            await session.execute(
                text(statement),
                {
                    "val": canonical_json_bytes(cleaned_record).decode("utf-8"),
                    "eid": item.entity_id,
                },
            )
            if sink.mark_done_column:
                mark_done_column = ident(sink.mark_done_column, "mark_done_column")
                await session.execute(
                    text(
                        f"UPDATE {table} SET {mark_done_column} = true "
                        f"WHERE {key} = :eid"
                    ),
                    {"eid": item.entity_id},
                )
        return result


class NoneSinkHandler:
    """Discard the result."""

    async def handle(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig,
        raw: dict,
        item: Any,
        parser_definition: ParserDefinition | None,
    ) -> SinkResult:
        return SinkResult()


class ResultSinkRouter:
    def __init__(
        self,
        *,
        db: Any,
        pipeline: Any,
        parser: Any = general_parser,
        stream_queue: Any,
        persist_results: bool,
    ):
        self._db = db
        self._parser = parser
        self._stream_queue = stream_queue
        self._persist_results = persist_results
        self._key_integer_column_cache: dict[tuple[str, str], bool] = {}
        self._handlers: dict[str, SinkHandler] = {
            "standard": StandardSinkHandler(
                parser=parser,
                pipeline=pipeline,
                persist_results=persist_results,
            ),
            "direct": DirectSinkHandler(
                db=db,
                parser=parser,
                persist_results=persist_results,
            ),
            "none": NoneSinkHandler(),
        }

    async def persist(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig | RedisStreamSinkConfig,
        raw: dict,
        item: Any,
        parser_definition: ParserDefinition | None,
        parser_revision_id: int | None,
    ) -> SinkResult:
        if isinstance(sink, RedisStreamSinkConfig):
            records = _parse_records(self._parser, task, raw, parser_definition)
            self._log_parser_selection(task, parser_definition, parser_revision_id)
            return await self._publish_records(task=task, sink=sink, records=records)

        mode = sink.mode
        if parser_definition is not None and mode != "none":
            output_mode = parser_definition.output.mode
            incompatible = (output_mode == "model" and mode == "direct") or (
                output_mode == "json" and mode == "standard"
            )
            if mode == "auto" and output_mode == "json" and not sink.result_column:
                incompatible = True
            if incompatible:
                raise SinkValidationError("parser_sink_incompatible")
        if mode == "auto":
            if parser_definition is not None:
                mode = "standard" if parser_definition.output.mode == "model" else "direct"
            else:
                entry = self._parser.registry.get(task.platform, task.action)
                mode = entry.mode if entry else "none"
        handler = self._handlers.get(mode)
        if handler is None:
            raise SinkValidationError("unknown_sink_mode")
        result = await handler.handle(
            task=task,
            source=source,
            sink=sink,
            raw=raw,
            item=item,
            parser_definition=parser_definition,
        )
        self._log_parser_selection(task, parser_definition, parser_revision_id)
        if mode != "direct" and self._should_mark_done(
            mode=mode, sink=sink, item=item, result=result
        ):
            await self._mark_done(
                task=task,
                source=source,
                sink=sink,
                entity_id=item.entity_id,
            )
        return result

    async def publish_work_item(
        self,
        *,
        task: Any,
        sink: RedisStreamSinkConfig,
        item: Any,
        params_schema: dict[str, Any] | bool | None,
    ) -> SinkResult:
        return await self._publish_records(
            task=task,
            sink=sink,
            records=[item.params],
            params_schema=params_schema,
        )

    async def _publish_records(
        self,
        *,
        task: Any,
        sink: RedisStreamSinkConfig,
        records: Iterable[Mapping[str, Any]],
        params_schema: dict[str, Any] | bool | None = None,
    ) -> SinkResult:
        materialized = list(records)
        if not materialized:
            return SinkResult()

        mapped_records: list[dict[str, Any]] = []
        skipped = 0
        for record in materialized:
            if not all(source_name in record for source_name in sink.param_map):
                skipped += 1
                continue
            params = {
                target_name: record[source_name]
                for source_name, target_name in sink.param_map.items()
            }
            if params_schema is not None:
                self._validate_downstream_params(params_schema, params)
            mapped_records.append(params)

        if not mapped_records:
            raise SinkValidationError("no_valid_downstream_params")

        result = SinkResult(processed=len(materialized), skipped=skipped)
        if not self._persist_results:
            return result

        metadata = {
            "producer_task_id": str(task.task_id),
            "producer_platform": task.platform,
            "producer_action": task.action,
            "produced_at": datetime.now(timezone.utc).isoformat(),
        }
        for params in mapped_records:
            enqueue_result = await self._stream_queue.enqueue(sink, params, metadata)
            result += SinkResult(
                produced=int(enqueue_result.produced),
                deduplicated=int(enqueue_result.deduplicated),
            )
        return result

    @staticmethod
    def _validate_downstream_params(schema: Any, params: dict[str, Any]) -> None:
        try:
            validate_action_params(schema, params)
        except ActionParamsValidationError as error:
            raise SinkValidationError(
                f"invalid_downstream_params:{error.path}"
            ) from None
        except InvalidActionParamSchema:
            raise SinkValidationError("invalid_downstream_schema") from None

    @staticmethod
    def _log_parser_selection(
        task: Any,
        parser_definition: ParserDefinition | None,
        parser_revision_id: int | None,
    ) -> None:
        fields = _safe_log_fields(
            {
                "ba_id": getattr(task, "ba_id", None),
                "platform": task.platform,
                "action": task.action,
                "parser_revision_id": parser_revision_id,
                "parser_source": "dynamic" if parser_definition else "static",
            }
        )
        _log_event("info", "Crawler sink parser selected", fields)

    def _should_mark_done(
        self,
        *,
        mode: str,
        sink: DatabaseSinkConfig,
        item: Any,
        result: SinkResult,
    ) -> bool:
        return bool(
            self._persist_results
            and mode != "none"
            and result.processed > 0
            and sink.mark_done_column
            and item.entity_id
        )

    async def _mark_done(
        self,
        *,
        task: Any,
        source: DatabaseSourceConfig | None,
        sink: DatabaseSinkConfig,
        entity_id: str,
    ) -> None:
        if source is None:
            raise ValueError(
                f"mark_done requires source.key_column (task={task.platform}/{task.action})"
            )
        table = ident(sink.mark_done_table or source.table, "table")
        column = ident(sink.mark_done_column, "mark_done_column")
        key = ident(source.key_column, "key_column")
        statement = f"UPDATE {table} SET {column} = true WHERE {key} = :eid"
        typed_entity_id: str | int = entity_id
        if entity_id.isdigit() and await self._source_key_is_integer_column(table, key):
            typed_entity_id = int(entity_id)
        async with self._db.asession_scope() as session:
            await session.execute(text(statement), {"eid": typed_entity_id})

    async def _source_key_is_integer_column(self, table: str, column: str) -> bool:
        cache_key = (table, column)
        if cache_key in self._key_integer_column_cache:
            return self._key_integer_column_cache[cache_key]
        statement = text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t "
            "AND column_name = :c LIMIT 1"
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(statement, {"t": table, "c": column})
            data_type = result.scalar()
        is_integer = data_type in {"smallint", "integer", "bigint"}
        self._key_integer_column_cache[cache_key] = is_integer
        return is_integer
