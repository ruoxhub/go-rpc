"""go-rpc HTTP 调用端。

本文件由两部分组成（原 backend/app/core/rpc.py 已并入此处）：

- ``RpcHTTPClient`` / ``AsyncRpcHTTPClient``：轻量同步/异步调用客户端，
  返回剥壳后的 ``data``，``code != 0`` 抛 ``RpcAPIError``。
- ``RpcClient``：生产级异步调用客户端（原 backend 独有），带
  RetryBudget 限流重试、full-jitter 退避、流式响应尺寸护栏与 JSON
  结构校验，返回完整信封（dict），错误统一为 ``RpcError`` 家族。

两套客户端鉴权头与错误语义刻意保持不同，调用方按需选择。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "AsyncRpcHTTPClient",
    "BlockedRpcError",
    "InvalidRpcJsonError",
    "PermanentRpcError",
    "RateLimitedRpcError",
    "RetryableRpcError",
    "RetryBudget",
    "RpcAPIError",
    "RpcClient",
    "RpcError",
    "RpcHTTPClient",
    "RpcResponseTooLargeError",
    "RpcTransportError",
    "classify_http_status",
    "format_error",
    "full_jitter_delay",
    "redact_secrets",
    "retry_after_seconds",
]

# RpcClient 重试退避常量
_BASE_DELAY = 0.5
_MAX_DELAY = 10.0
_RETRYABLE_EXCEPTIONS = (httpx.TransportError, asyncio.TimeoutError)

# ---------------------------------------------------------------------------
# 轻量客户端（同步 + 异步）：剥壳返回 data，code != 0 抛 RpcAPIError
# ---------------------------------------------------------------------------


class RpcTransportError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RpcAPIError(Exception):
    def __init__(self, message: str, code: int, raw_response: dict[str, Any]):
        super().__init__(message)
        self.code = code
        self.raw_response = raw_response


def _payload(
    group: str, action: str, params: Any, timeout: float | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"group": group, "action": action, "params": params}
    if timeout is not None and timeout > 0:
        body["timeout"] = math.ceil(timeout)
    return body


def _result(response: httpx.Response) -> Any:
    if response.status_code < 200 or response.status_code >= 300:
        raise RpcTransportError(
            f"invoke returned HTTP status {response.status_code}", response.status_code
        )
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise RpcTransportError("invalid JSON response") from exc
    if not isinstance(data, dict):
        raise RpcTransportError("invoke response must be an object")
    code = data.get("code", 0)
    if code != 0:
        raise RpcAPIError(str(data.get("message", "invoke failed")), code, data)
    if "data" in data:
        return data["data"]
    return {
        key: value
        for key, value in data.items()
        if key not in {"code", "message", "group", "clientId", "trace_id"}
    }


class RpcHTTPClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def invoke(
        self, group: str, action: str, params: Any, timeout: float | None = None
    ) -> Any:
        request_timeout = (
            min(self.timeout, timeout)
            if timeout is not None and timeout > 0
            else self.timeout
        )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            response = self._client.post(
                f"{self.base_url}/business/invoke",
                json=_payload(group, action, params, timeout),
                headers=headers,
                timeout=request_timeout,
            )
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"invoke request failed: {exc}") from exc
        return _result(response)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class AsyncRpcHTTPClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def invoke(
        self, group: str, action: str, params: Any, timeout: float | None = None
    ) -> Any:
        request_timeout = (
            min(self.timeout, timeout)
            if timeout is not None and timeout > 0
            else self.timeout
        )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            response = await self._client.post(
                f"{self.base_url}/business/invoke",
                json=_payload(group, action, params, timeout),
                headers=headers,
                timeout=request_timeout,
            )
        except httpx.HTTPError as exc:
            raise RpcTransportError(f"invoke request failed: {exc}") from exc
        return _result(response)

    async def close(self) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()


# ---------------------------------------------------------------------------
# 生产级客户端错误族（原 backend/app/core/rpc_errors.py）
# ---------------------------------------------------------------------------


class RpcError(Exception):
    """Base error with a stable category and optional HTTP status."""

    category = "rpc_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PermanentRpcError(RpcError):
    category = "permanent"


class RpcResponseTooLargeError(PermanentRpcError):
    category = "response_too_large"


class InvalidRpcJsonError(PermanentRpcError):
    category = "invalid_json"


class RateLimitedRpcError(RpcError):
    category = "rate_limited"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after_seconds = retry_after_seconds


class BlockedRpcError(RpcError):
    category = "blocked"


class RetryableRpcError(RpcError):
    category = "retryable"


def _retry_delay_or_none(
    attempt: int,
    max_retries: int,
    budget: RetryBudget,
    *,
    retryable: bool,
) -> float | None:
    """Decide whether to retry and return the full-jitter backoff delay.

    Short-circuit order is preserved: the retry budget is only consumed
    when the error is retryable and attempts remain.
    """
    if not (retryable and attempt < max_retries and budget.consume_retry()):
        return None
    return full_jitter_delay(attempt, base_delay=_BASE_DELAY, max_delay=_MAX_DELAY)


def classify_http_status(status_code: int) -> type[RpcError]:
    """Map an HTTP status to the stable error exposed by ``RpcClient``."""
    if status_code == 429:
        return RateLimitedRpcError
    if status_code == 403:
        return BlockedRpcError
    if status_code >= 500:
        return RetryableRpcError
    return PermanentRpcError


# ---------------------------------------------------------------------------
# 重试助手（原 backend/app/common/backoff.py）
# ---------------------------------------------------------------------------


def full_jitter_delay(
    attempt: int,
    *,
    base_delay: float,
    max_delay: float,
    uniform: Callable[[float, float], float] = random.uniform,
) -> float:
    """Return a full-jitter exponential backoff delay."""
    upper_bound = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    return uniform(0.0, upper_bound)


def retry_after_seconds(
    headers: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse Retry-After delta-seconds or HTTP-date into a non-negative delay."""
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    value = raw.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (target - current).total_seconds())


class RetryBudget:
    """Small process-local token budget that caps retry amplification."""

    def __init__(self, ratio: float, capacity: float) -> None:
        if not 0 <= ratio <= 1:
            raise ValueError("retry budget ratio must be between 0 and 1")
        self._ratio = ratio
        self._capacity = max(0.0, capacity)
        self._credits = self._capacity

    def record_request(self) -> None:
        self._credits = min(self._capacity, self._credits + self._ratio)

    def consume_retry(self) -> bool:
        if self._credits < 1.0:
            return False
        self._credits -= 1.0
        return True


# ---------------------------------------------------------------------------
# 错误脱敏（原 backend/app/common/errors.py 中 RpcClient 用到的最小子集）
# ---------------------------------------------------------------------------

_SECRET_VALUE = re.compile(
    r"(?ix)((?:[a-z0-9]+[_-])*(?:api[_-]?key|token|password|secret[_-]?key|secret|access[_-]?key))"
    r"(?![a-z0-9_-])(\s*[:=]\s*)"
    r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r'"(?:\\.|[^"\\])*\\?\Z|\'(?:\\.|[^\'\\])*\\?\Z|[^\s,;]+)'
)

_BEARER_TOKEN = re.compile(r"(?i)\b(Bearer)(\s+)(\S+)")
_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s]+")


def _replace_secret(match: re.Match[str]) -> str:
    value = match.group(3)
    quote = value[0] if value[:1] in {'"', "'"} else ""
    return f"{match.group(1)}{match.group(2)}{quote}***{quote}"


def redact_secrets(message: str) -> str:
    message = _URL.sub("[REDACTED_URL]", message)
    message = _BEARER_TOKEN.sub(r"\1\2***", message)
    return _SECRET_VALUE.sub(_replace_secret, message)


def format_error(exc: BaseException, max_length: int = 2000) -> str:
    """Return a bounded exception type/message with credentials redacted."""
    return f"{type(exc).__name__}: {redact_secrets(str(exc))}"[:max_length]


# ---------------------------------------------------------------------------
# 响应尺寸 / JSON 结构护栏（原 backend/app/core/rpc.py 内部函数）
# ---------------------------------------------------------------------------

_JSON_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _response_size_error() -> RpcResponseTooLargeError:
    return RpcResponseTooLargeError("RPC response exceeds configured size limit")


def _content_length(headers: httpx.Headers) -> int | None:
    values: list[int] = []
    for raw_value in headers.get_list("Content-Length"):
        for part in raw_value.split(","):
            value = part.strip()
            if not value or not value.isascii() or not value.isdigit():
                raise _response_size_error()
            try:
                # isdigit() 已保证 ASCII 纯数字，此分支不可达。
                values.append(int(value))
            except ValueError:  # pragma: no cover
                raise _response_size_error() from None
    if not values:
        return None
    if any(value != values[0] for value in values[1:]):
        raise _response_size_error()
    return values[0]


def _require_identity_encoding(headers: httpx.Headers) -> None:
    for raw_value in headers.get_list("Content-Encoding"):
        encodings = [part.strip().lower() for part in raw_value.split(",")]
        if not encodings or any(encoding != "identity" for encoding in encodings):
            raise _response_size_error()


def _skip_json_whitespace(value: str, index: int) -> int:
    while index < len(value) and value[index] in " \t\r\n":
        index += 1
    return index


def _scan_json_string(value: str, index: int, max_string_bytes: int) -> int:
    end = index + 1
    while end < len(value):
        char = value[end]
        if char == '"':
            try:
                decoded = json.loads(value[index : end + 1])
                encoded_size = len(decoded.encode("utf-8"))
            except (UnicodeEncodeError, json.JSONDecodeError) as exc:
                raise InvalidRpcJsonError("RPC response is not valid JSON") from exc
            if encoded_size > max_string_bytes:
                raise InvalidRpcJsonError("RPC response exceeds JSON structure limits")
            return end + 1
        if char == "\\":
            end += 2
            continue
        if ord(char) < 0x20:
            raise InvalidRpcJsonError("RPC response is not valid JSON")
        end += 1
    raise InvalidRpcJsonError("RPC response is not valid JSON")


def _validate_json_structure(
    content: bytes | bytearray,
    *,
    max_depth: int,
    max_nodes: int,
    max_array_items: int,
    max_string_bytes: int,
) -> str:
    if max_depth < 0 or max_nodes < 1 or max_array_items < 0 or max_string_bytes < 0:
        raise InvalidRpcJsonError("RPC JSON structure limits are invalid")
    try:
        value = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidRpcJsonError("RPC response is not valid JSON") from exc

    index = _skip_json_whitespace(value, 0)
    if index >= len(value) or value[index] not in "[{":
        raise InvalidRpcJsonError("RPC response must be a JSON object or array")

    stack: list[tuple[str, str, int]] = []
    nodes = 0

    def consume_value(start: int, depth: int) -> int:
        nonlocal nodes
        if depth > max_depth or nodes >= max_nodes:
            raise InvalidRpcJsonError("RPC response exceeds JSON structure limits")
        nodes += 1
        char = value[start]
        if char == "{":
            stack.append(("object", "key_or_end", 0))
            return start + 1
        if char == "[":
            stack.append(("array", "value_or_end", 0))
            return start + 1
        if char == '"':
            return _scan_json_string(value, start, max_string_bytes)
        if value.startswith("true", start):
            return start + 4
        if value.startswith("false", start):
            return start + 5
        if value.startswith("null", start):
            return start + 4
        match = _JSON_NUMBER.match(value, start)
        if match is not None:
            return match.end()
        raise InvalidRpcJsonError("RPC response is not valid JSON")

    index = consume_value(index, 0)
    while stack:
        index = _skip_json_whitespace(value, index)
        if index >= len(value):
            raise InvalidRpcJsonError("RPC response is not valid JSON")
        kind, state, item_count = stack[-1]
        char = value[index]

        if kind == "object":
            if state in {"key_or_end", "key"}:
                if state == "key_or_end" and char == "}":
                    stack.pop()
                    index += 1
                    continue
                if char != '"':
                    raise InvalidRpcJsonError("RPC response is not valid JSON")
                index = _scan_json_string(value, index, max_string_bytes)
                stack[-1] = (kind, "colon", item_count)
                continue
            if state == "colon":
                if char != ":":
                    raise InvalidRpcJsonError("RPC response is not valid JSON")
                stack[-1] = (kind, "value", item_count)
                index += 1
                continue
            if state == "value":
                stack[-1] = (kind, "comma_or_end", item_count)
                index = consume_value(index, len(stack))
                continue
            if char == ",":
                stack[-1] = (kind, "key", item_count)
                index += 1
                continue
            if char == "}":
                stack.pop()
                index += 1
                continue
            raise InvalidRpcJsonError("RPC response is not valid JSON")

        if state in {"value_or_end", "value"}:
            if state == "value_or_end" and char == "]":
                stack.pop()
                index += 1
                continue
            if item_count >= max_array_items:
                raise InvalidRpcJsonError("RPC response exceeds JSON structure limits")
            stack[-1] = (kind, "comma_or_end", item_count + 1)
            index = consume_value(index, len(stack))
            continue
        if char == ",":
            stack[-1] = (kind, "value", item_count)
            index += 1
            continue
        if char == "]":
            stack.pop()
            index += 1
            continue
        raise InvalidRpcJsonError("RPC response is not valid JSON")

    if _skip_json_whitespace(value, index) != len(value):
        raise InvalidRpcJsonError("RPC response is not valid JSON")
    return value


# ---------------------------------------------------------------------------
# 生产级异步客户端（原 backend/app/core/rpc.py 的 RpcClient）
# ---------------------------------------------------------------------------


class RpcClient:
    """Async HTTP client for go-rpc /business/invoke endpoint.

    鉴权使用 ``sekiro-token`` 头；仅在分类为 ``RetryableRpcError`` 时重试，
    受进程内 ``RetryBudget`` 约束并使用 full-jitter 退避。指定
    ``max_response_bytes`` 时走流式读取并强制 identity 编码与 JSON 结构
    上限校验。
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str = "",
        timeout: int = 60,
        max_retries: int = 3,
        config_store: Any = None,
        retry_budget_ratio: float = 0.2,
    ):
        if base_url is None and config_store is None:
            raise TypeError("base_url or config_store is required")
        self.base_url = base_url.rstrip("/") if base_url is not None else ""
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self._retry_budget = RetryBudget(
            retry_budget_ratio, capacity=max(0, max_retries - 1)
        )
        self.config_store = config_store
        try:
            init_read_timeout = float(timeout)
        except (TypeError, ValueError):
            raise
        self.client = httpx.AsyncClient(
            # 内部 go-rpc 是固定本地端点，不应被宿主进程注入的
            # ALL_PROXY / NO_PROXY 劫持；同时规避 httpx 0.28 对形如
            # `*::1` 的 NO_PROXY 项解析为 `Invalid port: ':1'` 的缺陷。
            trust_env=False,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            timeout=httpx.Timeout(
                connect=10.0, read=init_read_timeout, write=10.0, pool=10.0
            ),
        )

    async def invoke(
        self,
        platform: str,
        action: str,
        params: dict,
        *,
        max_response_bytes: int | None = None,
        json_max_depth: int = 64,
        json_max_nodes: int = 100_000,
        max_array_items: int = 20,
        max_string_bytes: int = 256 * 1024,
    ) -> Any:
        self._retry_budget.record_request()
        if self.config_store is not None:
            settings = await self.config_store.get_rpc()
            base_url = settings.base_url.rstrip("/")
            timeout = settings.timeout_seconds
        else:
            base_url = self.base_url
            timeout = self.timeout
        payload = {"group": platform, "action": action, "params": params}
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["sekiro-token"] = self.token

        last_exc: RpcError | None = None
        attempt = 0
        try:
            read_timeout = float(timeout)
        except (TypeError, ValueError):
            raise
        request_timeout = httpx.Timeout(
            connect=10.0, read=read_timeout, write=10.0, pool=10.0
        )
        for attempt in range(1, self.max_retries + 1):
            attempt_started = time.monotonic()
            try:
                url = f"{base_url}/business/invoke"
                if max_response_bytes is None:
                    resp = await self.client.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=request_timeout,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                else:
                    bounded_headers = {**headers, "Accept-Encoding": "identity"}
                    async with self.client.stream(
                        "POST",
                        url,
                        json=payload,
                        headers=bounded_headers,
                        timeout=request_timeout,
                    ) as resp:
                        resp.raise_for_status()
                        _require_identity_encoding(resp.headers)
                        declared_size = _content_length(resp.headers)
                        if (
                            declared_size is not None
                            and declared_size > max_response_bytes
                        ):
                            raise _response_size_error()

                        content = bytearray()
                        async for chunk in resp.aiter_bytes():
                            if len(chunk) > max_response_bytes - len(content):
                                raise _response_size_error()
                            content.extend(chunk)
                    if declared_size is not None and len(content) != declared_size:
                        raise _response_size_error()
                    try:
                        json_text = _validate_json_structure(
                            content,
                            max_depth=json_max_depth,
                            max_nodes=json_max_nodes,
                            max_array_items=max_array_items,
                            max_string_bytes=max_string_bytes,
                        )
                        result = json.loads(json_text)
                    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
                        raise InvalidRpcJsonError(
                            "RPC response is not valid JSON"
                        ) from exc
                logger.debug(
                    "RPC invoke platform=%s action=%s attempt=%d outcome=success latency_ms=%d",
                    platform,
                    action,
                    attempt,
                    int((time.monotonic() - attempt_started) * 1000),
                )
                return result
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                error_type = classify_http_status(status_code)
                error_kwargs: dict[str, Any] = {"status_code": status_code}
                if status_code == 429:
                    error_kwargs["retry_after_seconds"] = retry_after_seconds(
                        getattr(e.response, "headers", {})
                    )
                last_exc = error_type(
                    f"RPC HTTP {status_code}: {format_error(e, max_length=300)}",
                    **error_kwargs,
                )
                # 仅对统一分类后的瞬时服务端错误重试（预算消耗与退避
                # 计算在 _retry_delay_or_none 内保持原短路顺序）。
                delay = _retry_delay_or_none(
                    attempt,
                    self.max_retries,
                    self._retry_budget,
                    retryable=(error_type is RetryableRpcError),
                )
                if delay is None:
                    break
                logger.warning(
                    "RPC invoke platform=%s action=%s attempt=%d outcome=%s "
                    "latency_ms=%d retry_in_seconds=%.1f error=%s",
                    platform,
                    action,
                    attempt,
                    last_exc.category,
                    int((time.monotonic() - attempt_started) * 1000),
                    delay,
                    last_exc,
                )
                await asyncio.sleep(delay)
            except _RETRYABLE_EXCEPTIONS as e:
                last_exc = RetryableRpcError(format_error(e, max_length=300))
                delay = _retry_delay_or_none(
                    attempt,
                    self.max_retries,
                    self._retry_budget,
                    retryable=True,
                )
                if delay is None:
                    break
                logger.warning(
                    "RPC invoke platform=%s action=%s attempt=%d outcome=%s "
                    "latency_ms=%d retry_in_seconds=%.1f error=%s",
                    platform,
                    action,
                    attempt,
                    last_exc.category,
                    int((time.monotonic() - attempt_started) * 1000),
                    delay,
                    last_exc,
                )
                await asyncio.sleep(delay)

        logger.error(
            "RPC invoke platform=%s action=%s attempts=%d outcome=%s error=%s",
            platform,
            action,
            attempt,
            last_exc.category if last_exc is not None else "unknown",
            last_exc,
        )
        if last_exc is None:
            raise RuntimeError("RPC invoke failed without a captured error")
        raise last_exc

    async def __aenter__(self) -> RpcClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.aclose()
