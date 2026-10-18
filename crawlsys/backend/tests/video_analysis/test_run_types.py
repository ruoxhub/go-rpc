from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from services.video_analysis.run_types import (
    DEFAULT_ANALYSIS_REQUEST_PATH,
    DEFAULT_RUN_MAX_ATTEMPTS,
    ExecutionConfigSnapshot,
    ModelIdentitySnapshot,
    PromptBundle,
    PromptSnapshotError,
    VideoSettingsSnapshot,
    hash_prompt,
    normalize_prompt,
)


def _model_identity(**overrides: object) -> ModelIdentitySnapshot:
    values = {
        "model_id": 7,
        "provider_id": 3,
        "display_name": "Analysis Model",
        "protocol": "openai-completion",
        "remote_model_id": "provider/model-v1",
        "endpoint": "https://user:pass@example.com:8443/v1?token=hidden#fragment",
    }
    values.update(overrides)
    return ModelIdentitySnapshot.from_endpoint(**values)


def _execution_snapshot(**overrides: object) -> ExecutionConfigSnapshot:
    values = {
        "analysis_model": _model_identity(),
        "transcription_model": None,
        "temperature": 0.0,
        "max_tokens": 8192,
        "enable_thinking": False,
        "video": VideoSettingsSnapshot(
            is_base64=False,
            frame_sampling_strategy="scene_guided",
            max_frames=32,
            frame_interval_seconds=5.0,
            frame_timestamps=(),
        ),
        "request_path": "chat",
        "review_route": None,
    }
    values.update(overrides)
    return ExecutionConfigSnapshot.model_validate(values)


def test_normalize_prompt_normalizes_newlines_and_one_trailing_newline():
    assert normalize_prompt("  a\r\nb \r\n") == "a\nb\n"


@pytest.mark.parametrize("text", ["", " \r\n\t "])
def test_normalize_prompt_rejects_empty_content(text: str):
    with pytest.raises(PromptSnapshotError, match="PROMPT_INVALID") as exc_info:
        normalize_prompt(text)

    assert exc_info.value.code == "PROMPT_INVALID"


def test_prompt_bundle_normalizes_and_hashes_each_stage_independently():
    bundle = PromptBundle.create(
        rule_id=1,
        version_id=2,
        version=3,
        observation_prompt=" observe\r\n",
        evaluation_prompt="evaluate\rnext",
    )

    assert bundle.observation_prompt == "observe\n"
    assert bundle.evaluation_prompt == "evaluate\nnext\n"
    assert bundle.observation_prompt_hash == hashlib.sha256(
        b"observe\n"
    ).hexdigest()
    assert bundle.evaluation_prompt_hash == hashlib.sha256(
        b"evaluate\nnext\n"
    ).hexdigest()
    assert hash_prompt(" observe\r\n") == bundle.observation_prompt_hash


def test_model_identity_only_fingerprints_normalized_non_secret_endpoint():
    snapshot = _model_identity()
    expected = hashlib.sha256(
        b"openai-completion|https://example.com:8443/v1"
    ).hexdigest()

    assert snapshot.endpoint_fingerprint == expected
    serialized = snapshot.model_dump_json()
    assert "user" not in serialized
    assert "pass" not in serialized
    assert "hidden" not in serialized
    assert "example.com" not in serialized


@pytest.mark.parametrize("field", ["api_key", "password", "secret", "token"])
def test_execution_snapshot_rejects_secret_fields_recursively(field: str):
    with pytest.raises(ValidationError, match="secret-bearing field"):
        _execution_snapshot(**{field: "must-not-persist"})


def test_execution_snapshot_is_frozen_and_serializes_safe_behavior_only():
    snapshot = _execution_snapshot()

    with pytest.raises(ValidationError):
        snapshot.max_tokens = 1

    payload = snapshot.model_dump(mode="json")
    assert payload["analysis_model"]["model_id"] == 7
    assert payload["video"]["frame_sampling_strategy"] == "scene_guided"
    assert payload["request_path"] == "chat"
    assert set(payload).isdisjoint({"api_key", "base_url", "password", "token"})
    assert DEFAULT_RUN_MAX_ATTEMPTS == 3
    assert DEFAULT_ANALYSIS_REQUEST_PATH == "chat"
