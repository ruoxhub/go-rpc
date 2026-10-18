from datetime import datetime

import pytest

from runtime_config.filters import compile_filters
from runtime_config.models import FilterRule


def test_empty_filters_compile_to_no_condition():
    compiled = compile_filters([])

    assert compiled.sql == ""
    assert compiled.params == {}


@pytest.mark.parametrize("operator", ["=", "!=", ">", ">=", "<", "<="])
def test_plain_column_comparisons_are_parameterized(operator):
    compiled = compile_filters(
        [FilterRule(field="view_count", operator=operator, value=10)]
    )

    assert compiled.sql == f"view_count {operator} :filter_value_0"
    assert compiled.params == {"filter_value_0": 10}


def test_in_uses_individual_bound_values():
    compiled = compile_filters(
        [FilterRule(field="view_count", operator="in", value=[1, 2])]
    )

    assert compiled.sql == "view_count IN (:filter_value_0_0, :filter_value_0_1)"
    assert compiled.params == {"filter_value_0_0": 1, "filter_value_0_1": 2}


def test_exists_and_multiple_rules_use_and():
    compiled = compile_filters(
        [
            FilterRule(field="extend_data.label", operator="exists", value=None),
            FilterRule(field="view_count", operator=">", value=0),
        ]
    )

    assert " AND " in compiled.sql
    assert ":filter_path_0" in compiled.sql
    assert compiled.params == {"filter_path_0": ["label"], "filter_value_1": 0}


def test_json_path_and_value_are_not_interpolated_into_sql():
    compiled = compile_filters(
        [
            FilterRule(
                field="extend_data.metrics.play_count",
                operator="=",
                value="' OR TRUE --",
            )
        ]
    )

    assert "metrics" not in compiled.sql
    assert "play_count" not in compiled.sql
    assert "OR TRUE" not in compiled.sql
    assert compiled.params["filter_path_0"] == ["metrics", "play_count"]
    assert compiled.params["filter_value_0"] == '"\' OR TRUE --"'


def test_date_column_accepts_parameterized_string_comparison():
    compiled = compile_filters(
        [FilterRule(field="pub_time", operator=">=", value="2026-01-01T08:00:00+08:00")]
    )

    assert compiled.sql == "pub_time >= :filter_value_0"
    assert compiled.params == {"filter_value_0": datetime(2026, 1, 1)}
    assert compiled.params["filter_value_0"].tzinfo is None


def test_json_numeric_comparison_guards_casts():
    compiled = compile_filters(
        [FilterRule(field="extend_data.score", operator=">", value=0)]
    )

    assert "jsonb_typeof" in compiled.sql
    assert "~" in compiled.sql
    assert "::numeric" in compiled.sql
    assert compiled.params["filter_value_0"] == 0
