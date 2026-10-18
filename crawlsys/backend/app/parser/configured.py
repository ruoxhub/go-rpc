from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Any, Iterator

from parser.definition import (
    FieldMapping,
    JsonValue,
    ParserDefinition,
    parse_json_pointer,
)
from parser.exceptions import ConfiguredParserError


_INTEGER = re.compile(r"^-?(0|[1-9][0-9]*)$")
_NUMBER = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$")
_MISSING = object()


@dataclass(frozen=True, slots=True)
class ParseFieldError:
    record_index: int
    target: str | None
    code: str


@dataclass(frozen=True, slots=True)
class ParseReport:
    source_records: int
    valid_records: int
    invalid_records: int
    errors: tuple[ParseFieldError, ...]


class ConfiguredParseResult(Iterator[dict[str, Any]]):
    def __init__(
        self,
        records: tuple[dict[str, Any], ...],
        record_indexes: tuple[int, ...],
        report: ParseReport,
    ) -> None:
        self.records = records
        self.record_indexes = record_indexes
        self.report = report
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._index >= len(self.records):
            raise StopIteration
        record = self.records[self._index]
        self._index += 1
        return record


class ConfiguredParser:
    def parse(
        self, data: JsonValue, definition: ParserDefinition
    ) -> ConfiguredParseResult:
        source = _resolve_pointer(data, definition.record_path)
        if source is _MISSING or not isinstance(source, (dict, list)):
            raise ConfiguredParserError("record_path_invalid")

        records = source if isinstance(source, list) else [source]
        valid: list[dict[str, Any]] = []
        valid_indexes: list[int] = []
        errors: list[ParseFieldError] = []
        for index, record in enumerate(records):
            mapped, record_errors = _map_record(index, record, definition)
            if record_errors:
                errors.extend(record_errors)
            else:
                valid.append(mapped)
                valid_indexes.append(index)

        report = ParseReport(
            source_records=len(records),
            valid_records=len(valid),
            invalid_records=len(records) - len(valid),
            errors=tuple(errors),
        )
        if records and not valid:
            raise ConfiguredParserError("all_records_invalid", report=report)
        return ConfiguredParseResult(tuple(valid), tuple(valid_indexes), report)


def _resolve_pointer(value: Any, pointer: str):
    current = value
    for token in parse_json_pointer(pointer, allow_root=True):
        if isinstance(current, dict):
            if token not in current:
                return _MISSING
            current = current[token]
        elif isinstance(current, list):
            if not _INTEGER.fullmatch(token) or token.startswith("-"):
                return _MISSING
            index = int(token)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _map_record(
    record_index: int, record: Any, definition: ParserDefinition
) -> tuple[dict[str, Any], list[ParseFieldError]]:
    mapped: dict[str, Any] = {}
    errors: list[ParseFieldError] = []
    for field in definition.fields:
        value = _field_value(record, field)
        if value is _MISSING:
            if field.required:
                errors.append(ParseFieldError(record_index, field.target, "required"))
            continue

        try:
            converted = _convert(value, field.type)
        except (OverflowError, OSError, ValueError):
            errors.append(ParseFieldError(record_index, field.target, "type"))
            continue
        if definition.output.mode == "json" and isinstance(converted, datetime):
            converted = converted.isoformat()
        _set_target(mapped, field.target, converted)
    return mapped, errors


def _field_value(record: Any, field: FieldMapping):
    if "value" in field.model_fields_set:
        return field.value

    value = _resolve_pointer(record, field.source or "")
    if value is not _MISSING and value is not None:
        return value
    if "default" in field.model_fields_set:
        return field.default
    return _MISSING


def _set_target(record: dict[str, Any], pointer: str, value: Any) -> None:
    tokens = parse_json_pointer(pointer, allow_root=False)
    current = record
    for token in tokens[:-1]:
        current = current.setdefault(token, {})
    current[tokens[-1]] = value


def _convert(value: Any, field_type: str | None):
    if field_type is None:
        return value
    if field_type == "string":
        if isinstance(value, (dict, list)) or value is None:
            raise ValueError
        return str(value)
    if field_type == "integer":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            return value
        if isinstance(value, str) and _INTEGER.fullmatch(value):
            return int(value)
        raise ValueError
    if field_type == "number":
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError
            return value
        if isinstance(value, str) and _NUMBER.fullmatch(value):
            number = float(value)
            if math.isfinite(number):
                return number
        raise ValueError
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if value == "true" or (type(value) is int and value == 1):
            return True
        if value == "false" or (type(value) is int and value == 0):
            return False
        raise ValueError
    if field_type == "datetime":
        return _to_datetime(value)
    if field_type == "object" and isinstance(value, dict):
        return value
    if field_type == "array" and isinstance(value, list):
        return value
    raise ValueError


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError
    if isinstance(value, int):
        timestamp = value
    elif isinstance(value, str) and _INTEGER.fullmatch(value):
        timestamp = int(value)
    elif isinstance(value, str):
        return datetime.fromisoformat(value)
    else:
        raise ValueError

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if abs(timestamp) < 100_000_000_000:
        return epoch + timedelta(seconds=timestamp)
    return epoch + timedelta(milliseconds=timestamp)


__all__ = [
    "ConfiguredParseResult",
    "ConfiguredParser",
    "ParseFieldError",
    "ParseReport",
]
