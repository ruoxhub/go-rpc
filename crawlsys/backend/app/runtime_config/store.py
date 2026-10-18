"""Redis-backed storage for validated runtime configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

from pydantic import ValidationError

from .models import (
    AnalysisVideoSettings,
    CleanerSettings,
    LlmSettings,
    LlmSettingsUpdate,
    PlatformCleanerPolicy,
    ProxySettings,
    ProxySettingsUpdate,
    RpcSettings,
    RuntimeConfigModel,
    SchedulerSettings,
)


LLM_KEY = "runtime:config:llm"
LEGACY_LLM_REQUEST_PATH_KEY = "runtime:config:llm:legacy-request-path"
SCHEDULER_KEY = "runtime:config:scheduler"
RPC_KEY = "runtime:config:scheduler:rpc"
ANALYSIS_VIDEO_KEY = "runtime:config:analysis:video"
PROXY_KEY = "runtime:config:proxy"
CLEANER_KEY = "runtime:config:cleaner"
PLATFORM_KEY_PREFIX = "runtime:config:cleaner:platform:"

_SAFE_PLATFORM = re.compile(r"^[A-Za-z0-9_-]+$")
SettingsT = TypeVar("SettingsT", bound=RuntimeConfigModel)
_INITIALIZE_ATTEMPTS = 3
_UPDATE_ATTEMPTS = 4
_COMPARE_AND_SET = """
local current = redis.call('GET', KEYS[1])
if current == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2])
  return {1, ARGV[2]}
end
return {0, current or false}
"""


class RuntimeConfigReadError(RuntimeError):
    """A stored runtime configuration cannot be read safely."""


class RuntimeConfigUpdateError(RuntimeError):
    """A runtime configuration could not be updated atomically."""


class AsyncStringRedis(Protocol):
    async def astrget(self, table: str) -> str | bytes | None: ...

    async def amget(self, keys: list[str]) -> list[str | bytes | None]: ...

    async def astrset(
        self, table: str, value: str, **kwargs: Any
    ) -> bool | None: ...

    async def eval(
        self, script: str, numkeys: int, *keys_and_args: str
    ) -> list[int | str | bytes | None]: ...


@dataclass(frozen=True)
class RuntimeConfigDefaults:
    llm: LlmSettings
    scheduler: SchedulerSettings
    rpc: RpcSettings
    analysis_video: AnalysisVideoSettings
    proxy: ProxySettings
    cleaner: CleanerSettings
    platform_policies: dict[str, PlatformCleanerPolicy]
    legacy_llm: Any | None = None


@dataclass(frozen=True)
class VideoAnalysisSnapshot:
    llm: LlmSettings
    video: AnalysisVideoSettings


def proxy_configured(value: ProxySettings | str) -> bool:
    return bool((value.url if isinstance(value, ProxySettings) else value).strip())


def summarize_proxy(value: ProxySettings | str) -> str:
    url = value.url if isinstance(value, ProxySettings) else value
    if not url.strip():
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"


class RuntimeConfigStore:
    def __init__(
        self, redis: AsyncStringRedis, defaults: RuntimeConfigDefaults
    ) -> None:
        self._redis = redis
        self._defaults = defaults

    @staticmethod
    def _validate_stored(
        domain: str,
        key: str,
        model: type[SettingsT],
        raw: str | bytes,
    ) -> SettingsT:
        try:
            return model.model_validate_json(raw)
        except ValidationError as error:
            category = (
                "invalid_json"
                if error.errors(include_input=False)[0]["type"] == "json_invalid"
                else "validation_failed"
            )
            raise RuntimeConfigReadError(
                f"runtime config read failed: domain={domain} key={key} category={category}"
            ) from None

    async def _get_or_initialize(
        self,
        domain: str,
        key: str,
        model: type[SettingsT],
        default: SettingsT,
    ) -> SettingsT:
        for _ in range(_INITIALIZE_ATTEMPTS):
            raw = await self._redis.astrget(key)
            if raw is not None:
                return self._validate_stored(domain, key, model, raw)
            created = await self._redis.astrset(
                key, default.model_dump_json(), nx=True
            )
            if created is True:
                return default
        raise RuntimeConfigReadError(
            f"runtime config read failed: domain={domain} key={key} category=initialization_race"
        ) from None

    async def _replace(
        self, key: str, model: type[SettingsT], value: SettingsT | dict[str, Any]
    ) -> SettingsT:
        validated = model.model_validate(value)
        await self._redis.astrset(key, validated.model_dump_json())
        return validated

    async def _update_sensitive(
        self,
        domain: str,
        key: str,
        model: type[SettingsT],
        default: SettingsT,
        changes: dict[str, Any],
    ) -> SettingsT:
        await self._get_or_initialize(domain, key, model, default)
        for _ in range(_UPDATE_ATTEMPTS):
            raw = await self._redis.astrget(key)
            if raw is None:
                raise RuntimeConfigUpdateError(
                    f"runtime config update failed: domain={domain} key={key} category=missing"
                ) from None
            current = self._validate_stored(domain, key, model, raw)
            updated = model.model_validate({**current.model_dump(), **changes})
            encoded = updated.model_dump_json()
            expected = raw.decode() if isinstance(raw, bytes) else raw
            try:
                result = await self._redis.eval(
                    _COMPARE_AND_SET, 1, key, expected, encoded
                )
            except Exception:
                raise RuntimeConfigUpdateError(
                    f"runtime config update failed: domain={domain} key={key} category=redis_error"
                ) from None
            if result and result[0] == 1:
                return self._validate_stored(domain, key, model, encoded)
        raise RuntimeConfigUpdateError(
            f"runtime config update failed: domain={domain} key={key} category=conflict"
        ) from None

    async def get_llm(self) -> LlmSettings:
        return await self._get_or_initialize(
            "llm", LLM_KEY, LlmSettings, self._defaults.llm
        )

    async def get_video_analysis_snapshot(self) -> VideoAnalysisSnapshot:
        keys = [LLM_KEY, ANALYSIS_VIDEO_KEY]
        defaults = [self._defaults.llm, self._defaults.analysis_video]
        for _ in range(_INITIALIZE_ATTEMPTS):
            raw_llm, raw_video = await self._redis.amget(keys)
            missing = [
                (key, default)
                for key, default, raw in zip(keys, defaults, (raw_llm, raw_video))
                if raw is None
            ]
            if not missing:
                return VideoAnalysisSnapshot(
                    llm=self._validate_stored("llm", LLM_KEY, LlmSettings, raw_llm),
                    video=self._validate_stored(
                        "analysis.video", ANALYSIS_VIDEO_KEY,
                        AnalysisVideoSettings, raw_video,
                    ),
                )
            for key, default in missing:
                await self._redis.astrset(key, default.model_dump_json(), nx=True)
        raise RuntimeConfigReadError(
            "runtime config read failed: domain=video_analysis "
            "category=initialization_race"
        ) from None

    async def get_legacy_llm_request_path(self) -> str:
        raw = await self._redis.astrget(LEGACY_LLM_REQUEST_PATH_KEY)
        if raw is None:
            await self._redis.astrset(
                LEGACY_LLM_REQUEST_PATH_KEY, "chat", nx=True
            )
            raw = await self._redis.astrget(LEGACY_LLM_REQUEST_PATH_KEY)
        value = raw.decode() if isinstance(raw, bytes) else raw
        if value not in {"chat", "responses"}:
            raise RuntimeConfigReadError(
                "runtime config read failed: domain=llm.legacy_request_path "
                f"key={LEGACY_LLM_REQUEST_PATH_KEY} category=validation_failed"
            )
        return value

    async def set_legacy_llm_request_path(self, value: str) -> None:
        if value not in {"chat", "responses"}:
            raise ValueError("legacy LLM request path must be chat or responses")
        await self._redis.astrset(LEGACY_LLM_REQUEST_PATH_KEY, value)

    async def replace_llm(self, value: LlmSettings | dict[str, Any]) -> LlmSettings:
        return await self._replace(LLM_KEY, LlmSettings, value)

    async def update_llm(self, value: LlmSettingsUpdate) -> LlmSettings:
        patch = value.model_dump(exclude_unset=True)
        return await self._update_sensitive(
            "llm", LLM_KEY, LlmSettings, self._defaults.llm, patch
        )

    async def get_scheduler(self) -> SchedulerSettings:
        return await self._get_or_initialize(
            "scheduler", SCHEDULER_KEY, SchedulerSettings, self._defaults.scheduler
        )

    async def replace_scheduler(
        self, value: SchedulerSettings | dict[str, Any]
    ) -> SchedulerSettings:
        return await self._replace(SCHEDULER_KEY, SchedulerSettings, value)

    async def get_rpc(self) -> RpcSettings:
        return await self._get_or_initialize(
            "scheduler.rpc", RPC_KEY, RpcSettings, self._defaults.rpc
        )

    async def replace_rpc(self, value: RpcSettings | dict[str, Any]) -> RpcSettings:
        return await self._replace(RPC_KEY, RpcSettings, value)

    async def get_analysis_video(self) -> AnalysisVideoSettings:
        return await self._get_or_initialize(
            "analysis.video",
            ANALYSIS_VIDEO_KEY,
            AnalysisVideoSettings,
            self._defaults.analysis_video,
        )

    async def replace_analysis_video(
        self, value: AnalysisVideoSettings | dict[str, Any]
    ) -> AnalysisVideoSettings:
        return await self._replace(ANALYSIS_VIDEO_KEY, AnalysisVideoSettings, value)

    async def get_proxy(self) -> ProxySettings:
        return await self._get_or_initialize(
            "proxy", PROXY_KEY, ProxySettings, self._defaults.proxy
        )

    async def replace_proxy(
        self, value: ProxySettings | dict[str, Any]
    ) -> ProxySettings:
        return await self._replace(PROXY_KEY, ProxySettings, value)

    async def update_proxy(self, value: ProxySettingsUpdate) -> ProxySettings:
        patch = value.model_dump(exclude_none=True)
        if not str(patch.get("url", "x")).strip():
            patch.pop("url", None)
        return await self._update_sensitive(
            "proxy", PROXY_KEY, ProxySettings, self._defaults.proxy, patch
        )

    async def get_cleaner(self) -> CleanerSettings:
        return await self._get_or_initialize(
            "cleaner", CLEANER_KEY, CleanerSettings, self._defaults.cleaner
        )

    async def replace_cleaner(
        self, value: CleanerSettings | dict[str, Any]
    ) -> CleanerSettings:
        return await self._replace(CLEANER_KEY, CleanerSettings, value)

    @staticmethod
    def _platform_key(platform: str) -> str:
        if not _SAFE_PLATFORM.fullmatch(platform):
            raise ValueError("platform must contain only letters, digits, '_' or '-'")
        return f"{PLATFORM_KEY_PREFIX}{platform}"

    async def get_platform_policy(
        self, platform: str
    ) -> PlatformCleanerPolicy | None:
        key = self._platform_key(platform)
        default = self._defaults.platform_policies.get(platform)
        if default is None:
            raw = await self._redis.astrget(key)
            if raw is not None:
                return self._validate_stored(
                    f"cleaner.platform.{platform}",
                    key,
                    PlatformCleanerPolicy,
                    raw,
                )
            return None
        return await self._get_or_initialize(
            f"cleaner.platform.{platform}",
            key,
            PlatformCleanerPolicy,
            default,
        )

    async def replace_platform_policy(
        self,
        platform: str,
        value: PlatformCleanerPolicy | dict[str, Any],
    ) -> PlatformCleanerPolicy:
        return await self._replace(
            self._platform_key(platform), PlatformCleanerPolicy, value
        )
