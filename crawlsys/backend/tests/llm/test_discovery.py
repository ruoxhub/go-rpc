from __future__ import annotations

import httpx
import pytest

from llm.catalog import DiscoveredModel, SyncCounts
from llm.discovery import (
    ModelDiscoveryError,
    ModelDiscoveryService,
    discovery_request,
    parse_models,
)
from llm.provider_url import ProviderUrlValidator
from models.llm_provider import LlmProvider, ProviderProtocol


def make_provider(
    *,
    id: int = 7,
    protocol: ProviderProtocol = ProviderProtocol.OPENAI_COMPLETION,
    base_url: str | None = "https://llm.example/",
    api_key: str = "top-secret",
    enabled: bool = True,
) -> LlmProvider:
    return LlmProvider(
        id=id,
        name="Provider",
        litellm_prefix=protocol.litellm_prefix,
        protocol=protocol,
        base_url=base_url,
        api_key=api_key,
        enabled=enabled,
    )


class SafeUrlValidator(ProviderUrlValidator):
    async def validate(self, url: str) -> None:
        assert url.startswith("https://")


@pytest.mark.parametrize(
    "protocol",
    [
        ProviderProtocol.OPENAI_COMPLETION,
        ProviderProtocol.OPENAI_RESPONSES,
        ProviderProtocol.DEEPSEEK,
    ],
)
def test_parse_models_supports_openai_shaped_formats(protocol):
    assert parse_models(protocol, {"data": [{"id": "model-a"}]}) == [
        DiscoveredModel("model-a", "model-a")
    ]


@pytest.mark.parametrize(
    ("protocol", "body", "expected"),
    [
        (
            ProviderProtocol.GEMINI,
            {"models": [{"name": "models/gemini-pro", "displayName": "Gemini Pro"}]},
            [DiscoveredModel("gemini-pro", "Gemini Pro")],
        ),
        (
            ProviderProtocol.CLAUDE,
            {"data": [{"id": "claude-3", "display_name": "Claude 3"}]},
            [DiscoveredModel("claude-3", "Claude 3")],
        ),
    ],
)
def test_parse_models_supports_native_formats(protocol, body, expected):
    assert parse_models(protocol, body) == expected


@pytest.mark.parametrize(
    ("protocol", "body"),
    [
        (ProviderProtocol.OPENAI_COMPLETION, {}),
        (ProviderProtocol.OPENAI_COMPLETION, {"data": [{"id": 3}]}),
        (ProviderProtocol.GEMINI, {"models": [{"name": "invalid"}]}),
        (ProviderProtocol.CLAUDE, {"data": "invalid"}),
    ],
)
def test_parse_models_rejects_invalid_response_shapes(protocol, body):
    with pytest.raises(ModelDiscoveryError, match="invalid response"):
        parse_models(protocol, body)


@pytest.mark.parametrize(
    ("protocol", "body"),
    [
        (ProviderProtocol.OPENAI_COMPLETION, {"data": [{"id": "  "}]}),
        (
            ProviderProtocol.GEMINI,
            {"models": [{"name": "models/gemini", "displayName": " "}]},
        ),
        (
            ProviderProtocol.CLAUDE,
            {"data": [
                {"id": "claude", "display_name": "Claude"},
                {"id": "claude", "display_name": "Claude"},
            ]},
        ),
    ],
)
def test_parse_models_rejects_blank_fields_and_duplicate_ids(protocol, body):
    with pytest.raises(ModelDiscoveryError, match="invalid response"):
        parse_models(protocol, body)


@pytest.mark.parametrize(
    ("protocol", "url", "headers"),
    [
        (
            ProviderProtocol.OPENAI_COMPLETION,
            "https://llm.example/v1/models",
            {"Authorization": "Bearer top-secret"},
        ),
        (
            ProviderProtocol.OPENAI_RESPONSES,
            "https://llm.example/v1/models",
            {"Authorization": "Bearer top-secret"},
        ),
        (
            ProviderProtocol.DEEPSEEK,
            "https://llm.example/v1/models",
            {"Authorization": "Bearer top-secret"},
        ),
        (
            ProviderProtocol.GEMINI,
            "https://llm.example/v1beta/models",
            {"x-goog-api-key": "top-secret"},
        ),
        (
            ProviderProtocol.CLAUDE,
            "https://llm.example/v1/models",
            {"x-api-key": "top-secret", "anthropic-version": "2023-06-01"},
        ),
    ],
)
def test_discovery_request_builds_protocol_specific_request(protocol, url, headers):
    request = discovery_request(make_provider(protocol=protocol))
    assert str(request.url) == url
    for name, value in headers.items():
        assert request.headers[name] == value


@pytest.mark.parametrize(
    ("protocol", "base_url", "expected"),
    [
        (ProviderProtocol.OPENAI_COMPLETION, "https://example.test/v1", "https://example.test/v1/models"),
        (ProviderProtocol.CLAUDE, "https://example.test/api/v1/", "https://example.test/api/v1/models"),
        (ProviderProtocol.GEMINI, "https://example.test/v1beta", "https://example.test/v1beta/models"),
        (ProviderProtocol.GEMINI, "https://example.test/proxy", "https://example.test/proxy/v1beta/models"),
    ],
)
def test_discovery_request_does_not_duplicate_version_path(protocol, base_url, expected):
    provider = make_provider(protocol=protocol, base_url=base_url)
    assert str(discovery_request(provider).url) == expected


@pytest.mark.parametrize("base_url", ["https://example.test?v=1", "https://example.test/#fragment"])
def test_discovery_request_rejects_query_and_fragment(base_url):
    with pytest.raises(ModelDiscoveryError, match="base URL"):
        discovery_request(make_provider(base_url=base_url))


class Catalog:
    def __init__(self, provider):
        self.provider = provider
        self.replacements = []
        self.sync_status = None
        self.success_calls = 0
        self.failure_error = None

    async def require_provider(self, provider_id):
        assert provider_id == self.provider.id
        return self.provider

    async def replace_discovered_models(self, provider_id, models):
        self.replacements.append((provider_id, models))
        return SyncCounts(1, 0, 0)

    async def record_sync_success(self, provider_id):
        self.success_calls += 1
        self.sync_status = ("success", provider_id, None)

    async def record_sync_failure(self, provider_id, error):
        if self.failure_error:
            raise self.failure_error
        self.sync_status = ("failed", provider_id, error)


@pytest.mark.asyncio
async def test_sync_fetches_and_replaces_catalog():
    catalog = Catalog(make_provider())
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "gpt"}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    assert result == SyncCounts(1, 0, 0)
    assert catalog.replacements == [(7, [DiscoveredModel("gpt", "gpt")])]
    assert catalog.success_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 500])
async def test_http_failure_is_sanitized_and_does_not_replace(status):
    catalog = Catalog(make_provider())
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, text="body-secret", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ModelDiscoveryError) as exc_info:
            await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    message = str(exc_info.value)
    assert str(status) in message
    assert "top-secret" not in message
    assert "body-secret" not in message
    assert catalog.replacements == []
    assert catalog.sync_status == ("failed", 7, f"HTTP status {status}")


@pytest.mark.asyncio
async def test_parse_failure_does_not_replace_existing_catalog():
    catalog = Catalog(make_provider())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ModelDiscoveryError):
            await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    assert catalog.replacements == []
    assert catalog.sync_status == ("failed", 7, "invalid response")


@pytest.mark.asyncio
async def test_disabled_provider_fails_before_request():
    catalog = Catalog(make_provider(enabled=False))
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelDiscoveryError, match="disabled"):
            await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    assert called is False
    assert catalog.replacements == []


@pytest.mark.asyncio
async def test_sync_uses_explicit_timeout_and_sanitizes_timeout_failure():
    catalog = Catalog(make_provider())

    def handler(request):
        assert request.extensions["timeout"] == {
            "connect": 120.0,
            "read": 120.0,
            "write": 120.0,
            "pool": 120.0,
        }
        raise httpx.ReadTimeout("body-secret top-secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ModelDiscoveryError) as exc_info:
            await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    assert "ReadTimeout" in str(exc_info.value)
    assert "body-secret" not in str(exc_info.value)
    assert "top-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_sync_failure_is_not_masked_when_recording_failure_also_fails():
    catalog = Catalog(make_provider())
    catalog.failure_error = RuntimeError("database-secret")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, text="body-secret", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ModelDiscoveryError, match="HTTP status 401") as exc_info:
            await ModelDiscoveryService(catalog, client, SafeUrlValidator()).sync(7)

    assert "database-secret" not in str(exc_info.value)
