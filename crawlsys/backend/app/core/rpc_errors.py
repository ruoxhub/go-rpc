"""Normalized RPC failures exposed to workers.

错误族的唯一定义在 ``go_rpc.caller``；本模块保留作为向后兼容层，重新导出
原有符号，避免 backend 内部同时存在两套不相认的异常类。
"""

from go_rpc import (
    BlockedRpcError,
    InvalidRpcJsonError,
    PermanentRpcError,
    RateLimitedRpcError,
    RetryableRpcError,
    RpcError,
    RpcResponseTooLargeError,
    classify_http_status,
)

__all__ = [
    "BlockedRpcError",
    "InvalidRpcJsonError",
    "PermanentRpcError",
    "RateLimitedRpcError",
    "RetryableRpcError",
    "RpcError",
    "RpcResponseTooLargeError",
    "classify_http_status",
]
