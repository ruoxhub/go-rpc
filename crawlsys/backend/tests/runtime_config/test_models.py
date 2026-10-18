"""Tests for runtime configuration DTO validation."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

import pytest
from pydantic import ValidationError

from cleaner.config import CleanerConfig
from core.config import (
    AnalysisVideoConfig,
    LlmConfig,
    ProxyConfig,
    RpcConfig,
    SchedulerRuntimeConfig,
)
from runtime_config.models import (
    AnalysisVideoSettings,
    CleanerSettings,
    FilterRule,
    GradeRuleModel,
    LlmSettings,
    LlmSettingsUpdate,
    PlatformCleanerPolicy,
    ProxySettings,
    ProxySettingsUpdate,
    RpcSettings,
    SchedulerSettings,
)


@pytest.mark.parametrize(
    ("config", "dto"),
    [
        (SchedulerRuntimeConfig(), SchedulerSettings),
        (RpcConfig(), RpcSettings),
        (AnalysisVideoConfig(), AnalysisVideoSettings),
        (ProxyConfig(), ProxySettings),
        (CleanerConfig(enabled=False), CleanerSettings),
    ],
)
def test_settings_models_validate_dataclass_dict_and_serialize(
    config: object, dto: type
) -> None:
    values = asdict(config)
    if dto is CleanerSettings:
        values.pop("thresholds")
    settings = dto.model_validate(values)

    assert json.loads(settings.model_dump_json()) == settings.model_dump(mode="json")


def test_settings_models_accept_valid_boundaries_and_serialize() -> None:
    llm = LlmSettings(
        default_analysis_model_id=1,
        default_transcription_model_id=None,
        max_tokens=1,
        temperature=0,
        enable_thinking=False,
    )
    scheduler = SchedulerSettings(
        worker_id="worker",
        poll_interval_ms=1,
        default_loop_interval_seconds=1,
        batch_size=1,
        zombie_reap_after_seconds=30,
        graceful_shutdown_seconds=1,
    )
    video = AnalysisVideoSettings(
        is_base64=True,
        frame_sampling_strategy="timestamps",
        max_frames=2,
        frame_interval_seconds=1,
        frame_timestamps=(0, 1.5),
    )

    assert json.loads(llm.model_dump_json())["max_tokens"] == 1
    assert scheduler.poll_interval_ms == 1
    assert RpcSettings(base_url="https://rpc.example.test", timeout_seconds=1)
    assert video.model_dump(mode="json") == {
        "is_base64": True,
        "frame_sampling_strategy": "timestamps",
        "max_frames": 2,
        "frame_interval_seconds": 1.0,
        "frame_timestamps": [0.0, 1.5],
    }
    assert ProxySettings(url="")
    assert ProxySettingsUpdate(url=None)
    assert LlmSettingsUpdate(default_analysis_model_id=None)


def test_llm_update_allows_null_model_ids_but_rejects_null_generation_fields():
    update = LlmSettingsUpdate(
        default_analysis_model_id=None,
        default_transcription_model_id=None,
    )
    assert update.model_dump(exclude_unset=True) == {
        "default_analysis_model_id": None,
        "default_transcription_model_id": None,
    }
    for field in ("max_tokens", "temperature", "enable_thinking"):
        with pytest.raises(ValidationError):
            LlmSettingsUpdate.model_validate({field: None})


def test_scheduler_zombie_reap_minimum_boundary():
    with pytest.raises(ValidationError):
        SchedulerSettings(zombie_reap_after_seconds=29)
    assert SchedulerSettings(zombie_reap_after_seconds=30).zombie_reap_after_seconds == 30


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (LlmSettings, {"max_tokens": True}),
        (LlmSettings, {"max_tokens": 1.5}),
        (LlmSettings, {"temperature": True}),
        (LlmSettings, {"temperature": -0.1}),
        (LlmSettings, {"default_analysis_model_id": 0}),
        (LlmSettings, {"default_transcription_model_id": -1}),
        (SchedulerSettings, {"batch_size": True}),
        (SchedulerSettings, {"batch_size": 1.5}),
        (SchedulerSettings, {"poll_interval_ms": 0}),
        (RpcSettings, {"base_url": "ftp://rpc.example.test"}),
        (RpcSettings, {"base_url": "http:///missing-host"}),
        (RpcSettings, {"timeout_seconds": True}),
        (AnalysisVideoSettings, {"is_base64": 1}),
        (AnalysisVideoSettings, {"frame_sampling_strategy": "unknown"}),
        (AnalysisVideoSettings, {"max_frames": 1}),
        (AnalysisVideoSettings, {"max_frames": True}),
        (AnalysisVideoSettings, {"max_frames": 513}),
        (AnalysisVideoSettings, {"frame_interval_seconds": 0}),
        (AnalysisVideoSettings, {"frame_interval_seconds": 0.0009}),
        (AnalysisVideoSettings, {"frame_interval_seconds": True}),
        (AnalysisVideoSettings, {"frame_timestamps": (-1,)}),
        (AnalysisVideoSettings, {"frame_timestamps": (True,)}),
        (ProxySettings, {"url": "socks5://proxy.example.test"}),
    ],
)
def test_settings_models_reject_invalid_values(model: type, values: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(values)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_analysis_video_settings_reject_non_finite_sampling_numbers(value):
    with pytest.raises(ValidationError):
        AnalysisVideoSettings(frame_interval_seconds=value)
    with pytest.raises(ValidationError):
        AnalysisVideoSettings(frame_timestamps=(value,))


def test_timestamps_strategy_requires_configured_timestamps():
    with pytest.raises(ValidationError, match="frame_timestamps"):
        AnalysisVideoSettings(
            frame_sampling_strategy="timestamps",
            frame_timestamps=(),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    ("model", "field"),
    [
        (LlmSettings, "temperature"),
        (CleanerSettings, "poll_interval"),
        (CleanerSettings, "suspect_seconds"),
        (GradeRuleModel, "max_hours"),
    ],
)
def test_settings_float_fields_reject_non_finite_values(
    model: type, field: str, value: float
) -> None:
    values = {field: value}
    if model is CleanerSettings:
        values["enabled"] = False
    elif model is GradeRuleModel:
        values["min_views"] = 0

    with pytest.raises(ValidationError):
        model.model_validate(values)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("operator", ["=", "in"])
def test_filter_rejects_non_finite_float_values(operator: str, value: float) -> None:
    filter_value = [value] if operator == "in" else value
    with pytest.raises(ValidationError):
        FilterRule(field="view_count", operator=operator, value=filter_value)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:notaport",
        "http://user@:80",
        "http://example .com:80",
        "http://user:password@example.com:80",
    ],
)
def test_rpc_rejects_malformed_urls_and_userinfo(url: str) -> None:
    with pytest.raises(ValidationError):
        RpcSettings(base_url=url)


@pytest.mark.parametrize(
    "url",
    [
        "https://rpc.example.test/prefix?x=1",
        "https://rpc.example.test/prefix#frag",
    ],
)
def test_rpc_rejects_query_and_fragment(url: str) -> None:
    with pytest.raises(ValidationError):
        RpcSettings(base_url=url)


def test_rpc_allows_path_prefix() -> None:
    assert RpcSettings(base_url="https://rpc.example.test/prefix")


def test_proxy_accepts_valid_userinfo_but_rejects_malformed_url() -> None:
    assert ProxySettings(url="https://user:password@proxy.example.test:8443")
    with pytest.raises(ValidationError):
        ProxySettings(url="https://proxy.example.test:notaport")


def test_cleaner_settings_validate_current_config_boundaries() -> None:
    settings = CleanerSettings(
        enabled=True,
        poll_interval=0.1,
        batch_size=1,
        max_batches_per_platform=1,
        ttl_days=1,
        watermark_key="cleaner:watermark",
        suspect_seconds=0.1,
    )

    assert settings.enabled is True
    assert "thresholds" not in settings.model_dump()


@pytest.mark.parametrize("field", ["poll_interval", "batch_size", "max_batches_per_platform", "ttl_days", "suspect_seconds"])
def test_cleaner_positive_fields_reject_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        CleanerSettings.model_validate({field: 0})


@pytest.mark.parametrize("field", ["batch_size", "max_batches_per_platform", "ttl_days"])
@pytest.mark.parametrize("value", [True, 1.5])
def test_cleaner_integer_fields_are_strict(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        CleanerSettings.model_validate({field: value})


def test_platform_policy_requires_grade_rule_independently_of_cleaner() -> None:
    assert CleanerSettings(enabled=True).enabled is True
    with pytest.raises(ValidationError) as policy_error:
        PlatformCleanerPolicy(filters=[])
    assert policy_error.value.errors()[0]["loc"] == ("p1",)


@pytest.mark.parametrize(
    "values",
    [{"max_hours": 0, "min_views": 0}, {"max_hours": 1, "min_views": -1}],
)
def test_grade_rule_boundaries(values: dict) -> None:
    with pytest.raises(ValidationError):
        GradeRuleModel.model_validate(values)


@pytest.mark.parametrize("min_views", [True, 1.0])
def test_grade_rule_min_views_is_a_strict_integer(min_views: object) -> None:
    with pytest.raises(ValidationError):
        GradeRuleModel(max_hours=1, min_views=min_views)


@pytest.mark.parametrize(
    "field",
    [
        "view_count",
        "pub_time",
        "download_time",
        "created_time",
        "extend_data.metrics.play_count",
        "extend_data._private.value_2",
    ],
)
def test_filter_accepts_safe_fields(field: str) -> None:
    value = "2026-01-01" if field.endswith("time") else 1
    assert FilterRule(field=field, operator=">=", value=value).field == field


@pytest.mark.parametrize(
    "field",
    [
        "title",
        "view_count; DROP TABLE content",
        "extend_data.metrics->>'views'",
        "extend_data.9metrics",
        "extend_data.metrics.bad-name",
        "extend_data",
    ],
)
def test_filter_rejects_unknown_or_unsafe_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        FilterRule(field=field, operator="=", value=1)


@pytest.mark.parametrize("operator", ["=", "!=", ">", ">=", "<", "<=", "in", "exists"])
def test_filter_accepts_supported_operators(operator: str) -> None:
    value = None if operator == "exists" else [1] if operator == "in" else 1
    assert FilterRule(field="view_count", operator=operator, value=value)


@pytest.mark.parametrize("operator", ["like", "is", "contains"])
def test_filter_rejects_unknown_operators(operator: str) -> None:
    with pytest.raises(ValidationError):
        FilterRule(field="view_count", operator=operator, value=1)


@pytest.mark.parametrize(
    ("operator", "value"),
    [
        ("exists", 1),
        ("in", []),
        ("in", "one"),
        ("=", None),
        ("!=", [1]),
        (">", None),
        (">=", [1]),
        ("<", True),
        ("<=", "1"),
        ("=", {"nested": "object"}),
        ("in", [{"nested": "object"}]),
    ],
)
def test_filter_operator_value_combinations(operator: str, value: object) -> None:
    with pytest.raises(ValidationError) as error:
        FilterRule(field="view_count", operator=operator, value=value)
    assert error.value.errors()[0]["loc"][0] == "value"


def test_filter_allows_json_scalars_and_scalar_lists() -> None:
    assert FilterRule(field="extend_data.active", operator="=", value=False)


@pytest.mark.parametrize("value", [True, 1.0, "1"])
def test_view_count_rejects_non_strict_integers(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        FilterRule(field="view_count", operator="=", value=value)
    assert error.value.errors()[0]["loc"] == ("value",)


@pytest.mark.parametrize("value", [[1, True], [1, 2.0], [1, "2"]])
def test_view_count_in_rejects_non_strict_integer_items(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        FilterRule(field="view_count", operator="in", value=value)
    assert error.value.errors()[0]["loc"] == ("value",)


def test_date_filter_normalizes_iso_strings_to_datetime() -> None:
    rule = FilterRule(field="pub_time", operator=">=", value="2026-01-02T03:04:05Z")
    in_rule = FilterRule(
        field="created_time",
        operator="in",
        value=["2026-01-01", "2026-01-02T03:04:05+08:00"],
    )

    assert rule.value == datetime(2026, 1, 2, 3, 4, 5)
    assert all(isinstance(item, datetime) for item in in_rule.value)
    assert in_rule.value[1] == datetime(2026, 1, 1, 19, 4, 5)
    assert '"2026-01-02T03:04:05"' in rule.model_dump_json()


def test_date_filter_offsets_normalize_to_same_naive_utc() -> None:
    utc = FilterRule(
        field="pub_time", operator="=", value="2026-01-02T03:04:05Z"
    )
    offset = FilterRule(
        field="pub_time", operator="=", value="2026-01-02T11:04:05+08:00"
    )

    assert utc.value == offset.value == datetime(2026, 1, 2, 3, 4, 5)
    assert utc.value.tzinfo is None


@pytest.mark.parametrize("value", ["not-a-date", 1, 1.0, True])
def test_date_filter_rejects_invalid_or_non_string_values(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        FilterRule(field="download_time", operator="=", value=value)
    assert error.value.errors()[0]["loc"] == ("value",)

def test_scheduler_timezone_defaults_to_shanghai():
    assert SchedulerSettings().timezone == "Asia/Shanghai"


@pytest.mark.parametrize("value", ["Mars/Olympus", "Not/AZone", "Asia/NotACity"])
def test_scheduler_rejects_unknown_timezone(value):
    with pytest.raises(ValidationError, match="未知时区"):
        SchedulerSettings(timezone=value)


def test_scheduler_accepts_valid_timezone():
    assert SchedulerSettings(timezone="America/New_York").timezone == "America/New_York"
