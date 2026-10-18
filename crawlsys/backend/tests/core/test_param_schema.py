import pytest

from core.param_schema import (
    ActionParamsValidationError,
    InvalidActionParamSchema,
    normalize_action_param_schema,
    validate_action_params,
)


LEGACY = [
    {
        "name": "cursor",
        "type": "int",
        "description": "分页游标",
        "default": 0,
        "required": True,
    },
    {"name": "filters", "type": "dict", "required": False},
]


def test_legacy_schema_normalization_preserves_sink_compatibility_fields():
    assert normalize_action_param_schema(LEGACY) == {
        "type": "object",
        "properties": {
            "cursor": {
                "type": "integer",
                "description": "分页游标",
                "default": 0,
            },
            "filters": {"type": "object"},
        },
        "required": ["cursor"],
    }


def test_invalid_json_schema_is_not_silently_ignored():
    with pytest.raises(InvalidActionParamSchema):
        normalize_action_param_schema({"type": "not-a-json-schema-type"})


def test_invalid_params_expose_path_without_value():
    with pytest.raises(ActionParamsValidationError) as caught:
        validate_action_params(LEGACY, {"cursor": "secret-value"})
    assert caught.value.path == "cursor"
    assert caught.value.validator == "type"
    assert "secret-value" not in str(caught.value)


@pytest.mark.parametrize(
    "schema",
    [
        ["not-a-parameter"],
        [{"name": ""}],
        [{"name": "cursor"}, {"name": "cursor"}],
    ],
)
def test_invalid_legacy_schema_is_rejected(schema):
    with pytest.raises(InvalidActionParamSchema):
        normalize_action_param_schema(schema)


def test_required_error_includes_missing_parameter_path():
    with pytest.raises(ActionParamsValidationError) as caught:
        validate_action_params(LEGACY, {"filters": {}})

    assert caught.value.path == "cursor"
    assert caught.value.validator == "required"
