"""Tests for SQL configuration safety helpers."""

import pytest

from core.sql_safety import expr, ident, limit_clause, validate_order_by, validate_where


@pytest.mark.parametrize("value", ["users", "public.users", "user_id"])
def test_ident_accepts_safe_identifiers(value):
    assert ident(value) == value


@pytest.mark.parametrize(
    "value",
    ["users; DROP TABLE users", "users -- comment", "1users", "safe\nDROP"],
)
def test_ident_rejects_unsafe_identifiers(value):
    with pytest.raises(ValueError, match="Invalid"):
        ident(value)


@pytest.mark.parametrize("value", ["payload->>'name'", "created_at > '2026-01-01'"])
def test_expr_accepts_configured_expressions(value):
    assert expr(value) == value


@pytest.mark.parametrize(
    "value",
    ["name; DELETE", "name -- comment", "name /* x */", "COALESCE(score, 0)"],
)
def test_expr_rejects_unsafe_expressions(value):
    with pytest.raises(ValueError, match="Invalid"):
        expr(value)


def test_validate_where_accepts_boolean_expression():
    clause = "published = FALSE AND platform = 'tiktok'"
    assert validate_where(clause) == clause


@pytest.mark.parametrize(
    "clause",
    [
        "published = FALSE; DROP TABLE seed",
        "published = FALSE -- comment",
        "id IN (SELECT id FROM secret)",
        "id = 1 /* comment */",
    ],
)
def test_validate_where_rejects_dangerous_clauses(clause):
    with pytest.raises(ValueError, match="Unsafe"):
        validate_where(clause)


def test_validate_order_by_accepts_columns_and_directions():
    assert validate_order_by(["updated_time ASC", "id", "score desc"]) == [
        "updated_time ASC",
        "id",
        "score desc",
    ]


@pytest.mark.parametrize(
    "order_by",
    [["id; DROP TABLE seed"], ["id -- comment"], ["LOWER(name)"], ["id, name"]],
)
def test_validate_order_by_rejects_unsafe_items(order_by):
    with pytest.raises(ValueError, match="Invalid"):
        validate_order_by(order_by)


@pytest.mark.parametrize("value", [1, 50, 500])
def test_limit_clause_accepts_bounds(value):
    assert limit_clause(value) == value


@pytest.mark.parametrize("value", [0, 501, True, "50"])
def test_limit_clause_rejects_out_of_range_or_non_integer(value):
    with pytest.raises(ValueError, match="1..500"):
        limit_clause(value)
