from datetime import datetime
import inspect
import logging
from contextlib import asynccontextmanager
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

# 本机 FastAPI/Starlette 基线不兼容；仅为直接调用路由函数允许模块导入。
import starlette.routing
_router_init = starlette.routing.Router.__init__
_compatible_router_init = _router_init
if "on_startup" not in inspect.signature(_router_init).parameters:
    def _compatible_router_init(self, *args, on_startup=None, on_shutdown=None, **kwargs):
        _router_init(self, *args, **kwargs)
        self.on_startup = list(on_startup or [])
        self.on_shutdown = list(on_shutdown or [])
    starlette.routing.Router.__init__ = _compatible_router_init
try:
    from api.llm.routes import (create_provider, delete_provider, disable_model,
        disable_provider, enable_model, enable_provider, get_provider, list_models,
        list_providers, router, sync_models, update_provider)
finally:
    starlette.routing.Router.__init__ = _router_init
from api.llm.schemas import ProviderCreate, ProviderRead, ProviderUpdate
from api.deps import get_llm_catalog
from api.main import create_app
from core.config import SchedulerConfig
from llm.catalog import CatalogConflictError, CatalogNotFoundError, SyncCounts
from llm.discovery import ModelDiscoveryError, ProviderDisabledError
from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol
from security.credentials import (
    ENCRYPTED_PREFIX,
    ENV_NAME,
    CredentialDecryptionError,
    clear_credential_cipher_cache,
)

def provider(**values):
    defaults = dict(id=1, name="OpenAI", litellm_prefix="openai", protocol=ProviderProtocol.OPENAI_COMPLETION,
                    base_url="https://api.example.com", api_key="super-secret-key", enabled=True,
                    last_sync_status=None, last_sync_at=None, last_sync_error=None,
                    created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1))
    defaults.update(values)
    return LlmProvider(**defaults)

def test_provider_schemas_validate_secret_and_redact_it():
    with pytest.raises(ValidationError):
        ProviderCreate(name="x", protocol="openai-completion", api_key="")
    with pytest.raises(ValidationError):
        ProviderCreate(name="x", protocol="openai-completion", api_key="   ")
    with pytest.raises(ValidationError):
        ProviderUpdate(name=None)
    with pytest.raises(ValidationError):
        ProviderCreate(name="x", protocol="openai-completion", base_url="https://user:pass@example.com", api_key="secret")
    read = ProviderRead.from_orm_model(provider())
    assert "api_key" not in read.model_dump()
    assert read.api_key_configured is True
    assert read.api_key_masked == "********-key"
    assert "a" not in ProviderRead.from_orm_model(provider(api_key="a")).api_key_masked


def test_provider_read_contract_never_contains_stored_ciphertext():
    value = provider(api_key="response-secret-key")

    response = ProviderRead.from_orm_model(value).model_dump()

    assert "api_key" not in response
    assert response["api_key_configured"] is True
    assert response["api_key_masked"].endswith("-key")
    assert ENCRYPTED_PREFIX not in str(response)

def test_provider_write_schemas_do_not_accept_litellm_prefix():
    with pytest.raises(ValidationError):
        ProviderCreate(
            name="x",
            protocol="openai-completion",
            base_url="https://api.example.com",
            api_key="secret",
            litellm_prefix="custom",
        )

def test_provider_api_validation_does_not_expose_api_key(caplog):
    marker = "provider-key-must-not-leak"
    app = create_app(SchedulerConfig())
    app.dependency_overrides[get_llm_catalog] = FakeCatalog

    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = TestClient(app).post(
            "/api/llm/providers",
            json={
                "name": "x",
                "protocol": "openai-completion",
                "api_key": marker + "x" * 8192,
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "api_key"]
    assert marker not in response.text
    assert "Request validation failed" in caplog.text
    assert marker not in caplog.text

def test_provider_api_unknown_key_field_does_not_expose_input(caplog):
    marker = "unknown-provider-key-must-not-leak"
    app = create_app(SchedulerConfig())
    app.dependency_overrides[get_llm_catalog] = FakeCatalog

    with caplog.at_level(logging.WARNING, logger="api.main"):
        response = TestClient(app).post(
            "/api/llm/providers",
            json={
                "name": "x",
                "protocol": "openai-completion",
                "api_key": "valid-key",
                "apiKey": marker,
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "apiKey"]
    assert marker not in response.text
    assert "Request validation failed" in caplog.text
    assert marker not in caplog.text

def test_provider_update_requires_new_key_when_authority_changes():
    from api.llm.routes import _validate_provider_update
    current = provider(base_url="https://old.example/v1")
    with pytest.raises(HTTPException) as exc:
        _validate_provider_update(current, ProviderUpdate(base_url="https://new.example/v1"))
    assert exc.value.status_code == 422
    assert exc.value.detail[0]["loc"] == ["body", "api_key"]
    _validate_provider_update(current, ProviderUpdate(base_url="https://old.example/v2"))

def test_provider_update_requires_new_key_when_format_changes():
    from api.llm.routes import _validate_provider_update

    current = provider(protocol=ProviderProtocol.OPENAI_COMPLETION)
    with pytest.raises(HTTPException) as exc:
        _validate_provider_update(current, ProviderUpdate(protocol="claude"))
    assert exc.value.status_code == 422
    assert exc.value.detail[0]["loc"] == ["body", "api_key"]

    _validate_provider_update(
        current,
        ProviderUpdate(protocol="claude", api_key="new-secret"),
    )

class FakeCatalog:
    def __init__(self):
        self.item = provider(); self.kwargs = None
        self.models = [LlmModel(id=2, provider_id=1, remote_model_id="gpt", litellm_model="openai/gpt",
            display_name="GPT", enabled=True, remote_available=True, last_discovered_at=None,
            created_at=datetime(2025, 1, 1), updated_at=datetime(2025, 1, 1))]
    async def list_providers(self): return [self.item]
    async def require_provider(self, provider_id): return self.item
    async def create_provider(self, **kwargs): self.kwargs = kwargs; return self.item
    async def update_provider(self, provider_id, **kwargs):
        self.kwargs = kwargs
        for key, value in kwargs.items(): setattr(self.item, key, value)
        return self.item
    async def delete_provider(self, provider_id): return None
    async def list_models(self, provider_id, usable_only=False): return self.models
    async def set_model_enabled(self, model_id, enabled): self.models[0].enabled = enabled; return self.models[0]


@pytest.mark.asyncio
async def test_create_without_encryption_key_returns_fixed_503(monkeypatch):
    class CreatingCatalog:
        async def create_provider(self, **values):
            protocol = ProviderProtocol(values["protocol"])
            return LlmProvider(
                **values,
                litellm_prefix=protocol.litellm_prefix,
            )

    monkeypatch.delenv(ENV_NAME, raising=False)
    clear_credential_cipher_cache()

    with pytest.raises(HTTPException) as error:
        await create_provider(
            ProviderCreate(
                name="missing-key",
                protocol="openai-completion",
                api_key="must-never-appear",
            ),
            CreatingCatalog(),
        )

    assert error.value.status_code == 503
    assert error.value.detail == "LLM credentials are unavailable"
    assert "must-never-appear" not in str(error.value)


@pytest.mark.asyncio
async def test_unreadable_provider_credential_returns_fixed_503():
    catalog = FakeCatalog()
    catalog.item._api_key = f"{ENCRYPTED_PREFIX}corrupt"

    with pytest.raises(HTTPException) as error:
        await get_provider(1, catalog)

    assert error.value.status_code == 503
    assert error.value.detail == "LLM credentials are unavailable"

@pytest.mark.asyncio
async def test_crud_routes_keep_blank_api_key_and_never_return_secret():
    catalog = FakeCatalog()
    created = await create_provider(ProviderCreate(name="OpenAI", protocol="openai-completion", api_key="secret"), catalog)
    assert "secret" not in created.model_dump_json()
    await update_provider(1, ProviderUpdate(name="Renamed", api_key=""), catalog)
    assert catalog.kwargs == {"name": "Renamed"}
    await update_provider(1, ProviderUpdate(api_key="   "), catalog)
    assert catalog.kwargs == {}
    assert len(await list_providers(catalog)) == 1
    assert (await get_provider(1, catalog)).litellm_prefix == "openai"
    assert (await enable_provider(1, catalog)).enabled is True
    assert catalog.kwargs == {"enabled": True}
    assert (await disable_provider(1, catalog)).enabled is False
    assert catalog.kwargs == {"enabled": False}

@pytest.mark.asyncio
async def test_model_filter_toggle_sync_and_error_mapping():
    catalog = FakeCatalog()
    assert (await list_models(1, "usable", catalog))[0].remote_model_id == "gpt"
    assert (await disable_model(2, catalog)).enabled is False
    assert (await enable_model(2, catalog)).enabled is True
    class Discovery:
        async def sync(self, provider_id): return SyncCounts(2, 3, 4)
    result = await sync_models(1, Discovery())
    assert (result.created, result.updated, result.unavailable, result.status) == (2, 3, 4, "success")
    assert isinstance(result.synced_at, datetime)
    class Failed:
        async def sync(self, provider_id): raise ModelDiscoveryError("Bearer secret")
    with pytest.raises(HTTPException) as exc:
        await sync_models(1, Failed())
    assert exc.value.status_code == 502
    assert "secret" not in str(exc.value.detail)
    class Disabled:
        async def sync(self, provider_id): raise ProviderDisabledError("arbitrary text")
    with pytest.raises(HTTPException) as exc:
        await sync_models(1, Disabled())
    assert exc.value.status_code == 409
    assert exc.value.detail == "Provider is disabled"

    class CredentialFailure:
        async def sync(self, provider_id):
            raise CredentialDecryptionError("sensitive internal detail")

    with pytest.raises(HTTPException) as exc:
        await sync_models(1, CredentialFailure())
    assert (exc.value.status_code, exc.value.detail) == (
        503,
        "LLM credentials are unavailable",
    )

@pytest.mark.asyncio
async def test_catalog_errors_map_to_http_statuses():
    class Missing(FakeCatalog):
        async def update_provider(self, provider_id, **kwargs): raise CatalogNotFoundError()
    with pytest.raises(HTTPException) as exc:
        await update_provider(9, ProviderUpdate(name="x"), Missing())
    assert exc.value.status_code == 404
    class Duplicate(FakeCatalog):
        async def create_provider(self, **kwargs): raise CatalogConflictError("duplicate secret")
    with pytest.raises(HTTPException) as exc:
        await create_provider(ProviderCreate(name="x", protocol="openai-completion", api_key="secret"), Duplicate())
    assert exc.value.status_code == 409

@pytest.mark.asyncio
async def test_all_catalog_route_stages_map_database_failure_to_503():
    from storage.exceptions import SQLOperationError
    class Failed(FakeCatalog):
        async def list_providers(self): raise SQLOperationError("secret")
        async def require_provider(self, provider_id): raise SQLOperationError("secret")
        async def list_models(self, provider_id, usable_only=False): raise SQLOperationError("secret")
        async def set_model_enabled(self, model_id, enabled): raise SQLOperationError("secret")
    for call in (
        lambda: list_providers(Failed()),
        lambda: get_provider(1, Failed()),
        lambda: list_models(1, "all", Failed()),
        lambda: disable_model(2, Failed()),
    ):
        with pytest.raises(HTTPException) as exc:
            await call()
        assert (exc.value.status_code, exc.value.detail) == (503, "LLM catalog is unavailable")

    class Discovery:
        async def sync(self, provider_id): raise SQLOperationError("secret")
    with pytest.raises(HTTPException) as exc:
        await sync_models(1, Discovery())
    assert (exc.value.status_code, exc.value.detail) == (503, "LLM catalog is unavailable")
    assert "secret" not in str(exc.value.detail)
    class Unavailable(FakeCatalog):
        async def create_provider(self, **kwargs):
            from storage.exceptions import SQLOperationError
            raise SQLOperationError("database secret")
    with pytest.raises(HTTPException) as exc:
        await create_provider(ProviderCreate(name="x", protocol="openai-completion", api_key="secret"), Unavailable())
    assert exc.value.status_code == 503
    assert exc.value.detail == "LLM catalog is unavailable"
    class DeleteMissing(FakeCatalog):
        async def delete_provider(self, provider_id): raise CatalogNotFoundError()
    with pytest.raises(HTTPException) as exc:
        await delete_provider(9, DeleteMissing())
    assert exc.value.status_code == 404
    class Referenced(FakeCatalog):
        async def delete_provider(self, provider_id): raise CatalogConflictError()
    with pytest.raises(HTTPException) as exc:
        await delete_provider(1, Referenced())
    assert exc.value.status_code == 409

def test_router_exposes_explicit_management_paths():
    actual = {(method, route.path) for route in router.routes for method in route.methods}
    expected = {
        ("GET", "/api/llm/providers"), ("POST", "/api/llm/providers"),
        ("GET", "/api/llm/providers/{provider_id}"),
        ("PATCH", "/api/llm/providers/{provider_id}"),
        ("DELETE", "/api/llm/providers/{provider_id}"),
        ("POST", "/api/llm/providers/{provider_id}/enable"),
        ("POST", "/api/llm/providers/{provider_id}/disable"),
        ("POST", "/api/llm/providers/{provider_id}/sync-models"),
        ("GET", "/api/llm/providers/{provider_id}/models"),
        ("POST", "/api/llm/providers/models/{model_id}/enable"),
        ("POST", "/api/llm/providers/models/{model_id}/disable"),
    }
    assert expected <= actual

def test_task_write_schema_does_not_accept_analysis_config():
    starlette.routing.Router.__init__ = _compatible_router_init
    try:
        from api.crawler.schemas import TaskCreate
    finally:
        starlette.routing.Router.__init__ = _router_init
    with pytest.raises(ValidationError, match="config"):
        TaskCreate(ba_id=1, config={"analysis": {"llm_model_id": 3}})

@pytest.mark.asyncio
async def test_settings_llm_update_is_inside_reference_guard():
    starlette.routing.Router.__init__ = _compatible_router_init
    try:
        from api.settings.routes import put_llm
    finally:
        starlette.routing.Router.__init__ = _router_init
    from runtime_config.models import LlmSettings, LlmSettingsUpdate
    events = []
    class Store:
        async def update_llm(self, value):
            events.append("write")
            return LlmSettings(default_analysis_model_id=value.default_analysis_model_id)
    class Catalog:
        @asynccontextmanager
        async def reference_guard(self, model_ids):
            events.append(("enter", model_ids)); yield; events.append("exit")
    await put_llm(LlmSettingsUpdate(default_analysis_model_id=3), Store(), Catalog())
    assert events == [("enter", [3]), "write", "exit"]
