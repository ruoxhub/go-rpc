"""GeneralParser — single public API for all platform parser dispatch."""

from typing import Any, Iterator

from .configured import (
    ConfiguredParseResult,
    ConfiguredParser,
    ParseFieldError,
    ParseReport,
)
from .definition import ParserDefinition
from .dto import ParsedItem
from .exceptions import (
    ConfiguredParserError,
    ParserCallConfigurationError,
    ParserExecutionError,
    ParserNotFoundError,
)
from .registry import ParserRegistry

_registry = ParserRegistry()
register = _registry.register
register_direct_parser = _registry.register_direct


class GeneralParser:
    """Dispatch static or configured parsers.

    Configured definitions are evaluated when :meth:`parse` is called, while
    static parser functions are evaluated lazily during iteration. Callers that
    classify parser failures must therefore create and materialize the returned
    iterator inside the same error boundary.
    """

    def __init__(self, registry: ParserRegistry) -> None:
        self._registry = registry
        self._configured = ConfiguredParser()

    def parse(
        self,
        platform: str,
        data: Any,
        parsetype: str,
        *,
        definition: ParserDefinition | None = None,
        as_dto: bool = True,
    ) -> Iterator[ParsedItem | dict]:
        if definition is not None:
            if definition.output.mode == "json" and as_dto:
                raise ParserCallConfigurationError("json_output_requires_dict")
            result = self._configured.parse(data, definition)
            return _ValidatedDynamicResult(result, definition, as_dto=as_dto)

        entry = self._registry.get(platform, parsetype)
        if entry is None:
            raise ParserNotFoundError(platform, parsetype, available=self._registry.list())
        return self._parse_static(entry.func, platform, parsetype, data, as_dto)

    def _parse_static(
        self,
        func: Any,
        platform: str,
        parsetype: str,
        data: Any,
        as_dto: bool,
    ) -> Iterator[ParsedItem | dict]:
        def _inner() -> Iterator[ParsedItem | dict]:
            try:
                for item in func(data):
                    yield ParsedItem.from_dict(item) if as_dto else item
            except Exception as e:
                raise ParserExecutionError(platform, parsetype, cause=e) from e

        return _inner()

    @property
    def registry(self) -> ParserRegistry:
        return self._registry


class _ValidatedDynamicResult(Iterator[ParsedItem | dict]):
    def __init__(
        self,
        result: ConfiguredParseResult,
        definition: ParserDefinition,
        *,
        as_dto: bool,
    ) -> None:
        if definition.output.mode == "json":
            self._records: tuple[ParsedItem | dict, ...] = result.records
            self._report = result.report
        else:
            records: list[ParsedItem | dict] = []
            errors = list(result.report.errors)
            for record, source_index in zip(
                result.records, result.record_indexes, strict=True
            ):
                mapped = {**record, "datatype": definition.output.datatype}
                try:
                    item = ParsedItem.from_dict(mapped)
                except ValueError:
                    errors.append(
                        ParseFieldError(
                            source_index, None, "model_validation_failed"
                        )
                    )
                else:
                    records.append(item if as_dto else mapped)

            self._records = tuple(records)
            self._report = ParseReport(
                source_records=result.report.source_records,
                valid_records=len(records),
                invalid_records=result.report.source_records - len(records),
                errors=tuple(errors),
            )
            if self._report.source_records and not records:
                raise ConfiguredParserError(
                    "model_validation_failed", report=self._report
                )
        self._index = 0

    @property
    def report(self) -> ParseReport:
        return self._report

    def __iter__(self):
        return self

    def __next__(self):
        if self._index >= len(self._records):
            raise StopIteration
        record = self._records[self._index]
        self._index += 1
        return record


general_parser = GeneralParser(_registry)

# Backward-compat alias for external modules that may reference Parser class
Parser = GeneralParser
