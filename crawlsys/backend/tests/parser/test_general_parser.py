import pytest

from parser.definition import validate_parser_definition
from parser.exceptions import ConfiguredParserError, ParserCallConfigurationError
from parser.parser import GeneralParser
from parser.registry import ParserRegistry


def dynamic_content_definition():
    return validate_parser_definition(
        {
            "schema_version": 1,
            "record_path": "/items",
            "output": {"mode": "model", "datatype": "content"},
            "fields": [
                {"target": "/content_id", "source": "/id", "required": True},
                {"target": "/platform", "value": "dynamic"},
            ],
        }
    )


def test_dynamic_definition_wins_over_registered_parser():
    registry = ParserRegistry()
    registry.register("demo", "detail")(
        lambda raw: iter([{"datatype": "content", "platform": "static"}])
    )
    parser = GeneralParser(registry)

    records = list(
        parser.parse(
            "demo",
            {"items": [{"id": "c1"}]},
            "detail",
            definition=dynamic_content_definition(),
            as_dto=False,
        )
    )

    assert records == [
        {"content_id": "c1", "platform": "dynamic", "datatype": "content"}
    ]


def test_dynamic_json_rejects_as_dto_true():
    definition = validate_parser_definition(
        {
            "schema_version": 1,
            "record_path": "",
            "output": {"mode": "json"},
            "fields": [{"target": "/ok", "value": True}],
        }
    )

    with pytest.raises(ParserCallConfigurationError) as caught:
        list(
            GeneralParser(ParserRegistry()).parse(
                "demo", {}, "detail", definition=definition
            )
        )

    assert caught.value.code == "json_output_requires_dict"


def test_no_definition_preserves_static_parser_behavior():
    registry = ParserRegistry()
    registry.register("demo", "detail")(
        lambda raw: iter([{"datatype": "content", "content_id": "c1"}])
    )

    parsed = list(
        GeneralParser(registry).parse("demo", {}, "detail", as_dto=False)
    )

    assert parsed == [{"datatype": "content", "content_id": "c1"}]


def test_dynamic_model_validates_dto_even_when_dict_output_requested():
    definition = validate_parser_definition(
        {
            "schema_version": 1,
            "record_path": "/items",
            "output": {"mode": "model", "datatype": "content"},
            "fields": [{"target": "/platform", "source": "/platform"}],
        }
    )

    with pytest.raises(ConfiguredParserError) as caught:
        list(
            GeneralParser(ParserRegistry()).parse(
                "demo",
                {"items": [{"platform": {"invalid": "type"}}]},
                "detail",
                definition=definition,
                as_dto=False,
            )
        )

    assert caught.value.code == "model_validation_failed"
    assert caught.value.report is not None
    assert caught.value.report.valid_records == 0
    assert caught.value.report.invalid_records == 1
    assert caught.value.report.errors[0].record_index == 0
    assert caught.value.report.errors[0].target is None
    assert caught.value.report.errors[0].code == "model_validation_failed"
