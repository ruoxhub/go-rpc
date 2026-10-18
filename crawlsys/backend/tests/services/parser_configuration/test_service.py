from __future__ import annotations

import hashlib
import inspect
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.config import ParserConfigurationConfig
from go_rpc import InvalidRpcJsonError, RateLimitedRpcError, RpcError
from parser.definition import ParserOutput
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.repository import ActionContext
from services.parser_configuration.service import ActionParserService

DEFINITION = {
    "schema_version": 1,
    "record_path": "/items",
    "output": {"mode": "json"},
    "fields": [{"target": "/id", "source": "/id", "required": True}],
}


def sample_metadata(sample_id=3, response_sha256="abc"):
    return SimpleNamespace(
        sample_id=sample_id,
        ba_id=7,
        raw_object_key="raw",
        redacted_object_key="redacted",
        response_sha256=response_sha256,
    )


def draft_revision(*, required_target="/id"):
    definition = {
        **DEFINITION,
        "fields": [
            {"target": required_target, "source": required_target, "required": True}
        ],
    }
    from parser.definition import definition_sha256, validate_parser_definition

    parsed = validate_parser_definition(definition)
    return SimpleNamespace(
        ba_id=7,
        revision_id=11,
        lock_version=2,
        definition=definition,
        definition_sha256=definition_sha256(parsed),
    )


@pytest.fixture
def service_parts():
    repo = MagicMock()
    for name in (
        "require_action_context",
        "create_sample",
        "get_sample",
        "list_samples",
        "sample_reference_count",
        "delete_sample_metadata",
        "delete_sample",
        "get_draft",
        "require_samples",
        "save_preview",
        "delete_action_configuration",
    ):
        setattr(repo, name, AsyncMock())
    repo.require_action_context.return_value = ActionContext(
        ba_id=7,
        platform="test",
        action="detail",
        params_schema={"type": "object"},
        sample_safe=True,
    )
    rpc = MagicMock(invoke=AsyncMock())
    rate_limiter = MagicMock(require=AsyncMock())
    object_store = MagicMock(
        write_pair=AsyncMock(),
        read_raw=AsyncMock(),
        read_redacted=AsyncMock(),
        delete_pair=AsyncMock(),
    )
    limiter = MagicMock()
    limiter.__aenter__ = AsyncMock(return_value=limiter)
    limiter.__aexit__ = AsyncMock(return_value=None)
    limiter_for = MagicMock(return_value=limiter)
    config = ParserConfigurationConfig(sample_hmac_key="test-hmac")
    service = ActionParserService(
        repository=repo,
        rpc=rpc,
        limiter_for=limiter_for,
        rate_limiter=rate_limiter,
        object_store=object_store,
        config=config,
    )
    return service, repo, rpc, rate_limiter, object_store


@pytest.mark.asyncio
async def test_unsafe_action_requires_confirmation_before_rate_limit_or_rpc(
    service_parts,
):
    service, repo, rpc, rate_limiter, object_store = service_parts
    repo.require_action_context.return_value = ActionContext(
        ba_id=7,
        platform="test",
        action="detail",
        params_schema={"type": "object"},
        sample_safe=False,
    )
    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_sample(
            ba_id=7, params={"token": "secret"}, confirm_side_effect=False
        )
    assert caught.value.code == "sample_confirmation_required"
    rate_limiter.require.assert_not_awaited()
    rpc.invoke.assert_not_awaited()
    object_store.write_pair.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmation_is_not_forwarded_and_only_redacted_params_are_saved(
    service_parts,
):
    service, repo, rpc, _rate_limiter, object_store = service_parts
    repo.require_action_context.return_value = ActionContext(
        ba_id=7,
        platform="test",
        action="detail",
        params_schema={"type": "object"},
        sample_safe=False,
    )
    rpc.invoke.return_value = {"data": [{"email": "alice@example.com"}]}
    object_store.write_pair.return_value = SimpleNamespace(
        raw_object_key="raw",
        redacted_object_key="redacted",
        response_sha256="a" * 64,
        response_bytes=42,
    )
    await service.create_sample(
        ba_id=7,
        params={"access_token": "secret", "cursor": 1},
        confirm_side_effect=True,
    )
    assert rpc.invoke.await_args is not None
    assert rpc.invoke.await_args.args[2] == {"access_token": "secret", "cursor": 1}
    assert repo.create_sample.await_args is not None
    metadata = repo.create_sample.await_args.args[0]
    assert metadata.request_params_redacted["access_token"] == "<redacted:token>"
    assert not hasattr(metadata, "request_params_raw")


@pytest.mark.asyncio
async def test_sample_success_order_is_bounded_and_never_calls_sink(service_parts):
    service, repo, rpc, rate_limiter, object_store = service_parts
    events = []
    repo.require_action_context.side_effect = lambda _ba_id: (
        events.append("action") or repo.require_action_context.return_value
    )
    rate_limiter.require.side_effect = lambda **_kwargs: events.append("redis")
    limiter = service._limiter_for.return_value
    limiter.__aenter__.side_effect = lambda: events.append("platform") or limiter
    rpc.invoke.side_effect = lambda *_args, **_kwargs: (
        events.append("rpc") or {"id": "1"}
    )
    object_store.write_pair.side_effect = lambda **_kwargs: (
        events.append("objects")
        or SimpleNamespace(
            raw_object_key="raw",
            redacted_object_key="redacted",
            response_sha256="a" * 64,
            response_bytes=10,
        )
    )
    repo.create_sample.side_effect = lambda _metadata: (
        events.append("database") or sample_metadata()
    )

    await service.create_sample(ba_id=7, params={}, confirm_side_effect=False)

    assert events == ["action", "redis", "platform", "rpc", "objects", "database"]
    assert rpc.invoke.await_args is not None
    assert rpc.invoke.await_args.kwargs == {
        "max_response_bytes": service._config.sample_max_response_bytes
    }


@pytest.mark.asyncio
async def test_database_failure_compensates_object_pair(service_parts):
    service, repo, rpc, _rate_limiter, object_store = service_parts
    rpc.invoke.return_value = {"id": "1"}
    stored = SimpleNamespace(
        raw_object_key="raw",
        redacted_object_key="redacted",
        response_sha256="a" * 64,
        response_bytes=10,
    )
    object_store.write_pair.return_value = stored
    repo.create_sample.side_effect = RuntimeError("database failed")

    with pytest.raises(RuntimeError):
        await service.create_sample(ba_id=7, params={}, confirm_side_effect=False)

    object_store.delete_pair.assert_awaited_once_with("raw", "redacted")


@pytest.mark.asyncio
async def test_missing_hmac_key_fails_without_rpc(service_parts):
    service, _repo, rpc, _rate_limiter, _object_store = service_parts
    service._sample_hmac_key = b""
    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_sample(ba_id=7, params={}, confirm_side_effect=True)
    assert caught.value.code == "sample_hmac_unavailable"
    rpc.invoke.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rpc_error", "code", "status_code"),
    [
        (
            RateLimitedRpcError("hidden", retry_after_seconds=9),
            "sample_rate_limited",
            429,
        ),
        (InvalidRpcJsonError("hidden body"), "sample_rpc_invalid_json", 502),
    ],
)
async def test_rpc_errors_map_to_stable_whitelist(
    service_parts, rpc_error, code, status_code
):
    service, _repo, rpc, _rate_limiter, object_store = service_parts
    rpc.invoke.side_effect = rpc_error
    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_sample(ba_id=7, params={}, confirm_side_effect=False)
    assert caught.value.code == code
    assert caught.value.status_code == status_code
    assert "hidden" not in str(caught.value.details)
    object_store.write_pair.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_rpc_error_does_not_expose_exception_text(service_parts):
    service, _repo, rpc, _rate_limiter, object_store = service_parts
    rpc.invoke.side_effect = RpcError("raw body token=secret")
    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_sample(ba_id=7, params={}, confirm_side_effect=False)
    assert caught.value.code == "sample_rpc_failed"
    assert "secret" not in str(caught.value)
    object_store.write_pair.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_container_response_is_rejected_before_storage(service_parts):
    service, _repo, rpc, _rate_limiter, object_store = service_parts
    rpc.invoke.return_value = "secret response"
    with pytest.raises(ParserConfigurationError) as caught:
        await service.create_sample(ba_id=7, params={}, confirm_side_effect=False)
    assert caught.value.code == "sample_rpc_invalid_json"
    object_store.write_pair.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_sample_reads_only_redacted_object(service_parts):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    repo.get_sample.return_value = sample_metadata()
    object_store.read_redacted.return_value = b'{"token":"<redacted:token>"}'
    result = await service.get_sample(ba_id=7, sample_id=3)
    assert result == {"token": "<redacted:token>"}
    object_store.read_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_sample_preserves_storage_failure_and_maps_corrupt_json(
    service_parts,
):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    repo.get_sample.return_value = sample_metadata()
    object_store.read_redacted.side_effect = ParserConfigurationError(
        "sample_storage_failed", "stable storage failure"
    )
    with pytest.raises(ParserConfigurationError) as caught:
        await service.get_sample(ba_id=7, sample_id=3)
    assert caught.value.code == "sample_storage_failed"

    object_store.read_redacted.side_effect = None
    object_store.read_redacted.return_value = b'{"broken"'
    with pytest.raises(ParserConfigurationError) as caught:
        await service.get_sample(ba_id=7, sample_id=3)
    assert caught.value.code == "sample_object_corrupt"


@pytest.mark.asyncio
async def test_delete_referenced_sample_keeps_objects(service_parts):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    repo.delete_sample.side_effect = ParserConfigurationError(
        "sample_in_use", "sample is in use"
    )
    with pytest.raises(ParserConfigurationError) as caught:
        await service.delete_sample(ba_id=7, sample_id=3)
    assert caught.value.code == "sample_in_use"
    object_store.delete_pair.assert_not_awaited()
    assert repo.delete_sample.await_args is not None
    delete_objects = repo.delete_sample.await_args.kwargs["delete_objects"]
    await delete_objects(sample_metadata())
    object_store.delete_pair.assert_awaited_once_with("raw", "redacted")


@pytest.mark.asyncio
async def test_preview_uses_raw_object_but_returns_redacted_records(service_parts):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    draft = draft_revision()
    raw = b'{"items":[{"email":"alice@example.com","id":"1"}]}'
    repo.get_draft.return_value = draft
    repo.require_action_context.return_value = ActionContext(
        7, "test", "detail", {}, True
    )
    repo.require_samples.return_value = [
        sample_metadata(response_sha256=hashlib.sha256(raw).hexdigest())
    ]
    object_store.read_raw.return_value = raw
    report = await service.preview(
        ba_id=7, revision_id=11, expected_lock_version=2, sample_ids=[3]
    )
    assert report.passed is True
    assert "alice@example.com" not in str(report.preview)
    repo.save_preview.assert_awaited_once()


@pytest.mark.asyncio
async def test_preview_passes_with_valid_records_and_warns_about_dirty_records(
    service_parts,
):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    draft = draft_revision()
    raw = b'{"items":[{"id":"1"},{}]}'
    repo.get_draft.return_value = draft
    repo.require_samples.return_value = [
        sample_metadata(response_sha256=hashlib.sha256(raw).hexdigest())
    ]
    object_store.read_raw.return_value = raw
    report = await service.preview(
        ba_id=7, revision_id=11, expected_lock_version=2, sample_ids=[3]
    )
    assert report.passed is True
    assert report.valid_records == 1
    assert report.invalid_records == 1
    assert repo.save_preview.await_args.kwargs["validation_report"]["passed"] is True


@pytest.mark.asyncio
async def test_failed_preview_replaces_green_report_with_failed_report(service_parts):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    draft = draft_revision(required_target="/missing")
    raw = b'{"items":[{}]}'
    repo.get_draft.return_value = draft
    repo.require_samples.return_value = [
        sample_metadata(response_sha256=hashlib.sha256(raw).hexdigest())
    ]
    object_store.read_raw.return_value = raw
    with pytest.raises(ParserConfigurationError) as caught:
        await service.preview(
            ba_id=7, revision_id=11, expected_lock_version=2, sample_ids=[3]
        )
    assert caught.value.code == "parser_preview_failed"
    assert repo.save_preview.await_args.kwargs["validation_report"]["passed"] is False


@pytest.mark.asyncio
async def test_preview_preserves_storage_failure_instead_of_marking_missing(
    service_parts,
):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    draft = draft_revision()
    repo.get_draft.return_value = draft
    repo.require_samples.return_value = [sample_metadata(response_sha256="a" * 64)]
    object_store.read_raw.side_effect = ParserConfigurationError(
        "sample_storage_failed", "stable storage failure"
    )
    with pytest.raises(ParserConfigurationError) as caught:
        await service.preview(
            ba_id=7, revision_id=11, expected_lock_version=2, sample_ids=[3]
        )
    assert caught.value.code == "sample_storage_failed"
    repo.save_preview.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_action_removes_objects_before_database_rows(service_parts):
    service, repo, _rpc, _rate_limiter, object_store = service_parts
    events = []
    object_store.delete_pair.side_effect = lambda *_args: events.append("objects")

    async def delete_action_configuration(_ba_id, *, delete_objects):
        await delete_objects(sample_metadata())
        events.append("database")

    repo.delete_action_configuration.side_effect = delete_action_configuration
    await service.delete_action(7)
    assert events == ["objects", "database"]


@pytest.mark.asyncio
async def test_manual_service_exposes_stable_ai_unavailable(service_parts):
    service, *_parts = service_parts
    with pytest.raises(ParserConfigurationError) as caught:
        await service.assist(
            ba_id=7,
            revision_id=11,
            expected_lock_version=2,
            sample_id=3,
            model_id=4,
            output=ParserOutput(mode="json"),
        )
    assert caught.value.code == "ai_unavailable"
    assert caught.value.status_code == 503
    assert list(inspect.signature(service.assist).parameters) == [
        "ba_id",
        "revision_id",
        "expected_lock_version",
        "sample_id",
        "model_id",
        "output",
    ]


@pytest.mark.asyncio
async def test_restore_delegates_ba_id_to_repository(service_parts):
    service, repo, _rpc, _rate_limiter, _object_store = service_parts
    repo.restore_as_draft = AsyncMock(return_value=SimpleNamespace(ba_id=7))
    await service.restore(ba_id=7, revision_id=11)
    repo.restore_as_draft.assert_awaited_once_with(11, ba_id=7)


@pytest.mark.asyncio
async def test_patch_and_lifecycle_delegate_without_ai_metadata(service_parts):
    service, repo, _rpc, _rate_limiter, _object_store = service_parts
    repo.get_draft = AsyncMock(return_value=draft_revision())
    repo.patch_draft = AsyncMock(return_value=draft_revision())
    repo.publish = AsyncMock(return_value=SimpleNamespace(status="published"))
    repo.archive = AsyncMock(return_value=SimpleNamespace(status="archived"))
    repo.delete_draft = AsyncMock()

    await service.patch_draft(
        ba_id=7,
        revision_id=11,
        expected_lock_version=2,
        definition=DEFINITION,
    )
    assert repo.patch_draft.await_args is not None
    assert repo.patch_draft.await_args.kwargs["source"] == "manual"
    assert repo.patch_draft.await_args.kwargs["source_sample_id"] is None
    assert repo.patch_draft.await_args.kwargs["generation_metadata"] is None
    await service.publish(ba_id=7, revision_id=11)
    await service.archive(ba_id=7, revision_id=11)
    await service.delete_draft(ba_id=7, revision_id=11)
    repo.publish.assert_awaited_once_with(11)
    repo.archive.assert_awaited_once_with(7, 11)
    repo.delete_draft.assert_awaited_once_with(11)


@pytest.mark.asyncio
async def test_sensitive_payloads_never_reach_logs(service_parts, caplog, monkeypatch):
    service, repo, rpc, _rate_limiter, object_store = service_parts
    sentinel = "task10-secret-sentinel-7f52"

    class CapturingLogger:
        def error(self, message, *args):
            logging.getLogger("task10-sensitive-log-test").error(message.format(*args))

    import services.parser_configuration.service as service_module

    monkeypatch.setattr(service_module, "logger", CapturingLogger())
    caplog.set_level(logging.ERROR, logger="task10-sensitive-log-test")
    rpc.invoke.return_value = {
        "body": sentinel,
        "email": f"{sentinel}@example.com",
        "phone": "13800138000",
        "token": sentinel,
    }
    object_store.write_pair.return_value = SimpleNamespace(
        raw_object_key=f"raw/{sentinel}",
        redacted_object_key=f"redacted/{sentinel}",
        response_sha256="a" * 64,
        response_bytes=42,
    )
    repo.create_sample.side_effect = RuntimeError("database failure")
    object_store.delete_pair.side_effect = RuntimeError("object failure")

    with pytest.raises(RuntimeError):
        await service.create_sample(
            ba_id=7,
            params={"token": sentinel, "body": sentinel},
            confirm_side_effect=False,
        )

    rpc.invoke.side_effect = RpcError(f"rpc body {sentinel}")
    with pytest.raises(ParserConfigurationError):
        await service.create_sample(
            ba_id=7,
            params={"token": sentinel},
            confirm_side_effect=False,
        )

    assert sentinel not in caplog.text
    assert f"{sentinel}@example.com" not in caplog.text
    assert "13800138000" not in caplog.text
    assert json.dumps({"token": sentinel}) not in caplog.text
