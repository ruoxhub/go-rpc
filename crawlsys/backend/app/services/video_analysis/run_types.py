"""Immutable, secret-free contracts for queued video-analysis runs."""

from __future__ import annotations

import hashlib
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_RUN_MAX_ATTEMPTS = 3
DEFAULT_ANALYSIS_REQUEST_PATH = "chat"


class PromptSnapshotError(ValueError):
    """A prompt cannot be persisted as a safe run snapshot."""

    def __init__(self, code: str = "PROMPT_INVALID") -> None:
        self.code = code
        super().__init__(code)


def normalize_prompt(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise PromptSnapshotError()
    return f"{normalized}\n"


def hash_prompt(text: str) -> str:
    return hashlib.sha256(normalize_prompt(text).encode("utf-8")).hexdigest()


class _FrozenSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptBundle(_FrozenSnapshot):
    rule_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    version: int = Field(gt=0)
    observation_prompt: str
    evaluation_prompt: str
    observation_prompt_hash: str
    evaluation_prompt_hash: str

    @classmethod
    def create(
        cls,
        *,
        rule_id: int,
        version_id: int,
        version: int,
        observation_prompt: str,
        evaluation_prompt: str,
    ) -> "PromptBundle":
        observation = normalize_prompt(observation_prompt)
        evaluation = normalize_prompt(evaluation_prompt)
        return cls(
            rule_id=rule_id,
            version_id=version_id,
            version=version,
            observation_prompt=observation,
            evaluation_prompt=evaluation,
            observation_prompt_hash=hash_prompt(observation),
            evaluation_prompt_hash=hash_prompt(evaluation),
        )


class ModelIdentitySnapshot(_FrozenSnapshot):
    model_id: int = Field(gt=0)
    provider_id: int = Field(gt=0)
    display_name: str = Field(min_length=1)
    protocol: str = Field(min_length=1)
    remote_model_id: str = Field(min_length=1)
    endpoint_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_endpoint(
        cls,
        *,
        model_id: int,
        provider_id: int,
        display_name: str,
        protocol: str,
        remote_model_id: str,
        endpoint: str,
    ) -> "ModelIdentitySnapshot":
        try:
            parsed = urlsplit(endpoint)
            port = parsed.port
        except ValueError as error:
            raise ValueError("endpoint must be a valid HTTP(S) URL") from error
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if scheme not in {"http", "https"} or not host:
            raise ValueError("endpoint must be a valid HTTP(S) URL")
        if ":" in host:
            host = f"[{host}]"
        authority = f"{host}:{port}" if port is not None else host
        path = parsed.path or "/"
        identity = f"{protocol.strip().lower()}|{scheme}://{authority}{path}"
        return cls(
            model_id=model_id,
            provider_id=provider_id,
            display_name=display_name,
            protocol=protocol,
            remote_model_id=remote_model_id,
            endpoint_fingerprint=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        )


class VideoSettingsSnapshot(_FrozenSnapshot):
    is_base64: bool
    frame_sampling_strategy: Literal["interval", "count", "timestamps", "scene_guided"]
    max_frames: int = Field(ge=2)
    frame_interval_seconds: float = Field(ge=0)
    frame_timestamps: tuple[float, ...] = ()


_SECRET_FIELDS = {"api_key", "password", "secret", "token"}


def _find_secret_field(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SECRET_FIELDS or any(
                normalized.endswith(f"_{secret}") for secret in _SECRET_FIELDS
            ):
                return str(key)
            if found := _find_secret_field(nested):
                return found
    elif isinstance(value, (list, tuple)):
        for nested in value:
            if found := _find_secret_field(nested):
                return found
    return None


class ExecutionConfigSnapshot(_FrozenSnapshot):
    analysis_model: ModelIdentitySnapshot
    transcription_model: ModelIdentitySnapshot | None
    temperature: float = Field(ge=0)
    max_tokens: int = Field(gt=0)
    enable_thinking: bool
    video: VideoSettingsSnapshot
    request_path: Literal["chat", "responses"]
    review_route: Literal["R", "G"] | None

    @model_validator(mode="before")
    @classmethod
    def reject_secret_fields(cls, value: Any) -> Any:
        if field := _find_secret_field(value):
            raise ValueError(f"secret-bearing field is not allowed: {field}")
        return value
