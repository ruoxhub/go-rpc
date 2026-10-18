"""Validation helpers for administrator-configured SQL fragments."""

from core.constants import (
    _EXPR_RE,
    _IDENT_RE,
    _ORDER_BY_RE,
    _WHERE_DANGEROUS,
    _WHERE_RE,
)


def ident(name: str, label: str = "SQL identifier") -> str:
    if not _IDENT_RE.fullmatch(name):
        raise ValueError(f"Invalid {label}: {name!r}")
    return name


def expr(name: str, label: str = "SQL expression") -> str:
    if _WHERE_DANGEROUS.search(name) or not _EXPR_RE.fullmatch(name):
        raise ValueError(f"Invalid {label}: {name!r}")
    return name


def validate_where(clause: str) -> str:
    if _WHERE_DANGEROUS.search(clause):
        raise ValueError(f"Unsafe WHERE clause rejected: {clause!r}")
    if not _WHERE_RE.match(clause.strip()):
        raise ValueError(f"Invalid WHERE clause: {clause!r}")
    return clause


def validate_order_by(order_by: list[str]) -> list[str]:
    if not order_by:
        return []
    cleaned: list[str] = []
    for raw in order_by:
        item = (raw or "").strip()
        if not _ORDER_BY_RE.fullmatch(item):
            raise ValueError(f"Invalid order_by item: {raw!r}")
        cleaned.append(item)
    return cleaned


def limit_clause(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError(f"Invalid source.limit: {limit!r} (expected int 1..500)")
    return limit
