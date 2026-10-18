from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from models.base import DATATYPE_TO_MODEL
from parser.dto import ParsedItem


FieldType = Literal[
    "string", "integer", "number", "boolean", "datetime", "object", "array"
]

FIELD_TYPES: tuple[FieldType, ...] = (
    "string",
    "integer",
    "number",
    "boolean",
    "datetime",
    "object",
    "array",
)


def parser_value_types(annotation: object) -> list[FieldType]:
    if annotation is Any:
        return list(FIELD_TYPES)
    origin = get_origin(annotation)
    if origin is Annotated:
        return parser_value_types(get_args(annotation)[0])
    if origin in (Union, UnionType):
        inferred = {
            field_type
            for member in get_args(annotation)
            if member is not type(None)
            for field_type in parser_value_types(member)
        }
        return [field_type for field_type in FIELD_TYPES if field_type in inferred] or list(
            FIELD_TYPES
        )
    scalar = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        datetime: "datetime",
    }.get(annotation)  # type: ignore[arg-type]
    if scalar is not None:
        return [scalar]
    if annotation is dict or origin in (dict, Mapping):
        return ["object"]
    if annotation in (list, tuple, set, frozenset) or origin in (
        list,
        tuple,
        set,
        frozenset,
        Sequence,
    ):
        return ["array"]
    return list(FIELD_TYPES)


def get_datatype_model_fields(datatype: str) -> list[dict[str, Any]]:
    dto_model = ParsedItem._DTO_BY_KIND.get(datatype)
    orm_model = DATATYPE_TO_MODEL.get(datatype)
    if dto_model is None or orm_model is None:
        return []
    table = getattr(orm_model, "__table__", None)
    columns = table.columns if table is not None else {}
    shared_names = sorted(set(dto_model.model_fields) & set(orm_model.__mapper__.attrs.keys()))
    fields = []
    for name in shared_names:
        if name == "datatype":
            continue
        dto_field = dto_model.model_fields[name]
        col = columns.get(name) if hasattr(columns, "get") else None
        desc = dto_field.description or (getattr(col, "comment", None) if col is not None else None)
        fields.append({
            "target": f"/{name}",
            "required": dto_field.is_required(),
            "value_types": parser_value_types(dto_field.annotation),
            "description": desc or None,
        })
    return fields


def parse_json_pointer(pointer: str, *, allow_root: bool) -> tuple[str, ...]:
    if not isinstance(pointer, str):
        raise ValueError("JSON Pointer must be a string")
    if pointer == "":
        if allow_root:
            return ()
        raise ValueError("root JSON Pointer is not allowed")
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must be absolute")

    decoded = []
    for token in pointer[1:].split("/"):
        chars = []
        index = 0
        while index < len(token):
            if token[index] != "~":
                chars.append(token[index])
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in "01":
                raise ValueError("JSON Pointer contains an invalid escape")
            chars.append("~" if token[index + 1] == "0" else "/")
            index += 2
        decoded.append("".join(chars))
    return tuple(decoded)


class StrictDefinitionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class ParserOutput(StrictDefinitionModel):
    mode: Literal["json", "model"]
    datatype: str | None = None

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "model" and not self.datatype:
            raise ValueError("model output requires datatype")
        if self.mode == "json" and self.datatype is not None:
            raise ValueError("json output forbids datatype")
        return self


class FieldMapping(StrictDefinitionModel):
    target: str
    source: str | None = None
    value: JsonValue = None
    type: FieldType | None = None
    default: JsonValue = None
    required: bool = False

    @model_validator(mode="after")
    def validate_source_or_value(self):
        present = self.model_fields_set
        if ("source" in present) == ("value" in present):
            raise ValueError("exactly one of source or value is required")
        if "source" in present and self.source is None:
            raise ValueError("source must be a JSON Pointer string")
        parse_json_pointer(self.target, allow_root=False)
        if self.source is not None:
            parse_json_pointer(self.source, allow_root=True)
        return self


class ParserDefinition(StrictDefinitionModel):
    schema_version: Literal[1]
    record_path: str = ""
    output: ParserOutput
    fields: tuple[FieldMapping, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_paths(self):
        parse_json_pointer(self.record_path, allow_root=True)
        targets = [
            parse_json_pointer(field.target, allow_root=False)
            for field in self.fields
        ]
        target_set = set(targets)
        if len(target_set) != len(targets):
            raise ValueError("duplicate target")
        if any(
            target[:depth] in target_set
            for target in targets
            for depth in range(1, len(target))
        ):
            raise ValueError("target ancestor conflict")
        if self.output.mode == "model":
            if any(len(target) != 1 for target in targets):
                raise ValueError("model output targets must be top-level")
            if ("datatype",) in target_set:
                raise ValueError("datatype is injected by output contract")
        return self


def validate_parser_definition(value: Any) -> ParserDefinition:
    definition = ParserDefinition.model_validate(value)
    if definition.output.mode == "json":
        return definition

    datatype = definition.output.datatype
    dto_model = ParsedItem._DTO_BY_KIND.get(datatype) if datatype else None
    orm_model = DATATYPE_TO_MODEL.get(datatype) if datatype else None
    if dto_model is None or orm_model is None:
        raise ValueError("model output datatype is not registered")

    contract_fields = set(dto_model.model_fields) & set(
        orm_model.__mapper__.attrs.keys()
    )
    targets = {field.target[1:] for field in definition.fields}
    if not targets <= contract_fields:
        raise ValueError("model output targets must exist in both DTO and ORM")
    return definition


def definition_sha256(definition: ParserDefinition) -> str:
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "FIELD_TYPES",
    "FieldMapping",
    "FieldType",
    "ParserDefinition",
    "ParserOutput",
    "definition_sha256",
    "get_datatype_model_fields",
    "parse_json_pointer",
    "parser_value_types",
    "validate_parser_definition",
]
