from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import ParserConfigurationConfig
from llm.model_factory import ModelResolution
from parser.definition import ParserDefinition, ParserOutput
from parser.sanitizer import canonical_json_bytes
from services.parser_configuration.assistant import (
    AssistantActionParserService,
    ParserRuleAssistant,
    ParserSuggestion,
)
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionContext


DEFINITION = ParserDefinition.model_validate(
    {
        "schema_version": 1,
        "record_path": "/data",
        "output": {"mode": "json"},
        "fields": [{"target": "/id", "source": "/id"}],
    }
)

ALT_DEFINITION = ParserDefinition.model_validate(
    {
        "schema_version": 1,
        "record_path": "/items",
        "output": {"mode": "json"},
        "fields": [{"target": "/id", "source": "/id"}],
    }
)

EXPLICIT_NULL_DEFINITION = ParserDefinition.model_validate(
    {
        "schema_version": 1,
        "record_path": "/data",
        "output": {"mode": "json"},
        "fields": [{"target": "/id", "source": "/id", "default": None}],
    }
)

MODEL_DEFINITION = ParserDefinition.model_validate(
    {
        "schema_version": 1,
        "record_path": "/data",
        "output": {"mode": "model", "datatype": "content"},
        "fields": [{"target": "/content_id", "source": "/id"}],
    }
)


def _receipt_hash(definition: ParserDefinition) -> str:
    payload = definition.model_dump(mode="json", exclude_unset=True)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _create_receipt_payload(**overrides):
    payload = {
        "purpose": "create",
        "ba_id": 7,
        "source_sample_id": 3,
        "definition_sha256": _receipt_hash(DEFINITION),
        "model_id": 4,
        "model_name": "trusted-model",
        "prompt_version": "parser-definition-v1",
        "redacted_sample_sha256": "c" * 64,
        "duration_ms": 12,
        "attempts": 1,
        "preview_summary": {"valid_records": 1},
        "issued_at": 100,
        "expires_at": 300,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_assistant_marks_bounded_redacted_sample_untrusted_and_has_no_tools():
    runnable = MagicMock(ainvoke=AsyncMock(return_value=DEFINITION))
    model = MagicMock()
    model.with_structured_output.return_value = runnable
    factory = MagicMock(
        resolve=AsyncMock(return_value=ModelResolution(model, "trusted-model", 4))
    )
    assistant = ParserRuleAssistant(factory, max_bytes=4096, max_array_items=20)

    suggestion = await assistant.suggest(
        redacted_sample={"email": "<redacted:email>", "items": [{"id": "1"}]},
        output_contract=ParserOutput(mode="json"),
        model_id=4,
    )

    messages = runnable.ainvoke.await_args.args[0]
    serialized = str(messages)
    assert "untrusted data" in serialized.lower()
    assert "<redacted:email>" in serialized
    assert "alice@example.com" not in serialized
    assert assistant.tools == ()
    assert suggestion.definition == DEFINITION
    assert suggestion.model_id == 4
    assert suggestion.model_name == "trusted-model"
    factory.resolve.assert_awaited_once_with(
        4, temperature=0, enable_thinking=False
    )
    model.bind_tools.assert_not_called()


@pytest.mark.asyncio
async def test_assistant_injects_model_fields_for_model_mode():
    runnable = MagicMock(ainvoke=AsyncMock(return_value=MODEL_DEFINITION))
    model = MagicMock()
    model.with_structured_output.return_value = runnable
    factory = MagicMock(
        resolve=AsyncMock(return_value=ModelResolution(model, "trusted-model", 4))
    )
    assistant = ParserRuleAssistant(factory, max_bytes=4096, max_array_items=20)

    suggestion = await assistant.suggest(
        redacted_sample={"items": [{"id": "1", "title": "hello"}]},
        output_contract=ParserOutput(mode="model", datatype="content"),
        model_id=4,
    )

    messages = runnable.ainvoke.await_args.args[0]
    system_msg = messages[0].content
    human_msg = messages[1].content
    assert "target data model is 'content'" in system_msg
    assert "target_model_fields" in system_msg
    assert '"target_data_model":"content"' in human_msg
    assert '"target":"/content_id"' in human_msg
    assert '"target":"/title"' in human_msg
    assert suggestion.definition == MODEL_DEFINITION

@pytest.fixture
def assistant_service_parts():
    raw = b'{"data":[{"id":"1"}]}'
    sample = SimpleNamespace(
        sample_id=3,
        ba_id=7,
        raw_object_key="raw",
        redacted_object_key="redacted",
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )
    draft = SimpleNamespace(revision_id=11, ba_id=7, lock_version=2)
    repository = MagicMock(
        require_action_context=AsyncMock(
            return_value=ActionContext(7, "test", "detail", {}, True)
        ),
        get_draft=AsyncMock(return_value=draft),
        get_sample=AsyncMock(return_value=sample),
        create_draft=AsyncMock(return_value=draft),
        patch_draft=AsyncMock(return_value=draft),
        publish=AsyncMock(),
    )
    object_store = MagicMock(
        read_redacted=AsyncMock(return_value=raw),
        read_raw=AsyncMock(return_value=raw),
    )
    assistant = MagicMock(
        suggest=AsyncMock(
            return_value=ParserSuggestion(
                definition=DEFINITION,
                model_id=4,
                model_name="trusted-model",
                prompt_version="parser-definition-v1",
                duration_ms=12,
                attempts=1,
                redacted_sample_sha256="c" * 64,
            )
        )
    )
    service = AssistantActionParserService(
        repository=repository,
        rpc=MagicMock(),
        limiter_for=MagicMock(),
        rate_limiter=MagicMock(require=AsyncMock()),
        object_store=object_store,
        config=ParserConfigurationConfig(
            sample_hmac_key="sample-key", assist_receipt_key="receipt-key"
        ),
        assistant=assistant,
    )
    return service, repository


@pytest.mark.asyncio
async def test_initial_suggestion_returns_candidate_without_reading_or_writing_draft(
    assistant_service_parts,
):
    service, repository = assistant_service_parts

    result = await service.suggest_initial(
        ba_id=7,
        sample_id=3,
        model_id=4,
        output=ParserOutput(mode="json"),
    )

    assert result.definition == DEFINITION
    assert result.preview == ({"id": "1"},)
    repository.get_draft.assert_not_awaited()
    repository.create_draft.assert_not_awaited()
    service._object_store.read_redacted.assert_awaited_once_with("redacted")
    service._assistant.suggest.assert_awaited_once_with(
        redacted_sample={"data": [{"id": "1"}]},
        output_contract=ParserOutput(mode="json"),
        model_id=4,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_overrides", "definition"),
    [
        ({"purpose": "patch"}, DEFINITION),
        ({"ba_id": 8}, DEFINITION),
        ({"expires_at": 200}, DEFINITION),
        ({"issued_at": "100"}, DEFINITION),
        ({"source_sample_id": True}, DEFINITION),
        ({}, ALT_DEFINITION),
    ],
)
async def test_create_draft_rejects_invalid_create_receipt(
    assistant_service_parts, monkeypatch, payload_overrides, definition
):
    service, repository = assistant_service_parts
    monkeypatch.setattr(
        "services.parser_configuration.assistant.time.time", lambda: 200
    )
    receipt = service._sign(_create_receipt_payload(**payload_overrides))

    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_draft(
            ba_id=7,
            definition=definition,
            assist_receipt=receipt,
        )

    assert caught.value.code == "assist_receipt_invalid"
    repository.create_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_draft_rejects_tampered_receipt(
    assistant_service_parts, monkeypatch
):
    service, repository = assistant_service_parts
    monkeypatch.setattr(
        "services.parser_configuration.assistant.time.time", lambda: 200
    )
    receipt = service._sign(_create_receipt_payload())
    tampered = f"{receipt[:-1]}{'A' if receipt[-1] != 'A' else 'B'}"

    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_draft(
            ba_id=7,
            definition=DEFINITION,
            assist_receipt=tampered,
        )

    assert caught.value.code == "assist_receipt_invalid"
    repository.create_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_receipt_distinguishes_absent_and_explicit_null_default(
    assistant_service_parts,
):
    service, repository = assistant_service_parts
    candidate = await service.suggest_initial(
        ba_id=7,
        sample_id=3,
        model_id=4,
        output=ParserOutput(mode="json"),
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_draft(
            ba_id=7,
            definition=EXPLICIT_NULL_DEFINITION,
            assist_receipt=candidate.assist_receipt,
        )

    assert caught.value.code == "assist_receipt_invalid"
    repository.create_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_draft_records_ai_metadata_only_for_valid_create_receipt(
    assistant_service_parts,
):
    service, repository = assistant_service_parts
    candidate = await service.suggest_initial(
        ba_id=7, sample_id=3, model_id=4, output=ParserOutput(mode="json")
    )
    await service.create_draft(
        ba_id=7,
        definition=candidate.definition,
        assist_receipt=candidate.assist_receipt,
    )
    assert repository.create_draft.await_args.kwargs["source"] == "ai"
    assert repository.create_draft.await_args.kwargs["source_sample_id"] == 3

    repository.create_draft.reset_mock()
    await service.create_draft(ba_id=7, definition=DEFINITION, assist_receipt=None)
    assert repository.create_draft.await_args.kwargs["source"] == "manual"


@pytest.mark.asyncio
async def test_assist_returns_candidate_and_receipt_without_writing_draft(
    assistant_service_parts,
):
    service, repository = assistant_service_parts

    result = await service.assist(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        sample_id=3,
        model_id=4,
        output=ParserOutput(mode="json"),
    )

    assert result.definition == DEFINITION
    assert result.preview == ({"id": "1"},)
    assert result.assist_receipt
    repository.patch_draft.assert_not_awaited()
    repository.publish.assert_not_awaited()

    await service.patch_draft(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        definition=DEFINITION,
        assist_receipt=result.assist_receipt,
    )
    assert repository.patch_draft.await_args.kwargs["source"] == "ai"
    assert repository.patch_draft.await_args.kwargs["source_sample_id"] == 3
    metadata = repository.patch_draft.await_args.kwargs["generation_metadata"]
    assert metadata["model_id"] == 4
    assert "provider_key" not in metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "definition"),
    [
        ({"ba_id": 8}, DEFINITION),
        ({"revision_id": 12}, DEFINITION),
        ({"expected_lock_version": 3}, DEFINITION),
        (
            {},
            ParserDefinition.model_validate(
                {
                    "schema_version": 1,
                    "record_path": "/items",
                    "output": {"mode": "json"},
                    "fields": [{"target": "/id", "source": "/id"}],
                }
            ),
        ),
    ],
)
async def test_patch_rejects_receipt_context_mismatch(
    assistant_service_parts, overrides, definition, monkeypatch
):
    service, repository = assistant_service_parts
    monkeypatch.setattr(
        "services.parser_configuration.assistant.time.time", lambda: 1_786_435_300
    )
    receipt = service._sign(
        {
            "purpose": "patch",
            "ba_id": 7,
            "revision_id": 11,
            "lock_version": 2,
            "source_sample_id": 3,
            "definition_sha256": _receipt_hash(DEFINITION),
            "model_id": 4,
            "model_name": "trusted-model",
            "prompt_version": "parser-definition-v1",
            "redacted_sample_sha256": "c" * 64,
            "duration_ms": 12,
            "attempts": 1,
            "preview_summary": {"valid_records": 1},
            "issued_at": 1_786_435_200,
            "expires_at": 1_786_436_100,
        }
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await service.patch_draft(
            ba_id=overrides.get("ba_id", 7),
            revision_id=overrides.get("revision_id", 11),
            expected_lock_version=overrides.get("expected_lock_version", 2),
            definition=definition,
            assist_receipt=receipt,
        )

    assert caught.value.code == "assist_receipt_invalid"
    repository.patch_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_rejects_tampered_and_expired_receipts(
    assistant_service_parts, monkeypatch
):
    service, repository = assistant_service_parts
    monkeypatch.setattr("services.parser_configuration.assistant.time.time", lambda: 100)
    payload = {
        "purpose": "patch",
        "ba_id": 7,
        "revision_id": 11,
        "lock_version": 2,
        "source_sample_id": 3,
        "definition_sha256": _receipt_hash(DEFINITION),
        "model_id": 4,
        "model_name": "trusted-model",
        "prompt_version": "parser-definition-v1",
        "redacted_sample_sha256": "c" * 64,
        "duration_ms": 12,
        "attempts": 1,
        "preview_summary": {"valid_records": 1},
        "issued_at": 1,
        "expires_at": 100,
    }
    expired = service._sign(payload)
    tampered = f"{expired[:-1]}{'A' if expired[-1] != 'A' else 'B'}"

    for receipt in (expired, tampered):
        with pytest.raises(ParserConfigurationError) as caught:
            await service.patch_draft(
                ba_id=7,
                revision_id=11,
                expected_lock_version=2,
                definition=DEFINITION,
                assist_receipt=receipt,
            )
        assert caught.value.code == "assist_receipt_invalid"
    repository.patch_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_rejects_receipt_when_hmac_key_is_unavailable(
    assistant_service_parts,
):
    service, repository = assistant_service_parts
    service._receipt_key = b""
    forged = service._sign(
        {
            "purpose": "patch",
            "ba_id": 7,
            "revision_id": 11,
            "lock_version": 2,
            "source_sample_id": 3,
            "definition_sha256": _receipt_hash(DEFINITION),
            "model_id": 4,
            "model_name": "trusted-model",
            "prompt_version": "parser-definition-v1",
            "redacted_sample_sha256": "c" * 64,
            "duration_ms": 12,
            "attempts": 1,
            "preview_summary": {"valid_records": 1},
            "issued_at": 1,
            "expires_at": 4_000_000_000,
        }
    )

    with pytest.raises(ParserConfigurationError) as caught:
        await service.patch_draft(
            ba_id=7,
            revision_id=11,
            expected_lock_version=2,
            definition=DEFINITION,
            assist_receipt=forged,
        )

    assert caught.value.code == "assist_receipt_invalid"
    repository.patch_draft.assert_not_awaited()


def test_assistant_repr_does_not_expose_factory_secrets():
    factory = MagicMock()
    factory.provider_key = "provider-secret"

    assistant = ParserRuleAssistant(factory, max_bytes=4096, max_array_items=20)

    assert "provider-secret" not in repr(assistant)
