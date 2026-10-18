from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from llm.catalog import CatalogConflictError, CatalogNotFoundError, LlmCatalog
from llm.discovery import ModelDiscoveryError, ModelDiscoveryService, ProviderDisabledError
from api.deps import get_llm_catalog, get_model_discovery
from security.credentials import (
    CredentialConfigurationError,
    CredentialDecryptionError,
)
from storage.exceptions import SQLOperationError
from .schemas import ModelRead, ProviderCreate, ProviderRead, ProviderUpdate, SyncResponse

router = APIRouter(prefix="/api/llm/providers", tags=["llm-providers"])
CREDENTIAL_ERRORS = (CredentialConfigurationError, CredentialDecryptionError)

def _raise_credential_unavailable() -> None:
    raise HTTPException(503, "LLM credentials are unavailable") from None


def _provider(value):
    try:
        return ProviderRead.from_orm_model(value)
    except CREDENTIAL_ERRORS:
        _raise_credential_unavailable()

def _validate_provider_update(current, value: ProviderUpdate) -> None:
    authority_changed = False
    if "base_url" in value.model_fields_set:
        old = urlsplit(current.base_url or "")
        new = urlsplit(str(value.base_url))
        authority_changed = (
            old.scheme, old.hostname, old.port
        ) != (new.scheme, new.hostname, new.port)
    protocol_changed = (
        "protocol" in value.model_fields_set
        and value.protocol != current.protocol
    )
    if (authority_changed or protocol_changed) and not (
        value.api_key and value.api_key.strip()
    ):
        raise HTTPException(
            422,
            [{
                "loc": ["body", "api_key"],
                "msg": "A new API key is required when provider target changes",
                "type": "value_error",
            }],
        )

def _raise_catalog(error):
    if isinstance(error, CatalogNotFoundError): raise HTTPException(404, "LLM resource not found") from None
    if isinstance(error, CatalogConflictError): raise HTTPException(409, "LLM resource conflict") from None
    if isinstance(error, SQLOperationError): raise HTTPException(503, "LLM catalog is unavailable") from None
    raise error

async def _catalog_call(awaitable):
    try:
        return await awaitable
    except (CatalogNotFoundError, CatalogConflictError, SQLOperationError) as error:
        _raise_catalog(error)
    except CREDENTIAL_ERRORS:
        _raise_credential_unavailable()

@router.get("", response_model=list[ProviderRead])
async def list_providers(catalog: LlmCatalog = Depends(get_llm_catalog)):
    return [_provider(item) for item in await _catalog_call(catalog.list_providers())]

@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(provider_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)):
    return _provider(await _catalog_call(catalog.require_provider(provider_id)))

@router.post("", response_model=ProviderRead, status_code=201)
async def create_provider(value: ProviderCreate, catalog: LlmCatalog = Depends(get_llm_catalog)):
    values = value.model_dump()
    if values["base_url"] is not None: values["base_url"] = str(values["base_url"])
    return _provider(await _catalog_call(catalog.create_provider(**values)))

@router.patch("/{provider_id}", response_model=ProviderRead)
async def update_provider(provider_id: int, value: ProviderUpdate, catalog: LlmCatalog = Depends(get_llm_catalog)):
    current = await _catalog_call(catalog.require_provider(provider_id))
    _validate_provider_update(current, value)
    values = value.model_dump(exclude_unset=True)
    if "api_key" in values and not values["api_key"].strip(): values.pop("api_key")
    if "base_url" in values: values["base_url"] = str(values["base_url"])
    return _provider(await _catalog_call(catalog.update_provider(provider_id, **values)))

@router.post("/{provider_id}/enable", response_model=ProviderRead)
async def enable_provider(provider_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)):
    return _provider(await _catalog_call(catalog.update_provider(provider_id, enabled=True)))

@router.post("/{provider_id}/disable", response_model=ProviderRead)
async def disable_provider(provider_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)):
    return _provider(await _catalog_call(catalog.update_provider(provider_id, enabled=False)))

@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)):
    await _catalog_call(catalog.delete_provider(provider_id))
    return Response(status_code=204)

@router.post("/{provider_id}/sync-models", response_model=SyncResponse)
async def sync_models(provider_id: int, discovery: ModelDiscoveryService = Depends(get_model_discovery)):
    try:
        counts = await discovery.sync(provider_id)
        return SyncResponse(**counts.__dict__, status="success", synced_at=datetime.now(UTC))
    except (CatalogNotFoundError, CatalogConflictError, SQLOperationError) as error:
        _raise_catalog(error)
    except ProviderDisabledError:
        raise HTTPException(409, "Provider is disabled") from None
    except ModelDiscoveryError:
        raise HTTPException(502, "LLM model synchronization failed") from None
    except CREDENTIAL_ERRORS:
        _raise_credential_unavailable()

@router.get("/{provider_id}/models", response_model=list[ModelRead])
async def list_models(provider_id: int, status: str | None = Query(None, pattern="^(usable|enabled|disabled|unavailable|all)$"), catalog: LlmCatalog = Depends(get_llm_catalog)):
    try:
        await _catalog_call(catalog.require_provider(provider_id)) if hasattr(catalog, "require_provider") else None
        models = await _catalog_call(catalog.list_models(provider_id, usable_only=status == "usable"))
        if status == "enabled": models = [item for item in models if item.enabled]
        elif status == "disabled": models = [item for item in models if not item.enabled]
        elif status == "unavailable": models = [item for item in models if not item.remote_available]
        return [ModelRead.model_validate(item) for item in models]
    except HTTPException:
        raise

@router.post("/models/{model_id}/enable", response_model=ModelRead)
async def enable_model(model_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)): return await set_model_enabled(model_id, True, catalog)

@router.post("/models/{model_id}/disable", response_model=ModelRead)
async def disable_model(model_id: int, catalog: LlmCatalog = Depends(get_llm_catalog)): return await set_model_enabled(model_id, False, catalog)

async def set_model_enabled(model_id: int, enabled: bool, catalog: LlmCatalog):
    return ModelRead.model_validate(
        await _catalog_call(catalog.set_model_enabled(model_id, enabled))
    )
