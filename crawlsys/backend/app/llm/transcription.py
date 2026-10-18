"""Asynchronous audio transcription through LiteLLM."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from llm.errors import LLMError


@dataclass(frozen=True)
class TranscriptionTarget:
    model: str
    api_key: str
    base_url: str | None


class LiteLlmTranscriber:
    async def transcribe(
        self, audio_path: Path, target: TranscriptionTarget
    ) -> str:
        try:
            import litellm

            with audio_path.open("rb") as audio_file:
                response = await litellm.atranscription(
                    model=target.model,
                    file=audio_file,
                    api_key=target.api_key,
                    api_base=target.base_url,
                )
            text = getattr(response, "text", None)
            if not isinstance(text, str):
                raise TypeError("transcription response text is not a string")
            return text
        except Exception as exc:
            raise LLMError("音频转写失败") from exc
