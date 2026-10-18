"""Tests for Redis-backed runtime configuration storage."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from runtime_config import (
    AnalysisVideoSettings,
    CleanerSettings,
    LlmSettings,
    LlmSettingsUpdate,
    PlatformCleanerPolicy,
    ProxySettings,
    ProxySettingsUpdate,
    RpcSettings,
    RuntimeConfigDefaults,
    RuntimeConfigReadError,
    RuntimeConfigStore,
    SchedulerSettings,
    proxy_configured,
    summarize_proxy,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str | bytes] = {}
        self.set_calls: list[tuple[str, str, dict[str, object]]] = []
        self.nx_winner: tuple[str, str] | None = None
        self.nx_disappearances = 0
        self.eval_hook: Callable[[], Awaitable[None]] | None = None
        self.mget_calls: list[list[str]] = []

    async def astrget(self, key: str) -> str | bytes | None:
        return self.values.get(key)

    async def amget(self, keys: list[str]) -> list[str | bytes | None]:
        self.mget_calls.append(list(keys))
        return [self.values.get(key) for key in keys]

    async def astrset(self, key: str, value: str, **kwargs: object) -> bool | None:
        self.set_calls.append((key, value, kwargs))
        if kwargs.get("nx") and self.nx_disappearances:
            self.nx_disappearances -= 1
            self.values.pop(key, None)
            return None
        if kwargs.get("nx") and self.nx_winner and self.nx_winner[0] == key:
            self.values[key] = self.nx_winner[1]
            self.nx_winner = None
            return None
        if kwargs.get("nx") and key in self.values:
            return None
        self.values[key] = value
        return True

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: str
    ) -> list[int | str | bytes | None]:
        del script, numkeys
        if self.eval_hook is not None:
            hook, self.eval_hook = self.eval_hook, None
            await hook()
        key, expected, replacement = keys_and_args
        current = self.values.get(key)
        comparable = current.decode() if isinstance(current, bytes) else current
        if comparable == expected:
            self.values[key] = replacement
            return [1, replacement]
        return [0, current]


def make_defaults() -> RuntimeConfigDefaults:
    policy = PlatformCleanerPolicy(
        p1=[{"max_hours": 24.0, "min_views": 100}]
    )
    cleaner = CleanerSettings(
        enabled=True,
    )
    return RuntimeConfigDefaults(
        llm=LlmSettings(),
        scheduler=SchedulerSettings(),
        rpc=RpcSettings(),
        analysis_video=AnalysisVideoSettings(),
        proxy=ProxySettings(),
        cleaner=cleaner,
        platform_policies={"douyin": policy},
    )


@pytest.mark.asyncio
async def test_first_get_initializes_once_with_nx() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())

    first = await store.get_llm()
    second = await store.get_llm()

    assert first == second == LlmSettings()
    assert len(redis.set_calls) == 1
    assert redis.set_calls[0][2] == {"nx": True}


@pytest.mark.asyncio
async def test_video_analysis_snapshot_uses_one_mget_for_consistent_values() -> None:
    redis = FakeRedis()
    redis.values["runtime:config:llm"] = LlmSettings(
        default_analysis_model_id=7
    ).model_dump_json()
    redis.values["runtime:config:analysis:video"] = AnalysisVideoSettings(
        is_base64=True
    ).model_dump_json()
    store = RuntimeConfigStore(redis, make_defaults())

    snapshot = await store.get_video_analysis_snapshot()

    assert snapshot.llm.default_analysis_model_id == 7
    assert snapshot.video.is_base64 is True
    assert redis.mget_calls == [[
        "runtime:config:llm", "runtime:config:analysis:video"
    ]]


@pytest.mark.asyncio
async def test_video_analysis_snapshot_initializes_missing_keys_then_mgets_again() -> None:
    redis = FakeRedis()

    snapshot = await RuntimeConfigStore(
        redis, make_defaults()
    ).get_video_analysis_snapshot()

    assert snapshot.llm == LlmSettings()
    assert snapshot.video == AnalysisVideoSettings()
    assert len(redis.mget_calls) == 2


@pytest.mark.asyncio
async def test_legacy_llm_request_path_defaults_to_chat_and_round_trips() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())

    assert await store.get_legacy_llm_request_path() == "chat"
    await store.set_legacy_llm_request_path("responses")
    assert await store.get_legacy_llm_request_path() == "responses"


@pytest.mark.asyncio
async def test_nx_race_returns_winner_without_overwrite() -> None:
    redis = FakeRedis()
    winner = LlmSettings(default_analysis_model_id=7).model_dump_json()
    redis.nx_winner = ("runtime:config:llm", winner)
    store = RuntimeConfigStore(redis, make_defaults())

    result = await store.get_llm()

    assert result.default_analysis_model_id == 7
    assert redis.values["runtime:config:llm"] == winner


@pytest.mark.asyncio
async def test_nx_race_retries_when_winner_disappears() -> None:
    redis = FakeRedis()
    redis.nx_disappearances = 1

    result = await RuntimeConfigStore(redis, make_defaults()).get_llm()

    assert result == LlmSettings()
    assert len(redis.set_calls) == 2


@pytest.mark.asyncio
async def test_nx_race_exhaustion_raises_safe_read_error() -> None:
    redis = FakeRedis()
    redis.nx_disappearances = 3

    with pytest.raises(RuntimeConfigReadError) as caught:
        await RuntimeConfigStore(redis, make_defaults()).get_llm()

    assert "category=initialization_race" in str(caught.value)
    assert len(redis.set_calls) == 3


@pytest.mark.asyncio
async def test_redis_wins_and_invalid_values_do_not_fallback() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())
    redis.values["runtime:config:llm"] = LlmSettings(
        default_analysis_model_id=9
    ).model_dump_json().encode()
    assert (await store.get_llm()).default_analysis_model_id == 9

    redis.values["runtime:config:llm"] = "not-json"
    with pytest.raises(RuntimeConfigReadError):
        await store.get_llm()
    redis.values["runtime:config:llm"] = '{"model": 123}'
    with pytest.raises(RuntimeConfigReadError):
        await store.get_llm()
    assert len(redis.set_calls) == 0


@pytest.mark.asyncio
async def test_domains_replace_independently_and_round_trip() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())
    original_rpc = await store.get_rpc()

    replaced = await store.replace_scheduler({"worker_id": "new-worker"})

    assert replaced.worker_id == "new-worker"
    assert await store.get_rpc() == original_rpc
    assert await store.get_scheduler() == replaced


@pytest.mark.asyncio
async def test_llm_partial_update_and_proxy_blank_secret_preserve_existing() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())
    await store.replace_llm(LlmSettings(default_analysis_model_id=4))
    updated_llm = await store.update_llm(LlmSettingsUpdate(max_tokens=123))
    assert updated_llm.default_analysis_model_id == 4
    assert updated_llm.max_tokens == 123


@pytest.mark.asyncio
async def test_llm_update_can_clear_each_default_without_changing_omitted_fields() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())
    await store.replace_llm(LlmSettings(
        default_analysis_model_id=4,
        default_transcription_model_id=5,
        max_tokens=123,
    ))

    analysis_cleared = await store.update_llm(LlmSettingsUpdate(
        default_analysis_model_id=None
    ))
    assert analysis_cleared.default_analysis_model_id is None
    assert analysis_cleared.default_transcription_model_id == 5
    assert analysis_cleared.max_tokens == 123

    transcription_cleared = await store.update_llm(LlmSettingsUpdate(
        default_transcription_model_id=None
    ))
    assert transcription_cleared.default_analysis_model_id is None
    assert transcription_cleared.default_transcription_model_id is None
    assert transcription_cleared.max_tokens == 123

    await store.replace_proxy(ProxySettings(url="http://user:pass@example.test:8080/path?q=1"))
    assert (await store.update_proxy(ProxySettingsUpdate(url=""))).url.endswith("/path?q=1")
    updated = await store.update_proxy(ProxySettingsUpdate(url="https://next.test:9443"))
    assert updated.url == "https://next.test:9443"


@pytest.mark.asyncio
async def test_atomic_llm_updates_preserve_interleaved_fields() -> None:
    redis = FakeRedis()
    store_a = RuntimeConfigStore(redis, make_defaults())
    store_b = RuntimeConfigStore(redis, make_defaults())
    await store_a.replace_llm(LlmSettings(default_analysis_model_id=1))
    first_eval_started = asyncio.Event()
    release_first_eval = asyncio.Event()

    async def pause_first_eval() -> None:
        first_eval_started.set()
        await release_first_eval.wait()

    redis.eval_hook = pause_first_eval
    first_update = asyncio.create_task(
        store_a.update_llm(LlmSettingsUpdate(default_transcription_model_id=2))
    )
    await first_eval_started.wait()
    field_update = await store_b.update_llm(LlmSettingsUpdate(default_analysis_model_id=3))
    release_first_eval.set()
    first_result = await first_update

    assert field_update.default_analysis_model_id == 3
    assert first_result.default_analysis_model_id == 3
    assert first_result.default_transcription_model_id == 2
    assert await store_a.get_llm() == first_result


@pytest.mark.asyncio
async def test_read_error_never_contains_secret_input() -> None:
    redis = FakeRedis()
    secret = "super-secret-value"
    redis.values["runtime:config:llm"] = f'{{"legacy":"{secret}'

    with pytest.raises(RuntimeConfigReadError) as caught:
        await RuntimeConfigStore(redis, make_defaults()).get_llm()

    assert secret not in str(caught.value)
    assert "runtime:config:llm" in str(caught.value)


@pytest.mark.parametrize(
    ("value", "summary"),
    [
        ("https://proxy.example.test", "https://proxy.example.test"),
        ("http://proxy.example.test:8080", "http://proxy.example.test:8080"),
        ("http://user:password@proxy.example.test", "http://proxy.example.test"),
        ("http://[2001:db8::1]:8080", "http://[2001:db8::1]:8080"),
        (
            "https://proxy.example.test:9443/path?q=secret#fragment",
            "https://proxy.example.test:9443",
        ),
    ],
)
def test_summarize_proxy_only_returns_scheme_host_and_optional_port(
    value: str, summary: str
) -> None:
    assert summarize_proxy(value) == summary


def test_proxy_configured_only_reports_presence() -> None:
    value = "http://user:password@[2001:db8::1]:8080/path?q=secret#fragment"
    assert proxy_configured(value) is True
    assert proxy_configured("  ") is False


@pytest.mark.asyncio
async def test_platform_defaults_missing_and_validation() -> None:
    redis = FakeRedis()
    store = RuntimeConfigStore(redis, make_defaults())

    policy = await store.get_platform_policy("douyin")
    assert policy is not None and policy.p1[0].min_views == 100
    assert await store.get_platform_policy("missing") is None
    with pytest.raises(ValueError):
        await store.get_platform_policy("../../bad")
    with pytest.raises(ValueError):
        await store.replace_platform_policy("bad:key", policy)

    replacement = PlatformCleanerPolicy(
        p1=[{"max_hours": 12.0, "min_views": 50}]
    )
    assert await store.replace_platform_policy("douyin", replacement) == replacement
    assert await store.get_platform_policy("douyin") == replacement
