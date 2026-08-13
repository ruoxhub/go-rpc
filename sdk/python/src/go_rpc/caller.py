import json
import math
from typing import Any, Optional

import httpx


class RpcTransportError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RpcAPIError(Exception):
    def __init__(self, message: str, code: int, raw_response: dict[str, Any]):
        super().__init__(message)
        self.code = code
        self.raw_response = raw_response


def _payload(group: str, action: str, params: Any, timeout: Optional[float]) -> dict[str, Any]:
    body: dict[str, Any] = {"group": group, "action": action, "params": params}
    if timeout is not None and timeout > 0:
        body["timeout"] = math.ceil(timeout)
    return body


def _result(response: httpx.Response) -> Any:
    if response.status_code < 200 or response.status_code >= 300:
        raise RpcTransportError(f"invoke returned HTTP status {response.status_code}", response.status_code)
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
    return {key: value for key, value in data.items() if key not in {"code", "message", "group", "clientId", "trace_id"}}


class RpcHTTPClient:
    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def invoke(self, group: str, action: str, params: Any, timeout: Optional[float] = None) -> Any:
        request_timeout = min(self.timeout, timeout) if timeout is not None and timeout > 0 else self.timeout
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
    def __init__(self, base_url: str, token: Optional[str] = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def invoke(self, group: str, action: str, params: Any, timeout: Optional[float] = None) -> Any:
        request_timeout = min(self.timeout, timeout) if timeout is not None and timeout > 0 else self.timeout
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
