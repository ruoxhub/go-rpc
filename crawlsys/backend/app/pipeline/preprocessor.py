"""Pre-pipeline data cleansing and normalization."""

from __future__ import annotations

from typing import Any


def clean_nul_bytes(data: Any) -> Any:
    """递归剔除数据中的 NUL 字节 (\\x00)，防止破坏 PostgreSQL 事务。"""
    if isinstance(data, str):
        return data.replace("\x00", "")
    if isinstance(data, dict):
        return {k: clean_nul_bytes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [clean_nul_bytes(v) for v in data]
    return data


__all__ = ["clean_nul_bytes"]
