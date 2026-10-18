"""从远端 LLM 提供商发现可用模型。"""
from __future__ import annotations

from typing import Any, Protocol

import httpx

from common.logging import get_logger
from llm.catalog import DiscoveredModel, SyncCounts
from models.llm_provider import LlmProvider, ProviderProtocol
from llm.provider_url import ProviderUrlError, ProviderUrlValidator

logger = get_logger(__file__)

DISCOVERY_TIMEOUT_SECONDS = 120.0
OPENAI_SHAPED_PROTOCOLS = {
    ProviderProtocol.OPENAI_COMPLETION,
    ProviderProtocol.OPENAI_RESPONSES,
    ProviderProtocol.DEEPSEEK,
}


class ModelDiscoveryError(RuntimeError):
    """模型发现失败；消息只包含可安全对外展示的摘要。"""


class ProviderDisabledError(ModelDiscoveryError):
    """提供商已禁用，不能执行模型发现。"""


class DiscoveryCatalog(Protocol):
    async def require_provider(self, provider_id: int) -> LlmProvider: ...

    async def replace_discovered_models(
        self, provider_id: int, discovered_models: list[DiscoveredModel]
    ) -> SyncCounts: ...

    async def record_sync_failure(self, provider_id: int, error: str) -> None: ...


def _require_object_list(body: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(body, dict) or not isinstance(body.get(key), list):
        raise ModelDiscoveryError("model discovery received an invalid response")
    items = body[key]
    if not all(isinstance(item, dict) for item in items):
        raise ModelDiscoveryError("model discovery received an invalid response")
    return items


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelDiscoveryError("model discovery received an invalid response")
    return value.strip()


def _validate_unique(models: list[DiscoveredModel]) -> list[DiscoveredModel]:
    model_ids = [model.remote_model_id for model in models]
    if len(model_ids) != len(set(model_ids)):
        raise ModelDiscoveryError("model discovery received an invalid response")
    return models


def parse_models(
    protocol: ProviderProtocol, body: object
) -> list[DiscoveredModel]:
    """严格解析各提供商的模型列表响应。"""
    if protocol == ProviderProtocol.GEMINI:
        models = []
        for item in _require_object_list(body, "models"):
            name = _required_string(item, "name")
            if not name.startswith("models/") or len(name) == len("models/"):
                raise ModelDiscoveryError("model discovery received an invalid response")
            model_id = name.removeprefix("models/")
            models.append(
                DiscoveredModel(model_id, _required_string(item, "displayName"))
            )
        return _validate_unique(models)

    if protocol in OPENAI_SHAPED_PROTOCOLS:
        return _validate_unique([
            DiscoveredModel(model_id, model_id)
            for item in _require_object_list(body, "data")
            for model_id in [_required_string(item, "id")]
        ])

    if protocol == ProviderProtocol.CLAUDE:
        return _validate_unique([
            DiscoveredModel(
                _required_string(item, "id"),
                _required_string(item, "display_name"),
            )
            for item in _require_object_list(body, "data")
        ])

    raise ModelDiscoveryError("model discovery protocol is unsupported")


def discovery_request(provider: LlmProvider) -> httpx.Request:
    """构造不发送的提供商模型发现请求。"""
    if not isinstance(provider.base_url, str) or not provider.base_url.strip():
        raise ModelDiscoveryError("model discovery base URL is missing")
    base_url = httpx.URL(provider.base_url)
    if base_url.query or base_url.fragment:
        raise ModelDiscoveryError("model discovery base URL is invalid")

    version = (
        "v1beta"
        if provider.protocol == ProviderProtocol.GEMINI
        else "v1"
    )
    base_path = base_url.path.rstrip("/")
    if base_path.rsplit("/", 1)[-1] != version:
        base_path = f"{base_path}/{version}"
    models_url = base_url.copy_with(path=f"{base_path}/models")

    if provider.protocol in OPENAI_SHAPED_PROTOCOLS:
        return httpx.Request(
            "GET",
            models_url,
            headers={"Authorization": f"Bearer {provider.api_key}"},
        )
    if provider.protocol == ProviderProtocol.GEMINI:
        return httpx.Request(
            "GET",
            models_url,
            headers={"x-goog-api-key": provider.api_key},
        )
    if provider.protocol == ProviderProtocol.CLAUDE:
        return httpx.Request(
            "GET",
            models_url,
            headers={
                "x-api-key": provider.api_key,
                "anthropic-version": "2023-06-01",
            },
        )
    raise ModelDiscoveryError("model discovery protocol is unsupported")


class ModelDiscoveryService:
    def __init__(self, catalog: DiscoveryCatalog, client: httpx.AsyncClient, url_validator: ProviderUrlValidator | None = None) -> None:
        self._catalog = catalog
        self._client = client
        self._url_validator = url_validator or ProviderUrlValidator()

    async def _record_failure(self, provider_id: int, summary: str) -> None:
        try:
            await self._catalog.record_sync_failure(provider_id, summary)
        except Exception as error:
            logger.error(
                "Failed to record LLM model discovery failure: {}",
                type(error).__name__,
            )

    async def sync(self, provider_id: int) -> SyncCounts:
        provider = await self._catalog.require_provider(provider_id)
        if not provider.enabled:
            await self._record_failure(provider_id, "provider disabled")
            raise ProviderDisabledError("model discovery provider is disabled")

        try:
            await self._url_validator.validate(provider.base_url or "")
            request = discovery_request(provider)
            response = await self._client.get(
                request.url,
                headers=request.headers,
                timeout=DISCOVERY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            models = parse_models(provider.protocol, response.json())
        except ProviderUrlError as error:
            await self._record_failure(provider_id, "unsafe provider URL")
            raise ModelDiscoveryError("model discovery provider URL is unsafe") from error
        except ModelDiscoveryError:
            await self._record_failure(provider_id, "invalid response")
            raise
        except httpx.HTTPStatusError as error:
            summary = f"HTTP status {error.response.status_code}"
            await self._record_failure(provider_id, summary)
            raise ModelDiscoveryError(f"model discovery {summary}") from error
        except (httpx.HTTPError, ValueError) as error:
            summary = type(error).__name__
            await self._record_failure(provider_id, summary)
            raise ModelDiscoveryError(
                f"model discovery failed ({summary})"
            ) from error

        return await self._catalog.replace_discovered_models(provider_id, models)
