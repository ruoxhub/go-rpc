"""Create LangChain LiteLLM chat models from the persisted catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict

from models.llm_provider import LlmModel, LlmProvider

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_litellm import ChatLiteLLM


class ModelUnavailableError(LookupError):
    """The requested model cannot safely be used by the runtime."""


class ThinkingExtraBody(TypedDict):
    enable_thinking: Literal[True]


class ThinkingModelKwargs(TypedDict, total=False):
    extra_body: ThinkingExtraBody


def _thinking_model_kwargs(enable_thinking: bool | None) -> ThinkingModelKwargs:
    if enable_thinking is True:
        return {"extra_body": {"enable_thinking": True}}
    return {}


def _create_chat_model(
    *,
    model: str,
    api_key: str,
    api_base: str | None,
    temperature: float | None,
    max_tokens: int | None,
    enable_thinking: bool | None,
) -> "ChatLiteLLM":
    from langchain_litellm import ChatLiteLLM

    return ChatLiteLLM(
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs=_thinking_model_kwargs(enable_thinking),
    )


def validate_catalog_entry(
    catalog_entry: tuple[LlmModel, LlmProvider] | None,
) -> tuple[LlmModel, LlmProvider]:
    """Return a usable model/provider pair or raise one stable error."""
    if catalog_entry is None:
        raise ModelUnavailableError("Requested LLM model is unavailable")
    model, provider = catalog_entry
    if not provider.enabled or not model.enabled or not model.remote_available:
        raise ModelUnavailableError("Requested LLM model is unavailable")
    return model, provider


class ModelCatalog(Protocol):
    async def get_model(
        self, model_id: int
    ) -> tuple[LlmModel, LlmProvider] | None: ...

    async def get_models(
        self, model_ids: list[int]
    ) -> dict[int, tuple[LlmModel, LlmProvider]]: ...


@dataclass(frozen=True)
class ModelResolution:
    model: "BaseChatModel"
    name: str
    model_id: int


@dataclass(frozen=True)
class TranscriptionResolution:
    name: str
    api_key: str
    base_url: str | None


@dataclass(frozen=True)
class BatchModelResolution:
    analysis: ModelResolution
    transcription: TranscriptionResolution | None


class LitellmModelFactory:
    """Build chat models exclusively from trusted catalog records."""

    def __init__(self, catalog: ModelCatalog) -> None:
        self._catalog = catalog

    async def create(
        self,
        model_id: int,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
    ) -> "BaseChatModel":
        return (
            await self.resolve(
                model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            )
        ).model

    async def resolve(
        self,
        model_id: int,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
    ) -> ModelResolution:
        model, provider = await self._require_entry(model_id)

        return ModelResolution(
            model=_create_chat_model(
                model=model.litellm_model,
                api_base=provider.base_url,
                api_key=provider.api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            ),
            name=model.litellm_model,
            model_id=model_id,
        )

    async def resolve_transcription(self, model_id: int) -> TranscriptionResolution:
        model, provider = await self._require_entry(model_id)
        return TranscriptionResolution(model.litellm_model, provider.api_key, provider.base_url)

    async def resolve_batch(
        self,
        analysis_model_id: int,
        transcription_model_id: int | None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_thinking: bool | None = None,
    ) -> BatchModelResolution:
        ids = [analysis_model_id]
        if transcription_model_id is not None:
            ids.append(transcription_model_id)
        entries = await self._catalog.get_models(ids)
        analysis_model, analysis_provider = validate_catalog_entry(
            entries.get(analysis_model_id)
        )
        transcription_entry = None
        if transcription_model_id is not None:
            transcription_entry = validate_catalog_entry(
                entries.get(transcription_model_id)
            )
        analysis = ModelResolution(
            model=_create_chat_model(
                model=analysis_model.litellm_model,
                api_base=analysis_provider.base_url,
                api_key=analysis_provider.api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=enable_thinking,
            ),
            name=analysis_model.litellm_model,
            model_id=analysis_model_id,
        )
        transcription = None
        if transcription_entry is not None:
            transcription_model, transcription_provider = transcription_entry
            transcription = TranscriptionResolution(
                transcription_model.litellm_model,
                transcription_provider.api_key,
                transcription_provider.base_url,
            )
        return BatchModelResolution(analysis, transcription)

    async def _require_entry(self, model_id: int) -> tuple[LlmModel, LlmProvider]:
        return validate_catalog_entry(await self._catalog.get_model(model_id))
