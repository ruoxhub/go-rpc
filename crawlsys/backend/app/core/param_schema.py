from __future__ import annotations

from typing import Any

import jsonschema


class InvalidActionParamSchema(ValueError):
    pass


class ActionParamsValidationError(ValueError):
    def __init__(self, *, path: str, validator: str) -> None:
        self.path = path
        self.validator = validator
        super().__init__(f"invalid action params at path {path} ({validator})")


_TYPE_MAP = {
    "string": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "bool": "boolean",
    "boolean": "boolean",
    "list": "array",
    "dict": "object",
}


def normalize_action_param_schema(schema: object) -> dict[str, Any] | bool | None:
    if schema is None:
        return None
    if isinstance(schema, bool):
        return schema
    if isinstance(schema, list):
        properties: dict[str, Any] = {}
        required: list[str] = []
        for parameter in schema:
            if not isinstance(parameter, dict) or not isinstance(
                parameter.get("name"), str
            ):
                raise InvalidActionParamSchema(
                    "legacy parameter requires a string name"
                )
            name = parameter["name"]
            if not name.strip():
                raise InvalidActionParamSchema(
                    "legacy parameter requires a non-empty name"
                )
            if name in properties:
                raise InvalidActionParamSchema("legacy parameter names must be unique")
            property_schema: dict[str, Any] = {
                "type": _TYPE_MAP.get(parameter.get("type", "string"), "string")
            }
            if parameter.get("description"):
                property_schema["description"] = parameter["description"]
            if parameter.get("default") is not None:
                property_schema["default"] = parameter["default"]
            properties[name] = property_schema
            if parameter.get("required"):
                required.append(name)
        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
    if not isinstance(schema, dict):
        raise InvalidActionParamSchema(
            "schema must be an object, array, boolean, or null"
        )
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as error:
        raise InvalidActionParamSchema("invalid JSON Schema") from error
    return schema


def validate_action_params(schema: object, params: dict[str, Any]) -> None:
    normalized = normalize_action_param_schema(schema)
    if normalized is None:
        return
    try:
        jsonschema.validate(params, normalized)
    except jsonschema.ValidationError as error:
        path = [str(part) for part in error.absolute_path]
        if error.validator == "required" and isinstance(
            error.validator_value, list
        ):
            missing = next(
                (name for name in error.validator_value if name not in error.instance),
                None,
            )
            if missing is not None:
                path.append(str(missing))
        raise ActionParamsValidationError(
            path=".".join(path) or "$",
            validator=str(error.validator),
        ) from None
