import sys
from types import SimpleNamespace

import pytest

from llm.errors import LLMError
from llm.transcription import LiteLlmTranscriber, TranscriptionTarget


def install_litellm(monkeypatch, atranscription):
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(atranscription=atranscription),
    )


@pytest.mark.asyncio
async def test_transcribe_passes_target_and_returns_text(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    captured = {}

    async def atranscription(**kwargs):
        captured.update(kwargs)
        assert not kwargs["file"].closed
        return SimpleNamespace(text="spoken words")

    install_litellm(monkeypatch, atranscription)
    target = TranscriptionTarget(
        model="openai/whisper-1",
        api_key="secret-key",
        base_url="https://llm.example/v1",
    )

    text = await LiteLlmTranscriber().transcribe(audio_path, target)

    assert text == "spoken words"
    assert captured["model"] == "openai/whisper-1"
    assert captured["api_key"] == "secret-key"
    assert captured["api_base"] == "https://llm.example/v1"
    assert captured["file"].closed


@pytest.mark.asyncio
async def test_transcribe_rejects_missing_text(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    async def atranscription(**kwargs):
        return SimpleNamespace(text=None)

    install_litellm(monkeypatch, atranscription)

    with pytest.raises(LLMError, match="音频转写失败"):
        await LiteLlmTranscriber().transcribe(
            audio_path,
            TranscriptionTarget("model", "key", "https://example.test"),
        )


@pytest.mark.asyncio
async def test_transcribe_redacts_provider_and_io_errors(
    tmp_path, monkeypatch
):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    secret = "super-secret"
    base_url = "https://private.example/v1"

    async def atranscription(**kwargs):
        raise RuntimeError(f"request {base_url} key={secret} body=sensitive")

    install_litellm(monkeypatch, atranscription)

    with pytest.raises(LLMError) as caught:
        await LiteLlmTranscriber().transcribe(
            audio_path, TranscriptionTarget("model", secret, base_url)
        )

    assert str(caught.value) == "音频转写失败"
    assert secret not in str(caught.value)
    assert base_url not in str(caught.value)
    assert isinstance(caught.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_transcribe_closes_file_after_failure(tmp_path, monkeypatch):
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    captured = {}

    async def atranscription(**kwargs):
        captured["file"] = kwargs["file"]
        raise OSError("offline")

    install_litellm(monkeypatch, atranscription)

    with pytest.raises(LLMError):
        await LiteLlmTranscriber().transcribe(
            audio_path, TranscriptionTarget("model", "key", None)
        )

    assert captured["file"].closed
