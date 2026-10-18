from __future__ import annotations

import pytest
from pydantic import ValidationError

from parser.definition import (
    FieldMapping,
    ParserDefinition,
    ParserOutput,
    definition_sha256,
    parse_json_pointer,
    validate_parser_definition,
)


def model_definition(**overrides):
    value = {
        "schema_version": 1,
        "record_path": "/data/items",
        "output": {"mode": "model", "datatype": "content"},
        "fields": [
            {
                "target": "/content_id",
                "source": "/id",
                "type": "string",
                "required": True,
            },
            {"target": "/platform", "value": "kalodata"},
        ],
    }
    value.update(overrides)
    return value


def test_pointer_decodes_rfc6901_escapes():
    assert parse_json_pointer("/a~1b/~0key", allow_root=False) == (
        "a/b",
        "~key",
    )


def test_pointer_accepts_empty_root_only_when_allowed():
    assert parse_json_pointer("", allow_root=True) == ()
    with pytest.raises(ValueError):
        parse_json_pointer("", allow_root=False)


@pytest.mark.parametrize(
    "pointer", ["not/absolute", "/bad~2escape", "/dangling~"]
)
def test_invalid_pointer_is_rejected(pointer):
    with pytest.raises(ValueError):
        parse_json_pointer(pointer, allow_root=False)


def test_value_null_counts_as_present_and_source_is_exclusive():
    definition = ParserDefinition.model_validate(
        {
            "schema_version": 1,
            "record_path": "",
            "output": {"mode": "json"},
            "fields": [{"target": "/value", "value": None}],
        }
    )

    assert "value" in definition.fields[0].model_fields_set


@pytest.mark.parametrize(
    "field",
    [
        {"target": "/value"},
        {"target": "/value", "source": "/source", "value": 1},
        {"target": "/value", "source": None},
    ],
)
def test_field_requires_exactly_one_valid_source_or_value(field):
    with pytest.raises(ValidationError):
        ParserDefinition.model_validate(
            {
                "schema_version": 1,
                "output": {"mode": "json"},
                "fields": [field],
            }
        )


def test_source_accepts_the_document_root():
    definition = ParserDefinition.model_validate(
        {
            "schema_version": 1,
            "output": {"mode": "json"},
            "fields": [{"target": "/value", "source": ""}],
        }
    )

    assert definition.fields[0].source == ""


@pytest.mark.parametrize(
    "raw",
    [
        model_definition(unknown=True),
        model_definition(output={"mode": "model", "datatype": "content", "unknown": True}),
        model_definition(fields=[{"target": "/content_id", "value": "1", "unknown": True}]),
    ],
)
def test_unknown_fields_are_rejected_at_every_level(raw):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ParserDefinition.model_validate(raw)


def test_validation_errors_hide_input_values():
    with pytest.raises(ValidationError) as exc_info:
        ParserDefinition.model_validate(model_definition(secret="do-not-leak"))

    assert "do-not-leak" not in str(exc_info.value)


def test_definition_models_are_frozen():
    definition = ParserDefinition.model_validate(model_definition())

    with pytest.raises(ValidationError, match="frozen_instance"):
        definition.record_path = "/other"
    with pytest.raises(ValidationError, match="frozen_instance"):
        definition.output.mode = "json"
    with pytest.raises(ValidationError, match="frozen_instance"):
        definition.fields[0].target = "/other"


def test_schema_version_other_than_one_is_rejected():
    with pytest.raises(ValidationError):
        ParserDefinition.model_validate(model_definition(schema_version=2))


@pytest.mark.parametrize("field_count", [0, 501])
def test_field_count_is_bounded(field_count):
    fields = [
        {"target": f"/field_{index}", "value": index}
        for index in range(field_count)
    ]

    with pytest.raises(ValidationError):
        ParserDefinition.model_validate(
            {
                "schema_version": 1,
                "output": {"mode": "json"},
                "fields": fields,
            }
        )


@pytest.mark.parametrize("field_count", [1, 500])
def test_field_count_accepts_valid_boundaries(field_count):
    fields = [
        {"target": f"/field_{index}", "value": index}
        for index in range(field_count)
    ]

    definition = ParserDefinition.model_validate(
        {
            "schema_version": 1,
            "output": {"mode": "json"},
            "fields": fields,
        }
    )

    assert len(definition.fields) == field_count


def test_duplicate_target_is_rejected():
    raw = model_definition(
        fields=[
            {"target": "/platform", "value": "a"},
            {"target": "/platform", "value": "b"},
        ]
    )

    with pytest.raises(ValidationError, match="duplicate target"):
        ParserDefinition.model_validate(raw)


def test_target_ancestor_conflict_is_rejected():
    raw = model_definition(
        fields=[
            {"target": "/author", "source": "/author"},
            {"target": "/author/name", "source": "/author/name"},
        ]
    )

    with pytest.raises(ValidationError, match="ancestor"):
        ParserDefinition.model_validate(raw)


@pytest.mark.parametrize(
    "output",
    [
        {"mode": "json", "datatype": "content"},
        {"mode": "model"},
        {"mode": "model", "datatype": ""},
    ],
)
def test_output_mode_enforces_datatype_contract(output):
    with pytest.raises(ValidationError):
        ParserDefinition.model_validate(model_definition(output=output))


def test_model_output_rejects_nested_target():
    raw = model_definition(fields=[{"target": "/author/name", "value": "name"}])

    with pytest.raises(ValidationError, match="top-level"):
        ParserDefinition.model_validate(raw)


def test_model_output_rejects_datatype_target():
    raw = model_definition(fields=[{"target": "/datatype", "value": "content"}])

    with pytest.raises(ValidationError, match="injected"):
        ParserDefinition.model_validate(raw)


def test_validate_rejects_unregistered_datatype_without_echoing_it():
    with pytest.raises(ValueError) as exc_info:
        validate_parser_definition(
            model_definition(output={"mode": "model", "datatype": "secret-kind"})
        )

    assert "secret-kind" not in str(exc_info.value)


@pytest.mark.parametrize("target", ["/domain", "/is_detail"])
def test_validate_requires_target_in_both_dto_and_orm(target):
    with pytest.raises(ValueError, match="DTO and ORM"):
        validate_parser_definition(
            model_definition(fields=[{"target": target, "value": "value"}])
        )


def test_validate_accepts_registered_model_contract():
    definition = validate_parser_definition(model_definition())

    assert isinstance(definition, ParserDefinition)
    assert definition.output.datatype == "content"


def test_json_output_skips_model_registry_contract():
    definition = validate_parser_definition(
        {
            "schema_version": 1,
            "output": {"mode": "json"},
            "fields": [{"target": "/anything/nested", "value": True}],
        }
    )

    assert definition.output.mode == "json"


def test_definition_hash_is_canonical():
    left = validate_parser_definition(model_definition())
    right = validate_parser_definition(
        {
            "fields": model_definition()["fields"],
            "output": {"datatype": "content", "mode": "model"},
            "record_path": "/data/items",
            "schema_version": 1,
        }
    )

    assert definition_sha256(left) == definition_sha256(right)
    assert len(definition_sha256(left)) == 64


def test_definition_api_is_exported_from_parser_package():
    import parser

    assert parser.FieldMapping is FieldMapping
    assert parser.ParserDefinition is ParserDefinition
    assert parser.ParserOutput is ParserOutput
    assert parser.definition_sha256 is definition_sha256
    assert parser.parse_json_pointer is parse_json_pointer
    assert parser.validate_parser_definition is validate_parser_definition
