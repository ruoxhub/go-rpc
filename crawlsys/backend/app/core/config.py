"""Scheduler configuration — parsed from config.toml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from math import isfinite
from typing import Any
from urllib.parse import urlparse

from common.constants import (
    MAX_ANALYSIS_FRAMES,
    MIN_FRAME_INTERVAL_SECONDS,
    MIN_ZOMBIE_REAP_SECONDS,
)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None else value


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class PlatformQuota:
    platform: str
    concurrency: int = 1
    rps: float = 1.0
    burst: int = 3
    cooldown_on_block: int = 300


@dataclass(frozen=True)
class PgConfig:
    username: str
    password: str
    host: str
    port: int
    database: str

    @classmethod
    def from_raw(cls, raw: dict) -> "PgConfig":
        return cls(
            username=_env_str("CRAWLER_PG_USERNAME", raw.get("username", "")),
            password=os.environ.get("CRAWLER_PG_PASSWORD", raw.get("password", "")),
            host=_env_str("CRAWLER_PG_HOST", raw.get("host", "localhost")),
            port=_env_int("CRAWLER_PG_PORT", raw.get("port", 5432)),
            database=_env_str("CRAWLER_PG_DATABASE", raw.get("database", "")),
        )


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    password: str = ""

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/0"
        return f"redis://{self.host}:{self.port}/0"

    @classmethod
    def from_raw(cls, raw: dict) -> "RedisConfig":
        return cls(
            host=_env_str("CRAWLER_REDIS_HOST", raw.get("host", "localhost")),
            port=_env_int("CRAWLER_REDIS_PORT", raw.get("port", 6379)),
            password=os.environ.get("CRAWLER_REDIS_PASSWORD", raw.get("password", "")),
        )


@dataclass(frozen=True)
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    mode: str = "release"
    debugger: bool = False


@dataclass(frozen=True)
class LlmConfig:
    format: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    base_url: str = ""
    request_path: str = "chat"
    max_tokens: int = 8192
    temperature: float = 0.0
    enable_thinking: bool = False

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "LlmConfig":
        return cls(
            format=raw.get("format", "openai"),
            model=raw.get("model", "gpt-4o"),
            api_key=os.environ.get("OPENAI_API_KEY", raw.get("api_key", "")),
            base_url=os.environ.get("OPENAI_BASE_URL", raw.get("base_url", "")),
            request_path=raw.get("request_path", "chat"),
            max_tokens=raw.get("max_tokens", 8192),
            temperature=raw.get("temperature", 0.0),
            enable_thinking=raw.get("enable_thinking", False),
        )


@dataclass(frozen=True)
class MinioConfig:
    username: str = ""
    password: str = ""
    host: str = "localhost"
    port: int = 9000
    secure: bool = False


@dataclass(frozen=True)
class AnalysisVideoConfig:
    is_base64: bool = False
    frame_sampling_strategy: str = "scene_guided"
    max_frames: int = 32
    frame_interval_seconds: float = 5.0
    frame_timestamps: tuple[float, ...] = ()


@dataclass(frozen=True)
class SchedulerRuntimeConfig:
    worker_id: str = "scheduler-local-01"
    poll_interval_ms: int = 1000
    default_loop_interval_seconds: int = 3600
    batch_size: int = 10
    zombie_reap_after_seconds: int = 600
    graceful_shutdown_seconds: int = 30


@dataclass(frozen=True)
class RpcConfig:
    base_url: str = "http://localhost:5612"
    timeout_seconds: int = 60


@dataclass(frozen=True)
class ProxyConfig:
    url: str = ""


@dataclass(frozen=True)
class McpConfig:
    enabled: bool = True
    allowed_hosts: tuple[str, ...] = (
        "192.168.1.5",
        "192.168.1.5:*",
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
    )
    allowed_origins: tuple[str, ...] = ()
    inline_object_limit_bytes: int = 10 * 1024 * 1024
    inline_object_hard_limit_bytes: int = 50 * 1024 * 1024
    presigned_expiry_minutes: int = 15


@dataclass(frozen=True)
class ParserConfigurationConfig:
    sample_bucket: str = "crawler-parser-samples"
    sample_max_response_bytes: int = 10 * 1024 * 1024
    json_max_depth: int = 64
    json_max_nodes: int = 100_000
    ai_max_bytes: int = 256 * 1024
    ai_max_array_items: int = 20
    sample_global_limit_per_minute: int = 30
    sample_action_limit_per_minute: int = 5
    assist_global_limit_per_minute: int = 10
    assist_action_limit_per_minute: int = 2
    assist_receipt_ttl_seconds: int = 900
    preview_max_records: int = 20
    preview_max_errors: int = 200
    object_sse_enabled: bool = False
    sample_hmac_key: str = field(default="", repr=False)
    sample_hmac_key_version: str = "v1"
    assist_receipt_key: str = field(default="", repr=False)

    def storage_ready(self, *, web_mode: str, minio_secure: bool) -> bool:
        return web_mode != "release" or (minio_secure and self.object_sse_enabled)


_MAX_INLINE_OBJECT_HARD_LIMIT_BYTES = 50 * 1024 * 1024


_UNSET = object()


@dataclass(frozen=True, init=False)
class SchedulerConfig:
    rpc_token: str = ""
    postgresql: PgConfig = field(default_factory=lambda: PgConfig("", "", "localhost", 5432, ""))
    redis: RedisConfig = field(default_factory=lambda: RedisConfig("localhost", 6379))
    minio: MinioConfig = field(default_factory=MinioConfig)
    web: WebConfig = field(default_factory=WebConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    analysis_video: AnalysisVideoConfig = field(default_factory=AnalysisVideoConfig)
    runtime: SchedulerRuntimeConfig = field(default_factory=SchedulerRuntimeConfig)
    rpc: RpcConfig = field(default_factory=RpcConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    parser_configuration: ParserConfigurationConfig = field(
        default_factory=ParserConfigurationConfig
    )

    def __init__(
        self,
        poll_interval: float | object = _UNSET,
        default_loop_interval_seconds: int | object = _UNSET,
        zombie_reap_after_seconds: int | object = _UNSET,
        rpc_base_url: str | object = _UNSET,
        rpc_timeout: int | object = _UNSET,
        rpc_token: str = "",
        postgresql: PgConfig | None = None,
        redis: RedisConfig | None = None,
        minio: MinioConfig | None = None,
        web: WebConfig | None = None,
        llm: LlmConfig | None = None,
        analysis_video: AnalysisVideoConfig | None = None,
        runtime: SchedulerRuntimeConfig | None = None,
        rpc: RpcConfig | None = None,
        proxy: ProxyConfig | None = None,
        mcp: McpConfig | None = None,
        parser_configuration: ParserConfigurationConfig | None = None,
    ) -> None:
        runtime = runtime or SchedulerRuntimeConfig()
        runtime_values = {
            "worker_id": runtime.worker_id,
            "poll_interval_ms": runtime.poll_interval_ms,
            "default_loop_interval_seconds": runtime.default_loop_interval_seconds,
            "batch_size": runtime.batch_size,
            "zombie_reap_after_seconds": runtime.zombie_reap_after_seconds,
            "graceful_shutdown_seconds": runtime.graceful_shutdown_seconds,
        }
        if poll_interval is not _UNSET:
            if isinstance(poll_interval, (int, float)) and not isinstance(
                poll_interval, bool
            ):
                milliseconds = poll_interval * 1000
                runtime_values["poll_interval_ms"] = (
                    int(milliseconds)
                    if float(milliseconds).is_integer()
                    else milliseconds
                )
            else:
                runtime_values["poll_interval_ms"] = poll_interval
        if default_loop_interval_seconds is not _UNSET:
            runtime_values["default_loop_interval_seconds"] = default_loop_interval_seconds
        if zombie_reap_after_seconds is not _UNSET:
            runtime_values["zombie_reap_after_seconds"] = zombie_reap_after_seconds
        rpc = rpc or RpcConfig()
        if rpc_base_url is not _UNSET or rpc_timeout is not _UNSET:
            rpc = RpcConfig(
                base_url=rpc.base_url if rpc_base_url is _UNSET else rpc_base_url,
                timeout_seconds=(
                    rpc.timeout_seconds if rpc_timeout is _UNSET else rpc_timeout
                ),
            )
        object.__setattr__(self, "runtime", SchedulerRuntimeConfig(**runtime_values))
        object.__setattr__(self, "rpc", rpc)
        object.__setattr__(self, "rpc_token", rpc_token)
        object.__setattr__(self, "postgresql", postgresql or PgConfig("", "", "localhost", 5432, ""))
        object.__setattr__(self, "redis", redis or RedisConfig("localhost", 6379))
        object.__setattr__(self, "minio", minio or MinioConfig())
        object.__setattr__(self, "web", web or WebConfig())
        object.__setattr__(self, "llm", llm or LlmConfig())
        object.__setattr__(self, "analysis_video", analysis_video or AnalysisVideoConfig())
        object.__setattr__(self, "proxy", proxy or ProxyConfig())
        object.__setattr__(self, "mcp", mcp or McpConfig())
        object.__setattr__(
            self,
            "parser_configuration",
            parser_configuration or ParserConfigurationConfig(),
        )

    @property
    def worker_id(self) -> str:
        return self.runtime.worker_id

    @property
    def poll_interval_ms(self) -> int:
        return self.runtime.poll_interval_ms

    @property
    def poll_interval(self) -> float:
        return self.runtime.poll_interval_ms / 1000.0

    @property
    def default_loop_interval_seconds(self) -> int:
        return self.runtime.default_loop_interval_seconds

    @property
    def batch_size(self) -> int:
        return self.runtime.batch_size

    @property
    def zombie_reap_after_seconds(self) -> int:
        return self.runtime.zombie_reap_after_seconds

    @property
    def graceful_shutdown_seconds(self) -> int:
        return self.runtime.graceful_shutdown_seconds

    @property
    def rpc_base_url(self) -> str:
        return self.rpc.base_url

    @property
    def rpc_timeout(self) -> int:
        return self.rpc.timeout_seconds

    @classmethod
    def from_toml(cls, path: str) -> SchedulerConfig:
        with open(path, "rb") as f:
            raw = tomllib.load(f)

        sched = raw.get("scheduler", {})
        runtime = SchedulerRuntimeConfig(
            worker_id=sched.get("worker_id", "scheduler-local-01"),
            poll_interval_ms=sched.get("poll_interval_ms", 1000),
            default_loop_interval_seconds=sched.get(
                "default_loop_interval_seconds", 3600
            ),
            batch_size=sched.get("batch_size", 10),
            zombie_reap_after_seconds=sched.get("zombie_reap_after_seconds", 600),
            graceful_shutdown_seconds=sched.get("graceful_shutdown_seconds", 30),
        )
        rpc_raw = sched.get("rpc", {})
        rpc = RpcConfig(
            base_url=_env_str(
                "CRAWLER_RPC_BASE_URL",
                rpc_raw.get("base_url", "http://localhost:5612"),
            ),
            timeout_seconds=_env_int(
                "CRAWLER_RPC_TIMEOUT_SECONDS", rpc_raw.get("timeout_seconds", 60)
            ),
        )
        rpc_token = os.environ.get("SEKIRO_TOKEN", "")

        pg_raw = raw.get("postgresql", {})
        pg = PgConfig.from_raw(pg_raw)

        rd_raw = raw.get("redis", {})
        rd = RedisConfig.from_raw(rd_raw)
        minio_raw = raw.get("minio", {})
        minio = MinioConfig(
            username=_env_str(
                "CRAWLER_MINIO_USERNAME", minio_raw.get("username", "")
            ),
            password=os.environ.get(
                "CRAWLER_MINIO_PASSWORD", minio_raw.get("password", "")
            ),
            host=_env_str(
                "CRAWLER_MINIO_HOST", minio_raw.get("host", "localhost")
            ),
            port=_env_int("CRAWLER_MINIO_PORT", minio_raw.get("port", 9000)),
            secure=_env_bool(
                "CRAWLER_MINIO_SECURE", minio_raw.get("secure", False)
            ),
        )

        web_raw = raw.get("web", {})
        web_mode = web_raw.get("mode")
        legacy_debugger = web_raw.get("debugger", False)
        if web_mode is None:
            web_mode = "debugger" if legacy_debugger else "release"
        web = WebConfig(
            host=web_raw.get("host", "0.0.0.0"),
            port=web_raw.get("port", 8080),
            mode=web_mode,
            debugger=web_mode == "debugger",
        )
        llm = LlmConfig.from_raw(raw.get("llm", {}))
        video_raw = raw.get("analysis", {}).get("video", {})
        frame_timestamps = video_raw.get("frame_timestamps", ())
        analysis_video = AnalysisVideoConfig(
            is_base64=video_raw.get("is_base64", False),
            frame_sampling_strategy=video_raw.get(
                "frame_sampling_strategy", "scene_guided"
            ),
            max_frames=video_raw.get("max_frames", 32),
            frame_interval_seconds=video_raw.get("frame_interval_seconds", 5.0),
            frame_timestamps=(
                tuple(frame_timestamps)
                if isinstance(frame_timestamps, (list, tuple))
                else frame_timestamps
            ),
        )
        proxy = ProxyConfig(
            url=_env_str(
                "CRAWLER_PROXY_URL", raw.get("proxy", {}).get("url", "")
            )
        )
        mcp_raw = raw.get("mcp", {})
        allowed_hosts = mcp_raw.get("allowed_hosts", McpConfig().allowed_hosts)
        allowed_origins = mcp_raw.get("allowed_origins", ())
        mcp = McpConfig(
            enabled=mcp_raw.get("enabled", True),
            allowed_hosts=(
                tuple(allowed_hosts)
                if isinstance(allowed_hosts, (list, tuple))
                else allowed_hosts
            ),
            allowed_origins=(
                tuple(allowed_origins)
                if isinstance(allowed_origins, (list, tuple))
                else allowed_origins
            ),
            inline_object_limit_bytes=mcp_raw.get(
                "inline_object_limit_bytes", 10 * 1024 * 1024
            ),
            inline_object_hard_limit_bytes=mcp_raw.get(
                "inline_object_hard_limit_bytes", 50 * 1024 * 1024
            ),
            presigned_expiry_minutes=mcp_raw.get("presigned_expiry_minutes", 15),
        )
        parser_raw = raw.get("parser_configuration", {})
        parser_configuration = ParserConfigurationConfig(
            sample_bucket=parser_raw.get(
                "sample_bucket", "crawler-parser-samples"
            ),
            sample_max_response_bytes=parser_raw.get(
                "sample_max_response_bytes", 10 * 1024 * 1024
            ),
            json_max_depth=parser_raw.get("json_max_depth", 64),
            json_max_nodes=parser_raw.get("json_max_nodes", 100_000),
            ai_max_bytes=parser_raw.get("ai_max_bytes", 256 * 1024),
            ai_max_array_items=parser_raw.get("ai_max_array_items", 20),
            sample_global_limit_per_minute=parser_raw.get(
                "sample_global_limit_per_minute", 30
            ),
            sample_action_limit_per_minute=parser_raw.get(
                "sample_action_limit_per_minute", 5
            ),
            assist_global_limit_per_minute=parser_raw.get(
                "assist_global_limit_per_minute", 10
            ),
            assist_action_limit_per_minute=parser_raw.get(
                "assist_action_limit_per_minute", 2
            ),
            assist_receipt_ttl_seconds=parser_raw.get(
                "assist_receipt_ttl_seconds", 900
            ),
            preview_max_records=parser_raw.get("preview_max_records", 20),
            preview_max_errors=parser_raw.get("preview_max_errors", 200),
            object_sse_enabled=parser_raw.get("object_sse_enabled", False),
            sample_hmac_key=os.environ.get("CRAWLER_PARSER_SAMPLE_HMAC_KEY", ""),
            sample_hmac_key_version=os.environ.get(
                "CRAWLER_PARSER_SAMPLE_HMAC_KEY_VERSION", "v1"
            ),
            assist_receipt_key=os.environ.get(
                "CRAWLER_PARSER_ASSIST_RECEIPT_KEY", ""
            ),
        )

        return cls(
            rpc_token=rpc_token,
            postgresql=pg,
            redis=rd,
            minio=minio,
            web=web,
            llm=llm,
            analysis_video=analysis_video,
            runtime=runtime,
            rpc=rpc,
            proxy=proxy,
            mcp=mcp,
            parser_configuration=parser_configuration,
        )

    def validate(self) -> None:
        """启动时校验配置合法性。"""
        errors: list[str] = []
        runtime_positive_fields = (
            "poll_interval_ms",
            "default_loop_interval_seconds",
            "batch_size",
            "graceful_shutdown_seconds",
        )
        for name in runtime_positive_fields:
            value = getattr(self.runtime, name)
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"scheduler.{name} must be an integer")
            elif value <= 0:
                errors.append(f"scheduler.{name} must be > 0")
        zombie_reap = self.runtime.zombie_reap_after_seconds
        if isinstance(zombie_reap, bool) or not isinstance(zombie_reap, int):
            errors.append("scheduler.zombie_reap_after_seconds must be an integer")
        elif zombie_reap < MIN_ZOMBIE_REAP_SECONDS:
            errors.append(
                "scheduler.zombie_reap_after_seconds must be >= "
                f"{MIN_ZOMBIE_REAP_SECONDS}"
            )
        if not _is_http_url(self.rpc.base_url):
            errors.append("scheduler.rpc.base_url must be a valid http(s) URL")
        if isinstance(self.rpc.timeout_seconds, bool) or not isinstance(
            self.rpc.timeout_seconds, int
        ):
            errors.append("scheduler.rpc.timeout_seconds must be an integer")
        elif self.rpc.timeout_seconds <= 0:
            errors.append("scheduler.rpc.timeout_seconds must be > 0")
        if self.proxy.url and not _is_http_url(self.proxy.url):
            errors.append("proxy.url must be a valid http(s) URL")
        if self.web.mode not in {"release", "debugger"}:
            errors.append("web.mode must be 'release' or 'debugger'")
        llm_string_fields = (
            "format",
            "model",
            "api_key",
            "base_url",
            "request_path",
        )
        for name in llm_string_fields:
            if not isinstance(getattr(self.llm, name), str):
                errors.append(f"llm.{name} must be a string")
        if isinstance(self.llm.model, str) and not self.llm.model:
            errors.append("llm.model must be non-empty")
        if (
            isinstance(self.llm.format, str)
            and self.llm.format
            not in {
                "openai",
                "anthropic",
                "openai-completion",
                "openai-responses",
                "claude",
                "gemini",
                "deepseek",
            }
        ):
            errors.append("llm.format must be a supported provider format")
        if (
            isinstance(self.llm.request_path, str)
            and self.llm.request_path not in {"chat", "responses"}
        ):
            errors.append("llm.request_path must be 'chat' or 'responses'")
        if isinstance(self.llm.max_tokens, bool) or not isinstance(self.llm.max_tokens, int):
            errors.append("llm.max_tokens must be an integer")
        elif self.llm.max_tokens <= 0:
            errors.append("llm.max_tokens must be > 0")
        if isinstance(self.llm.temperature, bool) or not isinstance(
            self.llm.temperature, (int, float)
        ):
            errors.append("llm.temperature must be a number")
        elif self.llm.temperature < 0:
            errors.append("llm.temperature must be >= 0")
        if not isinstance(self.llm.enable_thinking, bool):
            errors.append("llm.enable_thinking must be a boolean")
        if not isinstance(self.analysis_video.is_base64, bool):
            errors.append("analysis.video.is_base64 must be a boolean")
        valid_sampling_strategies = {
            "interval",
            "count",
            "timestamps",
            "scene_guided",
        }
        if (
            not isinstance(self.analysis_video.frame_sampling_strategy, str)
            or self.analysis_video.frame_sampling_strategy
            not in valid_sampling_strategies
        ):
            errors.append(
                "analysis.video.frame_sampling_strategy must be one of "
                "interval, count, timestamps, scene_guided"
            )
        if (
            isinstance(self.analysis_video.max_frames, bool)
            or not isinstance(self.analysis_video.max_frames, int)
            or not 2 <= self.analysis_video.max_frames <= MAX_ANALYSIS_FRAMES
        ):
            errors.append(
                "analysis.video.max_frames must be an integer between 2 and "
                f"{MAX_ANALYSIS_FRAMES}"
            )
        interval = self.analysis_video.frame_interval_seconds
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not isfinite(interval)
            or interval < MIN_FRAME_INTERVAL_SECONDS
        ):
            errors.append(
                "analysis.video.frame_interval_seconds must be a finite number >= "
                f"{MIN_FRAME_INTERVAL_SECONDS}"
            )
        timestamps = self.analysis_video.frame_timestamps
        valid_timestamps = isinstance(timestamps, (list, tuple)) and all(
            not isinstance(timestamp, bool)
            and isinstance(timestamp, (int, float))
            and isfinite(timestamp)
            and timestamp >= 0
            for timestamp in timestamps
        )
        if not valid_timestamps:
            errors.append(
                "analysis.video.frame_timestamps must contain finite non-negative numbers"
            )
        elif (
            self.analysis_video.frame_sampling_strategy == "timestamps"
            and not timestamps
        ):
            errors.append(
                "analysis.video.frame_timestamps must not be empty for timestamps strategy"
            )
        if not isinstance(self.mcp.enabled, bool):
            errors.append("mcp.enabled must be a boolean")
        if not isinstance(self.mcp.allowed_hosts, (list, tuple)):
            errors.append("mcp.allowed_hosts must be a list or tuple of strings")
        elif not self.mcp.allowed_hosts:
            errors.append("mcp.allowed_hosts must not be empty")
        elif not all(
            isinstance(host, str) and host.strip() and host.strip() != "*"
            for host in self.mcp.allowed_hosts
        ):
            errors.append(
                "mcp.allowed_hosts must contain non-empty, non-wildcard strings"
            )
        if not isinstance(self.mcp.allowed_origins, (list, tuple)) or not all(
            isinstance(origin, str) for origin in self.mcp.allowed_origins
        ):
            errors.append("mcp.allowed_origins must be a list or tuple of strings")
        if isinstance(self.mcp.inline_object_limit_bytes, bool) or not isinstance(
            self.mcp.inline_object_limit_bytes, int
        ):
            errors.append("mcp.inline_object_limit_bytes must be an integer")
        elif self.mcp.inline_object_limit_bytes <= 0:
            errors.append("mcp.inline_object_limit_bytes must be > 0")
        if isinstance(self.mcp.inline_object_hard_limit_bytes, bool) or not isinstance(
            self.mcp.inline_object_hard_limit_bytes, int
        ):
            errors.append("mcp.inline_object_hard_limit_bytes must be an integer")
        elif self.mcp.inline_object_hard_limit_bytes <= 0:
            errors.append("mcp.inline_object_hard_limit_bytes must be > 0")
        elif self.mcp.inline_object_hard_limit_bytes > _MAX_INLINE_OBJECT_HARD_LIMIT_BYTES:
            errors.append(
                "mcp.inline_object_hard_limit_bytes must not exceed 50 MiB"
            )
        elif (
            isinstance(self.mcp.inline_object_limit_bytes, int)
            and not isinstance(self.mcp.inline_object_limit_bytes, bool)
            and self.mcp.inline_object_limit_bytes
            > self.mcp.inline_object_hard_limit_bytes
        ):
            errors.append(
                "mcp.inline_object_limit_bytes must not exceed "
                "mcp.inline_object_hard_limit_bytes"
            )
        if isinstance(self.mcp.presigned_expiry_minutes, bool) or not isinstance(
            self.mcp.presigned_expiry_minutes, int
        ):
            errors.append("mcp.presigned_expiry_minutes must be an integer")
        elif not 1 <= self.mcp.presigned_expiry_minutes <= 60:
            errors.append("mcp.presigned_expiry_minutes must be between 1 and 60")
        parser_config = self.parser_configuration
        if (
            not isinstance(parser_config.sample_bucket, str)
            or not parser_config.sample_bucket.strip()
        ):
            errors.append("parser_configuration.sample_bucket must be non-empty")
        parser_positive_fields = (
            "sample_max_response_bytes",
            "json_max_depth",
            "json_max_nodes",
            "ai_max_bytes",
            "ai_max_array_items",
            "sample_global_limit_per_minute",
            "sample_action_limit_per_minute",
            "assist_global_limit_per_minute",
            "assist_action_limit_per_minute",
            "assist_receipt_ttl_seconds",
            "preview_max_records",
            "preview_max_errors",
        )
        for name in parser_positive_fields:
            value = getattr(parser_config, name)
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"parser_configuration.{name} must be an integer")
            elif value <= 0:
                errors.append(f"parser_configuration.{name} must be > 0")
        if (
            isinstance(parser_config.ai_max_bytes, int)
            and not isinstance(parser_config.ai_max_bytes, bool)
            and isinstance(parser_config.sample_max_response_bytes, int)
            and not isinstance(parser_config.sample_max_response_bytes, bool)
            and parser_config.ai_max_bytes
            > parser_config.sample_max_response_bytes
        ):
            errors.append(
                "parser_configuration.ai_max_bytes must not exceed "
                "parser_configuration.sample_max_response_bytes"
            )
        if (
            not isinstance(parser_config.sample_hmac_key_version, str)
            or not parser_config.sample_hmac_key_version.strip()
        ):
            errors.append(
                "parser_configuration.sample_hmac_key_version must be non-empty"
            )
        if not isinstance(parser_config.object_sse_enabled, bool):
            errors.append("parser_configuration.object_sse_enabled must be a boolean")
        if not self.redis.host:
            errors.append("redis.host is required")
        if not self.postgresql.username:
            errors.append("postgresql.username is required")
        if not self.postgresql.database:
            errors.append("postgresql.database is required")
        if not self.postgresql.password:
            errors.append(
                "postgresql.password is required "
                "(set via config.toml or CRAWLER_PG_PASSWORD env var)"
            )
        if errors:
            raise ValueError("Config validation failed:\n  " + "\n  ".join(errors))


def _is_http_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False
