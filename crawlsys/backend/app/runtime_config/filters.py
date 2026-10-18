"""Compile validated cleaner filters into parameterized PostgreSQL SQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from .models import FilterRule


@dataclass(frozen=True)
class CompiledFilters:
    sql: str
    params: dict[str, Any]


def _json_expression(path_param: str) -> str:
    return (
        "jsonb_extract_path(extend::jsonb, "
        f"VARIADIC CAST(:{path_param} AS text[]))"
    )


def _numeric_json_expression(expression: str) -> str:
    text_value = f"({expression} #>> '{{}}')"
    return (
        "CASE "
        f"WHEN jsonb_typeof({expression}) = 'number' THEN {text_value}::numeric "
        f"WHEN jsonb_typeof({expression}) = 'string' "
        f"AND {text_value} ~ '^[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?$' "
        f"THEN {text_value}::numeric END"
    )


def compile_filters(rules: Sequence[FilterRule]) -> CompiledFilters:
    clauses: list[str] = []
    params: dict[str, Any] = {}

    for index, rule in enumerate(rules):
        value_name = f"filter_value_{index}"
        if rule.field.startswith("extend_data."):
            path_name = f"filter_path_{index}"
            params[path_name] = rule.field.split(".")[1:]
            expression = _json_expression(path_name)
            is_json = True
        else:
            expression = rule.field
            is_json = False

        if rule.operator == "exists":
            clauses.append(f"{expression} IS NOT NULL")
            continue

        if rule.operator == "in":
            placeholders = []
            for value_index, value in enumerate(rule.value):
                item_name = f"{value_name}_{value_index}"
                params[item_name] = json.dumps(value) if is_json else value
                placeholder = f":{item_name}"
                placeholders.append(
                    f"CAST({placeholder} AS jsonb)" if is_json else placeholder
                )
            clauses.append(f"{expression} IN ({', '.join(placeholders)})")
            continue

        if is_json and rule.operator in {">", ">=", "<", "<="}:
            expression = _numeric_json_expression(expression)
            params[value_name] = rule.value
            clauses.append(f"{expression} {rule.operator} :{value_name}")
        elif is_json:
            params[value_name] = json.dumps(rule.value)
            clauses.append(
                f"{expression} {rule.operator} CAST(:{value_name} AS jsonb)"
            )
        else:
            params[value_name] = rule.value
            clauses.append(f"{expression} {rule.operator} :{value_name}")

    return CompiledFilters(sql=" AND ".join(clauses), params=params)
