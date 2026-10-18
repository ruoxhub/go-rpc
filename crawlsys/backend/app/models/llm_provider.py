"""LLM 提供商与模型持久化模型。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, synonym

from common.errors import register_secret
from security.credentials import ENCRYPTED_PREFIX, get_credential_cipher

from .base import Base


class ProviderProtocol(str, Enum):
    """提供商请求格式。"""

    OPENAI_COMPLETION = "openai-completion"
    CLAUDE = "claude"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OPENAI_RESPONSES = "openai-responses"

    @property
    def litellm_prefix(self) -> str:
        return {
            "openai-completion": "openai",
            "claude": "anthropic",
            "gemini": "gemini",
            "deepseek": "deepseek",
            "openai-responses": "responses/openai",
        }[self.value]


class LlmProvider(Base):
    """LLM 提供商配置。"""

    __tablename__ = "t_llm_provider"
    __table_args__ = (
        Index("idx_llm_provider_enabled", "enabled"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    litellm_prefix: Mapped[str] = mapped_column(String(100), nullable=False)
    protocol: Mapped[ProviderProtocol] = mapped_column(
        SqlEnum(
            ProviderProtocol,
            name="provider_protocol_enum",
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
            create_constraint=True,
            length=32,
        ),
        nullable=False,
    )
    base_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    _api_key: Mapped[str] = mapped_column("api_key", Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("enabled", True)
        super().__init__(**kwargs)

    def _get_api_key(self) -> str:
        if not self._api_key:
            return self._api_key
        if not self._api_key.startswith(ENCRYPTED_PREFIX):
            register_secret(self._api_key)
            return self._api_key
        return get_credential_cipher().decrypt(self._api_key)

    def _set_api_key(self, value: str) -> None:
        if not value:
            self._api_key = value
            return
        self._api_key = get_credential_cipher().encrypt(value)

    api_key = synonym(
        "_api_key",
        descriptor=property(_get_api_key, _set_api_key),
    )


class LlmModel(Base):
    """提供商可用的远端 LLM 模型。"""

    __tablename__ = "t_llm_model"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "remote_model_id",
            name="uq_llm_model_provider_remote_model",
        ),
        Index("idx_llm_model_provider_id", "provider_id"),
        Index("idx_llm_model_enabled", "enabled"),
        Index("idx_llm_model_remote_available", "remote_available"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "public.t_llm_provider.id",
            name="fk_llm_model_provider",
        ),
        nullable=False,
    )
    remote_model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    litellm_model: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    remote_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    last_discovered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("enabled", True)
        kwargs.setdefault("remote_available", True)
        super().__init__(**kwargs)
