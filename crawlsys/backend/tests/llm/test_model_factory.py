"""LiteLLM model factory tests."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import requests
import tiktoken
from unittest.mock import patch

with patch("tiktoken.get_encoding", return_value=object()):
    from langchain_litellm import ChatLiteLLM
    from llm.model_factory import LitellmModelFactory, ModelUnavailableError
from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch):
    def reject_network(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("model factory tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject_network)
    monkeypatch.setattr(requests.Session, "send", reject_network)
    monkeypatch.setattr(tiktoken, "get_encoding", lambda _name: object())


class FakeCatalog:
    def __init__(self, result):
        self.result = result
        self.requested_ids: list[int] = []

    async def get_model(self, model_id: int):
        self.requested_ids.append(model_id)
        return self.result

    async def get_models(self, model_ids: list[int]):
        self.requested_ids.extend(model_ids)
        if isinstance(self.result, dict):
            return self.result
        return {model_id: self.result for model_id in model_ids if self.result}


def make_catalog_result(
    *,
    protocol: ProviderProtocol,
    litellm_model: str,
    base_url: str | None = None,
    provider_enabled: bool = True,
    model_enabled: bool = True,
    remote_available: bool = True,
):
    provider = LlmProvider(
        id=4,
        name="Provider",
        litellm_prefix="unused-prefix",
        protocol=protocol,
        base_url=base_url,
        api_key="super-secret-key",
        enabled=provider_enabled,
    )
    model = LlmModel(
        id=9,
        provider_id=provider.id,
        remote_model_id="remote-name",
        litellm_model=litellm_model,
        display_name="Model",
        enabled=model_enabled,
        remote_available=remote_available,
    )
    return model, provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protocol", "litellm_name", "base_url"),
    [
        (ProviderProtocol.OPENAI_COMPLETION, "openai/gpt-5", "https://openai.example/v1"),
        (ProviderProtocol.OPENAI_RESPONSES, "responses/openai/gpt-5", "https://openai.example/v1"),
        (ProviderProtocol.CLAUDE, "anthropic/claude-sonnet-4", "https://anthropic.example"),
        (ProviderProtocol.GEMINI, "gemini/gemini-2.5-pro", None),
        (ProviderProtocol.DEEPSEEK, "deepseek/deepseek-chat", "https://api.deepseek.com"),
    ],
)
async def test_create_uses_persisted_litellm_name_and_provider_credentials(
    protocol: ProviderProtocol,
    litellm_name: str,
    base_url: str | None,
    monkeypatch: pytest.MonkeyPatch,
):
    catalog = FakeCatalog(
        make_catalog_result(
            protocol=protocol, litellm_model=litellm_name, base_url=base_url
        )
    )

    monkeypatch.setattr(tiktoken, "get_encoding", lambda _name: object())
    result = await LitellmModelFactory(catalog).create(
        9, temperature=0.25, max_tokens=4096
    )

    assert isinstance(result, ChatLiteLLM)
    assert result.model == litellm_name
    assert result.api_base == base_url
    assert result.api_key == "super-secret-key"
    assert result.temperature == 0.25
    assert result.max_tokens == 4096
    assert catalog.requested_ids == [9]


@pytest.mark.asyncio
async def test_resolve_batch_loads_analysis_and_transcription_together():
    analysis = make_catalog_result(
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        litellm_model="openai/analysis",
    )
    transcription = make_catalog_result(
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        litellm_model="openai/transcription",
    )
    analysis[0].id = 7
    transcription[0].id = 8
    catalog = FakeCatalog({7: analysis, 8: transcription})

    result = await LitellmModelFactory(catalog).resolve_batch(
        7, 8, temperature=0.1, max_tokens=2048
    )

    assert result.analysis.name == "openai/analysis"
    assert isinstance(result.analysis.model, ChatLiteLLM)
    assert result.analysis.model.temperature == 0.1
    assert result.analysis.model.max_tokens == 2048
    assert result.transcription is not None
    assert result.transcription.name == "openai/transcription"
    assert result.transcription.api_key == "super-secret-key"
    assert catalog.requested_ids == [7, 8]


@pytest.mark.asyncio
@pytest.mark.parametrize("enable_thinking", [True, False, None])
async def test_create_only_sends_thinking_extra_body_when_enabled(enable_thinking):
    catalog = FakeCatalog(
        make_catalog_result(
            protocol=ProviderProtocol.OPENAI_COMPLETION,
            litellm_model="openai/analysis",
        )
    )

    model = await LitellmModelFactory(catalog).create(
        9, enable_thinking=enable_thinking
    )

    if enable_thinking is True:
        assert model._default_params["extra_body"] == {"enable_thinking": True}
    else:
        assert "extra_body" not in model._default_params


@pytest.mark.parametrize("module_name", ["llm", "llm.model_factory"])
def test_llm_import_does_not_load_litellm_or_tiktoken_encoding(
    tmp_path: Path,
    module_name: str,
):
    sitecustomize = tmp_path / "sitecustomize.py"
    sitecustomize.write_text(
        "import tiktoken\n"
        "def reject_encoding(*args, **kwargs):\n"
        "    raise AssertionError('tiktoken encoding must not load during import')\n"
        "tiktoken.get_encoding = reject_encoding\n",
        encoding="utf-8",
    )
    app_path = Path(__file__).resolve().parents[2] / "app"
    script = (
        f"import {module_name}\n"
        "import sys\n"
        "assert 'litellm' not in sys.modules\n"
        "assert 'langchain_litellm' not in sys.modules\n"
    )
    env = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(name, None)
    env.update(
        PYTHONPATH=f"{tmp_path}{os.pathsep}{app_path}",
        PYTHONNOUSERSITE="1",
    )

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "catalog_result",
    [
        None,
        make_catalog_result(
            protocol=ProviderProtocol.OPENAI_COMPLETION,
            litellm_model="openai/gpt-5",
            provider_enabled=False,
        ),
        make_catalog_result(
            protocol=ProviderProtocol.GEMINI,
            litellm_model="gemini/gemini-2.5-pro",
            model_enabled=False,
        ),
        make_catalog_result(
            protocol=ProviderProtocol.CLAUDE,
            litellm_model="anthropic/claude-sonnet-4",
            remote_available=False,
        ),
    ],
    ids=["missing", "provider-disabled", "model-disabled", "remote-unavailable"],
)
async def test_create_rejects_unusable_models_with_fixed_sanitized_error(catalog_result):
    catalog = FakeCatalog(catalog_result)

    with pytest.raises(ModelUnavailableError) as exc_info:
        await LitellmModelFactory(catalog).create(9)

    assert str(exc_info.value) == "Requested LLM model is unavailable"
    assert "super-secret-key" not in str(exc_info.value)
    assert "example" not in str(exc_info.value)
