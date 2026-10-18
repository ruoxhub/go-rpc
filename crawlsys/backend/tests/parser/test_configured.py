from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import JsonValue

from parser.configured import ConfiguredParser
from parser.definition import ParserDefinition
from parser.exceptions import ConfiguredParserError


def definition(fields, *, record_path="/items", mode="json", datatype=None):
    output = {"mode": mode}
    if datatype is not None:
        output["datatype"] = datatype
    return ParserDefinition.model_validate(
        {
            "schema_version": 1,
            "record_path": record_path,
            "output": output,
            "fields": fields,
        }
    )


def parse_one(raw, field, *, mode="json"):
    result = ConfiguredParser().parse(
        {"items": [raw]},
        definition(
            [field],
            mode=mode,
            datatype="content" if mode == "model" else None,
        ),
    )
    return list(result)[0]


def test_partial_invalid_records_are_skipped_and_reported():
    result = ConfiguredParser().parse(
        {"items": [{"id": "1"}, {}]},
        definition([{"target": "/id", "source": "/id", "required": True}]),
    )

    assert list(result) == [{"id": "1"}]
    assert result.record_indexes == (0,)
    assert result.report.source_records == 2
    assert result.report.valid_records == 1
    assert result.report.invalid_records == 1
    assert result.report.errors[0].code == "required"


def test_empty_source_array_is_successful_zero_result():
    result = ConfiguredParser().parse(
        {"items": []},
        definition([{"target": "/id", "source": "/id"}]),
    )

    assert list(result) == []
    assert result.report.source_records == 0


def test_non_empty_source_with_no_valid_records_fails():
    with pytest.raises(ConfiguredParserError) as caught:
        ConfiguredParser().parse(
            {"items": [{}]},
            definition(
                [{"target": "/id", "source": "/id", "required": True}]
            ),
        )

    assert caught.value.code == "all_records_invalid"
    report = caught.value.report
    assert report is not None
    assert report.invalid_records == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            99_999_999_999,
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(seconds=99_999_999_999),
        ),
        (
            100_000_000_000,
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(seconds=100_000_000),
        ),
        (
            -100_000_000_000,
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(seconds=-100_000_000),
        ),
    ],
)
def test_datetime_uses_fixed_seconds_milliseconds_threshold(raw, expected):
    record = parse_one(
        {"time": raw},
        {"target": "/time", "source": "/time", "type": "datetime"},
    )

    assert record == {"time": expected.isoformat()}


def test_record_root_object_builds_nested_targets():
    result = ConfiguredParser().parse(
        {"id": 7, "name": "Ada"},
        definition(
            [
                {"target": "/author/id", "source": "/id"},
                {"target": "/author/name", "source": "/name"},
            ],
            record_path="",
        ),
    )

    assert list(result) == [{"author": {"id": 7, "name": "Ada"}}]


def test_scalar_array_records_can_be_read_from_empty_source_pointer():
    result = ConfiguredParser().parse(
        {"items": [1, "2"]},
        definition([{"target": "/value", "source": "", "type": "integer"}]),
    )

    assert list(result) == [{"value": 1}, {"value": 2}]


def test_pointer_decodes_escapes_and_reads_array_indexes():
    record = parse_one(
        {"a/b": {"~key": ["first", "second"]}},
        {"target": "/picked", "source": "/a~1b/~0key/1"},
    )

    assert record == {"picked": "second"}


@pytest.mark.parametrize("source", ["/values/01", "/values/-1", "/values/x"])
def test_invalid_array_index_is_treated_as_missing(source):
    record = parse_one(
        {"values": [10, 20]},
        {"target": "/picked", "source": source, "default": 5},
    )

    assert record == {"picked": 5}


def test_wrong_pointer_container_is_treated_as_missing():
    record = parse_one(
        {"value": 1},
        {"target": "/picked", "source": "/value/nested", "default": "fallback"},
    )

    assert record == {"picked": "fallback"}


@pytest.mark.parametrize("raw", [{}, {"value": None}])
def test_missing_and_null_source_use_explicit_default(raw):
    record = parse_one(
        raw,
        {"target": "/picked", "source": "/value", "default": "fallback"},
    )

    assert record == {"picked": "fallback"}


def test_explicit_null_default_and_constant_are_preserved():
    result = ConfiguredParser().parse(
        {"items": [{}]},
        definition(
            [
                {
                    "target": "/from_default",
                    "source": "/missing",
                    "default": None,
                    "required": True,
                },
                {"target": "/constant", "value": None, "required": True},
            ]
        ),
    )

    assert list(result) == [{"from_default": None, "constant": None}]


def test_optional_missing_source_omits_target():
    record = parse_one({}, {"target": "/missing", "source": "/missing"})

    assert record == {}


@pytest.mark.parametrize(
    ("field_type", "raw", "expected"),
    [
        ("string", 12, "12"),
        ("string", True, "True"),
        ("integer", "-12", -12),
        ("number", "1.25e2", 125.0),
        ("number", 4, 4),
        ("number", 10**400, 10**400),
        ("boolean", "true", True),
        ("boolean", "false", False),
        ("boolean", 1, True),
        ("boolean", 0, False),
        ("object", {"nested": 1}, {"nested": 1}),
        ("array", [1, 2], [1, 2]),
    ],
)
def test_basic_type_conversions(field_type, raw, expected):
    record = parse_one(
        {"value": raw},
        {"target": "/value", "source": "/value", "type": field_type},
    )

    assert record == {"value": expected}


@pytest.mark.parametrize(
    ("field_type", "raw", "sensitive_value"),
    [
        ("string", {}, "{}"),
        ("string", [], "[]"),
        ("integer", True, "True"),
        ("integer", 1.0, "1.0"),
        ("integer", "1.0", "1.0"),
        ("integer", "+1", "+1"),
        ("integer", "01", "01"),
        ("number", True, "True"),
        ("number", float("nan"), "nan"),
        ("number", float("inf"), "inf"),
        ("number", "NaN", "NaN"),
        ("number", "Infinity", "Infinity"),
        ("boolean", "sensitive-boolean", "sensitive-boolean"),
        ("boolean", 2, "2"),
        ("object", "sensitive-object", "sensitive-object"),
        ("array", {"sensitive-array": "value"}, "sensitive-array"),
    ],
)
def test_invalid_type_conversions_report_without_values(
    field_type: str, raw: JsonValue, sensitive_value: str
):
    data: JsonValue = {"items": [{"value": raw}]}

    with pytest.raises(ConfiguredParserError) as caught:
        ConfiguredParser().parse(
            data,
            definition(
                [
                    {
                        "target": "/converted",
                        "source": "/value",
                        "type": field_type,
                    }
                ]
            ),
        )

    report = caught.value.report
    assert report is not None
    error = report.errors[0]
    assert (error.record_index, error.target, error.code) == (
        0,
        "/converted",
        "type",
    )
    assert sensitive_value not in str(caught.value)
    assert sensitive_value not in repr(report)
    assert set(error.__dataclass_fields__) == {"record_index", "target", "code"}


def test_iso_datetime_is_normalized_for_json_and_preserved_for_model():
    field = {"target": "/published_at", "source": "/time", "type": "datetime"}

    json_record = parse_one({"time": "2024-01-02T03:04:05Z"}, field)
    model_record = parse_one(
        {"time": "2024-01-02T03:04:05Z"}, field, mode="model"
    )

    assert json_record == {"published_at": "2024-01-02T03:04:05+00:00"}
    assert model_record == {
        "published_at": datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    }


@pytest.mark.parametrize(
    "raw", [True, 1.5, "1.5", "not-a-date", 10**30, -(10**30)]
)
def test_invalid_or_out_of_range_datetime_is_rejected(raw):
    with pytest.raises(ConfiguredParserError) as caught:
        parse_one(
            {"time": raw},
            {"target": "/time", "source": "/time", "type": "datetime"},
        )

    report = caught.value.report
    assert report is not None
    assert report.errors[0].code == "type"


@pytest.mark.parametrize("data", [{}, {"items": 1}, {"items": None}])
def test_invalid_record_path_fails_the_whole_parse(data):
    with pytest.raises(ConfiguredParserError) as caught:
        ConfiguredParser().parse(
            data, definition([{"target": "/value", "source": ""}])
        )

    assert caught.value.code == "record_path_invalid"
    assert caught.value.report is None


def test_result_is_materialized_single_pass_and_report_is_frozen():
    result = ConfiguredParser().parse(
        {"items": [{"id": 1}]},
        definition([{"target": "/id", "source": "/id"}]),
    )

    assert isinstance(result.records, tuple)
    assert iter(result) is result
    assert list(result) == [{"id": 1}]
    assert list(result) == []
    with pytest.raises(FrozenInstanceError):
        setattr(result.report, "valid_records", 2)


def test_same_input_and_definition_produce_equal_records_and_reports():
    data: JsonValue = {"items": [{"id": "1"}, {}]}
    parser_definition = definition(
        [{"target": "/id", "source": "/id", "required": True}]
    )

    left = ConfiguredParser().parse(data, parser_definition)
    right = ConfiguredParser().parse(data, parser_definition)

    assert left.records == right.records
    assert left.record_indexes == right.record_indexes
    assert left.report == right.report
