from sqlalchemy import CheckConstraint, UniqueConstraint

from common.errors import redact_secrets
from models import LlmModel, LlmProvider, ProviderProtocol
from security.credentials import (
    ENCRYPTED_PREFIX,
    ENV_NAME,
    clear_credential_cipher_cache,
)


def test_provider_and_model_defaults() -> None:
    provider = LlmProvider(
        name="anthropic",
        litellm_prefix="anthropic",
        protocol=ProviderProtocol.CLAUDE,
        api_key="test-key",
    )
    model = LlmModel(
        provider_id=1,
        remote_model_id="claude-sonnet-4-20250514",
        litellm_model="anthropic/claude-sonnet-4-20250514",
        display_name="Claude Sonnet 4",
    )

    assert provider.enabled is True
    assert model.enabled is True
    assert model.remote_available is True


def test_provider_protocols_have_fixed_litellm_prefixes() -> None:
    assert {
        protocol.value: protocol.litellm_prefix for protocol in ProviderProtocol
    } == {
        "openai-completion": "openai",
        "claude": "anthropic",
        "gemini": "gemini",
        "deepseek": "deepseek",
        "openai-responses": "responses/openai",
    }


def test_provider_api_key_is_encrypted_at_rest() -> None:
    provider = LlmProvider(
        name="encrypted",
        litellm_prefix="openai",
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        api_key="must-not-be-stored-plainly",
    )

    assert provider._api_key.startswith(ENCRYPTED_PREFIX)
    assert "must-not-be-stored-plainly" not in provider._api_key
    assert provider.api_key == "must-not-be-stored-plainly"


def test_provider_reads_legacy_plaintext_without_rewriting_it() -> None:
    provider = LlmProvider(
        name="legacy",
        litellm_prefix="openai",
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        api_key="temporary-key",
    )
    provider._api_key = "legacy-plain-key"

    assert provider.api_key == "legacy-plain-key"
    assert provider._api_key == "legacy-plain-key"
    assert redact_secrets("rejected legacy-plain-key") == "rejected ***"


def test_provider_allows_empty_key_without_encryption_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv(ENV_NAME, raising=False)
    clear_credential_cipher_cache()

    provider = LlmProvider(
        name="empty",
        litellm_prefix="openai",
        protocol=ProviderProtocol.OPENAI_COMPLETION,
        api_key="",
    )

    assert provider._api_key == ""
    assert provider.api_key == ""


def test_provider_table_constraints_and_indexes() -> None:
    table = LlmProvider.__table__

    assert table.schema == "public"
    assert table.name == "t_llm_provider"
    assert table.c.name.unique is True
    assert table.c.protocol.type.length == 32
    assert any(
        constraint.name == "provider_protocol_enum"
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )
    assert {index.name for index in table.indexes} == {"idx_llm_provider_enabled"}


def test_model_table_constraints_and_indexes() -> None:
    table = LlmModel.__table__
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    foreign_keys = {
        (foreign_key.target_fullname, foreign_key.constraint.name)
        for foreign_key in table.foreign_keys
    }

    assert table.schema == "public"
    assert table.name == "t_llm_model"
    assert ("provider_id", "remote_model_id") in unique_columns
    assert foreign_keys == {
        ("public.t_llm_provider.id", "fk_llm_model_provider")
    }
    assert {index.name for index in table.indexes} == {
        "idx_llm_model_enabled",
        "idx_llm_model_provider_id",
        "idx_llm_model_remote_available",
    }
