from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    protocol: ProviderProtocol
    base_url: AnyHttpUrl | None = None
    api_key: str = Field(min_length=1, max_length=8192)

    @field_validator("name", "api_key")
    @classmethod
    def reject_blank(cls, value: str):
        if not value.strip():
            raise ValueError("blank value is not allowed")
        return value

    @field_validator("base_url")
    @classmethod
    def reject_url_userinfo(cls, value: AnyHttpUrl | None):
        if value is not None and (value.username is not None or value.password is not None):
            raise ValueError("URL userinfo is not allowed")
        return value


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    protocol: ProviderProtocol | None = None
    base_url: AnyHttpUrl | None = None
    api_key: str | None = Field(default=None, max_length=8192)

    @field_validator("name", "protocol", "base_url")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("explicit null is not allowed")
        return value

    @field_validator("api_key")
    @classmethod
    def reject_null_api_key(cls, value):
        if value is None:
            raise ValueError("explicit null is not allowed")
        return value

    @field_validator("name")
    @classmethod
    def reject_blank_update(cls, value: str):
        if not value.strip():
            raise ValueError("blank value is not allowed")
        return value

    @field_validator("base_url")
    @classmethod
    def reject_update_url_userinfo(cls, value: AnyHttpUrl):
        if value.username is not None or value.password is not None:
            raise ValueError("URL userinfo is not allowed")
        return value


def _mask_secret(secret: str) -> str:
    if len(secret) <= 4:
        return "********"
    return f"********{secret[-4:]}"


class ProviderRead(BaseModel):
    id: int
    name: str
    litellm_prefix: str
    protocol: ProviderProtocol
    base_url: str | None
    enabled: bool
    api_key_configured: bool
    api_key_masked: str
    last_sync_status: str | None
    last_sync_at: datetime | None
    last_sync_error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_model(cls, value: LlmProvider):
        return cls(id=value.id, name=value.name, litellm_prefix=value.litellm_prefix,
                   protocol=value.protocol, base_url=value.base_url, enabled=value.enabled,
                   api_key_configured=bool(value.api_key), api_key_masked=_mask_secret(value.api_key),
                   last_sync_status=value.last_sync_status, last_sync_at=value.last_sync_at,
                   last_sync_error=value.last_sync_error, created_at=value.created_at,
                   updated_at=value.updated_at)


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider_id: int
    remote_model_id: str
    litellm_model: str
    display_name: str
    enabled: bool
    remote_available: bool
    last_discovered_at: datetime | None


class SyncResponse(BaseModel):
    created: int
    updated: int
    unavailable: int
    status: str
    synced_at: datetime
