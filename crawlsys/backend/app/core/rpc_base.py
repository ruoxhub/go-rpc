"""Common safety and validation utilities for RPC clients."""

from __future__ import annotations

from typing import Any


def validate_json_depth(data: Any, max_depth: int = 64, current_depth: int = 0) -> bool:
    """递归校验 JSON 结构深度，防止恶意深层嵌套导致的栈溢出或内存耗尽。"""
    if current_depth > max_depth:
        return False
    if isinstance(data, dict):
        return all(validate_json_depth(v, max_depth, current_depth + 1) for v in data.values())
    if isinstance(data, list):
        return all(validate_json_depth(v, max_depth, current_depth + 1) for v in data)
    return True


def validate_json_nodes(data: Any, max_nodes: int = 100_000) -> bool:
    """统计 JSON 节点总数，防止超大结构导致解析耗时过长。"""
    count = 0

    def _traverse(node: Any) -> bool:
        nonlocal count
        count += 1
        if count > max_nodes:
            return False
        if isinstance(node, dict):
            for v in node.values():
                if not _traverse(v):
                    return False
        elif isinstance(node, list):
            for item in node:
                if not _traverse(item):
                    return False
        return True

    return _traverse(data)


def validate_response_size(content_length: int | None, max_bytes: int) -> bool:
    """基于 Content-Length 头部预检响应体积，超出限制时快速失败。"""
    if content_length is None:
        return True
    return content_length <= max_bytes


__all__ = [
    "validate_json_depth",
    "validate_json_nodes",
    "validate_response_size",
]
