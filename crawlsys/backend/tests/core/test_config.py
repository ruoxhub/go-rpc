import os
import textwrap
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from core.config import (
    AnalysisVideoConfig,
    LlmConfig,
    ParserConfigurationConfig,
    ProxyConfig,
    RpcConfig,
    SchedulerConfig,
    SchedulerRuntimeConfig,
    WebConfig,
)


def _write_toml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".toml")
    Path(path).write_text(content, encoding="utf-8")
    os.close(fd)
    return path


FULL_TOML = textwrap.dedent("""\
    [postgresql]
    username = "u"
    password = "p"
    host = "h"
    port = 5432
    database = "d"

    [redis]
    username = ""
    password = "rp"
    host = "rh"
    port = 6379

    [scheduler]
    worker_id = "worker-01"
    poll_interval_ms = 2000
    default_loop_interval_seconds = 7200
    batch_size = 25
    zombie_reap_after_seconds = 123
    graceful_shutdown_seconds = 45

    [scheduler.rpc]
    base_url = "http://rpc:5612"
    timeout_seconds = 30

    [llm]
    model = "gpt-4.1"
    api_key = "file-key"
    base_url = "https://api.example.com/v1"
    request_path = "responses"
    max_tokens = 4096
    temperature = 0.5
    enable_thinking = true

    [analysis.video]
    is_base64 = true
    frame_sampling_strategy = "interval"
    max_frames = 12
    frame_interval_seconds = 2.5
    frame_timestamps = [0.0, 1.5, 4.0]

    [proxy]
    url = "https://proxy.example.com"
""")


def test_from_toml_parses_nested_runtime_sections():
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.runtime == SchedulerRuntimeConfig(
            worker_id="worker-01",
            poll_interval_ms=2000,
            default_loop_interval_seconds=7200,
            batch_size=25,
            zombie_reap_after_seconds=123,
            graceful_shutdown_seconds=45,
        )
        assert cfg.rpc == RpcConfig(
            base_url="http://rpc:5612", timeout_seconds=30
        )
        assert cfg.proxy == ProxyConfig(url="https://proxy.example.com")
        assert cfg.analysis_video == AnalysisVideoConfig(
            is_base64=True,
            frame_sampling_strategy="interval",
            max_frames=12,
            frame_interval_seconds=2.5,
            frame_timestamps=(0.0, 1.5, 4.0),
        )
        assert cfg.worker_id == cfg.runtime.worker_id
        assert cfg.poll_interval_ms == cfg.runtime.poll_interval_ms
        assert cfg.poll_interval == cfg.runtime.poll_interval_ms / 1000
        assert (
            cfg.default_loop_interval_seconds
            == cfg.runtime.default_loop_interval_seconds
        )
        assert cfg.batch_size == cfg.runtime.batch_size
        assert (
            cfg.zombie_reap_after_seconds
            == cfg.runtime.zombie_reap_after_seconds
        )
        assert (
            cfg.graceful_shutdown_seconds
            == cfg.runtime.graceful_shutdown_seconds
        )
        assert cfg.rpc_base_url == cfg.rpc.base_url
        assert cfg.rpc_timeout == cfg.rpc.timeout_seconds
    finally:
        os.unlink(path)


def test_legacy_constructor_values_are_normalized_into_nested_config():
    cfg = SchedulerConfig(
        poll_interval=2.5,
        default_loop_interval_seconds=7200,
        zombie_reap_after_seconds=120,
        rpc_base_url="https://rpc.example.com",
        rpc_timeout=15,
    )

    assert cfg.runtime.poll_interval_ms == 2500
    assert cfg.runtime.default_loop_interval_seconds == 7200
    assert cfg.runtime.zombie_reap_after_seconds == 120
    assert cfg.rpc == RpcConfig(
        base_url="https://rpc.example.com", timeout_seconds=15
    )


def test_from_toml_parses_poll_interval():
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.poll_interval == 2.0
    finally:
        os.unlink(path)


def test_from_toml_parses_default_loop_interval():
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.default_loop_interval_seconds == 7200
    finally:
        os.unlink(path)


def test_from_toml_parses_rpc():
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.rpc_base_url == "http://rpc:5612"
        assert cfg.rpc_timeout == 30
    finally:
        os.unlink(path)


def test_from_toml_reads_token_from_env(monkeypatch):
    path = _write_toml(FULL_TOML)
    monkeypatch.setenv("SEKIRO_TOKEN", "my-secret")
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.rpc_token == "my-secret"
    finally:
        os.unlink(path)


def test_from_toml_defaults_when_sections_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    minimal = textwrap.dedent("""\
        [postgresql]
        username = "u"
        password = "p"
        host = "h"
        port = 5432
        database = "d"

        [redis]
        username = ""
        password = "rp"
        host = "rh"
        port = 6379
    """)
    path = _write_toml(minimal)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.poll_interval == 1.0
        assert cfg.default_loop_interval_seconds == 3600
        assert cfg.rpc_base_url == "http://localhost:5612"
        assert cfg.runtime == SchedulerRuntimeConfig(
            worker_id="scheduler-local-01",
            poll_interval_ms=1000,
            default_loop_interval_seconds=3600,
            batch_size=10,
            zombie_reap_after_seconds=600,
            graceful_shutdown_seconds=30,
        )
        assert cfg.rpc == RpcConfig(
            base_url="http://localhost:5612", timeout_seconds=60
        )
        assert cfg.proxy == ProxyConfig(url="")
        assert cfg.llm == LlmConfig()
        assert cfg.analysis_video == AnalysisVideoConfig()
    finally:
        os.unlink(path)


def test_from_toml_parses_web_mode_debugger():
    toml = FULL_TOML + textwrap.dedent("""\

        [web]
        mode = "debugger"
    """)
    path = _write_toml(toml)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.web.mode == "debugger"
        assert cfg.web.debugger is True
    finally:
        os.unlink(path)


def test_from_toml_parses_web_mode_release():
    toml = FULL_TOML + textwrap.dedent("""\

        [web]
        mode = "release"
        debugger = true
    """)
    path = _write_toml(toml)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.web.mode == "release"
        assert cfg.web.debugger is False
    finally:
        os.unlink(path)


def test_from_toml_keeps_legacy_web_debugger():
    toml = FULL_TOML + textwrap.dedent("""\

        [web]
        debugger = true
    """)
    path = _write_toml(toml)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.web.mode == "debugger"
        assert cfg.web.debugger is True
    finally:
        os.unlink(path)


def test_validate_rejects_invalid_web_mode():
    cfg = SchedulerConfig(web=WebConfig(mode="bad"))
    with pytest.raises(ValueError, match="web.mode"):
        cfg.validate()


def test_validate_passes_for_valid_config(monkeypatch):
    monkeypatch.delenv("CRAWLER_PG_PASSWORD", raising=False)
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        cfg.validate()  # 不应抛出异常
    finally:
        os.unlink(path)


@pytest.mark.parametrize("interval", [0, -1])
def test_validate_rejects_non_positive_default_loop_interval(interval):
    cfg = SchedulerConfig(default_loop_interval_seconds=interval)
    with pytest.raises(ValueError, match="default_loop_interval_seconds must be > 0"):
        cfg.validate()


@pytest.mark.parametrize("interval", [29, 0, -1])
def test_validate_rejects_too_short_zombie_reap_after_seconds(interval):
    cfg = SchedulerConfig(zombie_reap_after_seconds=interval)
    with pytest.raises(ValueError, match="zombie_reap_after_seconds must be >= 30"):
        cfg.validate()


def test_validate_accepts_minimum_zombie_reap_after_seconds():
    path = _write_toml(FULL_TOML.replace(
        "zombie_reap_after_seconds = 123",
        "zombie_reap_after_seconds = 30",
    ))
    try:
        SchedulerConfig.from_toml(path).validate()
    finally:
        os.unlink(path)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("poll_interval_ms", 0),
        ("default_loop_interval_seconds", 0),
        ("batch_size", 0),
        ("zombie_reap_after_seconds", 0),
        ("graceful_shutdown_seconds", 0),
    ],
)
def test_validate_rejects_non_positive_runtime_values(field_name, value):
    runtime = SchedulerRuntimeConfig(**{field_name: value})
    with pytest.raises(ValueError, match=field_name):
        SchedulerConfig(runtime=runtime).validate()


@pytest.mark.parametrize("base_url", ["", "rpc:5612", "ftp://rpc:5612"])
def test_validate_rejects_invalid_nested_rpc_url(base_url):
    with pytest.raises(ValueError, match="rpc.base_url"):
        SchedulerConfig(rpc=RpcConfig(base_url=base_url)).validate()


def test_validate_rejects_malformed_rpc_url():
    with pytest.raises(ValueError, match="rpc.base_url"):
        SchedulerConfig(rpc=RpcConfig(base_url="http://[")).validate()


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_validate_rejects_non_positive_nested_rpc_timeout(timeout_seconds):
    with pytest.raises(ValueError, match="rpc.timeout_seconds"):
        SchedulerConfig(rpc=RpcConfig(timeout_seconds=timeout_seconds)).validate()


@pytest.mark.parametrize("value", [True, "10", 10.5])
@pytest.mark.parametrize(
    "field_name",
    [
        "poll_interval_ms",
        "default_loop_interval_seconds",
        "batch_size",
        "zombie_reap_after_seconds",
        "graceful_shutdown_seconds",
    ],
)
def test_validate_rejects_non_integer_runtime_values(field_name, value):
    runtime = SchedulerRuntimeConfig(**{field_name: value})
    with pytest.raises(ValueError, match=rf"scheduler\.{field_name}"):
        SchedulerConfig(runtime=runtime).validate()


@pytest.mark.parametrize("value", [True, "10", 10.5])
def test_validate_rejects_non_integer_rpc_timeout(value):
    with pytest.raises(ValueError, match=r"scheduler\.rpc\.timeout_seconds"):
        SchedulerConfig(rpc=RpcConfig(timeout_seconds=value)).validate()


@pytest.mark.parametrize("url", ["proxy:8080", "socks5://proxy:1080"])
def test_validate_rejects_invalid_proxy_url(url):
    with pytest.raises(ValueError, match="proxy.url"):
        SchedulerConfig(proxy=ProxyConfig(url=url)).validate()


def test_validate_allows_empty_proxy_url():
    path = _write_toml(FULL_TOML.replace(
        'url = "https://proxy.example.com"', 'url = ""'
    ))
    try:
        SchedulerConfig.from_toml(path).validate()
    finally:
        os.unlink(path)


def test_validate_raises_for_missing_username(monkeypatch):
    monkeypatch.delenv("CRAWLER_PG_PASSWORD", raising=False)
    bad = textwrap.dedent("""\
        [postgresql]
        username = ""
        password = "p"
        host = "h"
        port = 5432
        database = "d"

        [redis]
        username = ""
        password = "rp"
        host = "rh"
        port = 6379
    """)
    path = _write_toml(bad)
    try:
        cfg = SchedulerConfig.from_toml(path)
        with pytest.raises(ValueError, match="username"):
            cfg.validate()
    finally:
        os.unlink(path)


def test_validate_raises_for_missing_password(monkeypatch):
    monkeypatch.delenv("CRAWLER_PG_PASSWORD", raising=False)
    bad = textwrap.dedent("""\
        [postgresql]
        username = "u"
        password = ""
        host = "h"
        port = 5432
        database = "d"

        [redis]
        username = ""
        password = "rp"
        host = "rh"
        port = 6379
    """)
    path = _write_toml(bad)
    try:
        cfg = SchedulerConfig.from_toml(path)
        with pytest.raises(ValueError, match="password"):
            cfg.validate()
    finally:
        os.unlink(path)


def test_env_var_overrides_pg_password(monkeypatch):
    path = _write_toml(FULL_TOML)
    monkeypatch.setenv("CRAWLER_PG_PASSWORD", "env-secret")
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.postgresql.password == "env-secret"
    finally:
        os.unlink(path)


def test_env_var_overrides_redis_password(monkeypatch):
    path = _write_toml(FULL_TOML)
    monkeypatch.setenv("CRAWLER_REDIS_PASSWORD", "env-redis-secret")
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.redis.password == "env-redis-secret"
    finally:
        os.unlink(path)


def test_toml_password_used_when_env_not_set(monkeypatch):
    monkeypatch.delenv("CRAWLER_PG_PASSWORD", raising=False)
    monkeypatch.delenv("CRAWLER_REDIS_PASSWORD", raising=False)
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.postgresql.password == "p"
        assert cfg.redis.password == "rp"
    finally:
        os.unlink(path)


def test_deployment_environment_overrides_file(monkeypatch):
    monkeypatch.delenv("CRAWLER_PG_PASSWORD", raising=False)
    values = {
        "CRAWLER_PG_USERNAME": "docker-user",
        "CRAWLER_PG_HOST": "postgres",
        "CRAWLER_PG_PORT": "5544",
        "CRAWLER_PG_DATABASE": "docker-db",
        "CRAWLER_REDIS_HOST": "redis",
        "CRAWLER_REDIS_PORT": "6380",
        "CRAWLER_MINIO_USERNAME": "minio-user",
        "CRAWLER_MINIO_HOST": "host.docker.internal",
        "CRAWLER_MINIO_PORT": "19000",
        "CRAWLER_MINIO_SECURE": "true",
        "CRAWLER_RPC_BASE_URL": "http://host.docker.internal:5612",
        "CRAWLER_RPC_TIMEOUT_SECONDS": "75",
        "CRAWLER_PROXY_URL": "http://host.docker.internal:17890",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert vars(cfg.postgresql) == {
            "username": "docker-user",
            "password": "p",
            "host": "postgres",
            "port": 5544,
            "database": "docker-db",
        }
        assert cfg.redis.host == "redis"
        assert cfg.redis.port == 6380
        assert cfg.minio.username == "minio-user"
        assert cfg.minio.host == "host.docker.internal"
        assert cfg.minio.port == 19000
        assert cfg.minio.secure is True
        assert cfg.rpc == RpcConfig(
            base_url="http://host.docker.internal:5612",
            timeout_seconds=75,
        )
        assert cfg.proxy == ProxyConfig(url="http://host.docker.internal:17890")
    finally:
        os.unlink(path)


@pytest.mark.parametrize(
    "name",
    [
        "CRAWLER_PG_PORT",
        "CRAWLER_REDIS_PORT",
        "CRAWLER_MINIO_PORT",
        "CRAWLER_RPC_TIMEOUT_SECONDS",
    ],
)
def test_integer_environment_values_reject_non_integer(monkeypatch, name):
    monkeypatch.setenv(name, "not-an-integer")
    path = _write_toml(FULL_TOML)
    try:
        with pytest.raises(ValueError, match=rf"^{name} must be an integer$"):
            SchedulerConfig.from_toml(path)
    finally:
        os.unlink(path)


def test_docker_config_is_secret_free_and_release_ready(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "config.docker.toml"
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    assert raw["postgresql"]["password"] == ""
    assert raw["redis"]["password"] == ""
    assert raw["minio"]["password"] == ""
    assert raw["llm"]["api_key"] == ""
    assert raw["postgresql"]["host"] == "postgres"
    assert raw["redis"]["host"] == "redis"

    for name in (
        "CRAWLER_PG_USERNAME",
        "CRAWLER_PG_HOST",
        "CRAWLER_PG_PORT",
        "CRAWLER_PG_DATABASE",
        "CRAWLER_REDIS_HOST",
        "CRAWLER_REDIS_PORT",
        "CRAWLER_RPC_BASE_URL",
        "CRAWLER_RPC_TIMEOUT_SECONDS",
        "CRAWLER_MINIO_USERNAME",
        "CRAWLER_MINIO_HOST",
        "CRAWLER_MINIO_PORT",
        "CRAWLER_MINIO_SECURE",
        "CRAWLER_PROXY_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CRAWLER_PG_PASSWORD", "test-postgres-password")
    cfg = SchedulerConfig.from_toml(str(path))
    cfg.validate()
    assert cfg.web == WebConfig(
        host="0.0.0.0", port=8081, mode="release", debugger=False
    )


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("0", False)])
def test_minio_secure_environment_parses_boolean(monkeypatch, raw, expected):
    monkeypatch.setenv("CRAWLER_MINIO_SECURE", raw)
    file_value = str(not expected).lower()
    path = _write_toml(FULL_TOML + f"\n[minio]\nsecure = {file_value}\n")
    try:
        assert SchedulerConfig.from_toml(path).minio.secure is expected
    finally:
        os.unlink(path)


def test_minio_secure_environment_rejects_unknown_boolean(monkeypatch):
    monkeypatch.setenv("CRAWLER_MINIO_SECURE", "sometimes")
    path = _write_toml(FULL_TOML)
    try:
        with pytest.raises(
            ValueError, match=r"^CRAWLER_MINIO_SECURE must be a boolean$"
        ):
            SchedulerConfig.from_toml(path)
    finally:
        os.unlink(path)


def test_from_toml_parses_zombie_reap_after_seconds():
    path = _write_toml(FULL_TOML)
    try:
        assert SchedulerConfig.from_toml(path).zombie_reap_after_seconds == 123
    finally:
        os.unlink(path)


def test_from_toml_parses_all_llm_fields(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.llm == LlmConfig(
            model="gpt-4.1",
            api_key="file-key",
            base_url="https://api.example.com/v1",
            request_path="responses",
            max_tokens=4096,
            temperature=0.5,
            enable_thinking=True,
        )
    finally:
        os.unlink(path)


def test_from_toml_parses_analysis_video():
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.analysis_video == AnalysisVideoConfig(
            is_base64=True,
            frame_sampling_strategy="interval",
            max_frames=12,
            frame_interval_seconds=2.5,
            frame_timestamps=(0.0, 1.5, 4.0),
        )
    finally:
        os.unlink(path)


@pytest.mark.parametrize(
    "format_name",
    [
        "openai",
        "anthropic",
        "openai-completion",
        "openai-responses",
        "claude",
        "gemini",
        "deepseek",
    ],
)
def test_validate_accepts_llm_provider_formats(format_name):
    path = _write_toml(
        FULL_TOML.replace("[llm]\n", f'[llm]\nformat = "{format_name}"\n')
    )
    try:
        SchedulerConfig.from_toml(path).validate()
    finally:
        os.unlink(path)


def test_validate_rejects_invalid_llm_format():
    cfg = SchedulerConfig(llm=LlmConfig(format="unknown"))
    with pytest.raises(ValueError, match=r"llm\.format"):
        cfg.validate()


def test_validate_rejects_non_boolean_analysis_video():
    cfg = SchedulerConfig(
        analysis_video=AnalysisVideoConfig(is_base64="true")  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match=r"analysis\.video\.is_base64"):
        cfg.validate()


@pytest.mark.parametrize(
    ("config", "field"),
    [
        (AnalysisVideoConfig(frame_sampling_strategy="unknown"), "frame_sampling_strategy"),
        (
            AnalysisVideoConfig(frame_sampling_strategy=["interval"]),  # type: ignore[arg-type]
            "frame_sampling_strategy",
        ),
        (AnalysisVideoConfig(max_frames=1), "max_frames"),
        (AnalysisVideoConfig(max_frames=True), "max_frames"),
        (AnalysisVideoConfig(max_frames=513), "max_frames"),
        (AnalysisVideoConfig(frame_interval_seconds=0.0), "frame_interval_seconds"),
        (
            AnalysisVideoConfig(frame_interval_seconds=0.0009),
            "frame_interval_seconds",
        ),
        (
            AnalysisVideoConfig(frame_interval_seconds=float("inf")),
            "frame_interval_seconds",
        ),
        (AnalysisVideoConfig(frame_interval_seconds=True), "frame_interval_seconds"),
        (AnalysisVideoConfig(frame_timestamps=(-1.0,)), "frame_timestamps"),
        (
            AnalysisVideoConfig(frame_timestamps=(float("nan"),)),
            "frame_timestamps",
        ),
        (AnalysisVideoConfig(frame_timestamps=(True,)), "frame_timestamps"),
        (
            AnalysisVideoConfig(
                frame_sampling_strategy="timestamps", frame_timestamps=()
            ),
            "frame_timestamps",
        ),
    ],
)
def test_validate_rejects_invalid_frame_sampling_config(config, field):
    with pytest.raises(ValueError, match=rf"analysis\.video\.{field}"):
        SchedulerConfig(analysis_video=config).validate()


def test_llm_environment_overrides_file(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example.com/v1")
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.llm.api_key == "env-key"
        assert cfg.llm.base_url == "https://env.example.com/v1"
    finally:
        os.unlink(path)


def test_empty_llm_environment_values_override_file(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    path = _write_toml(FULL_TOML)
    try:
        cfg = SchedulerConfig.from_toml(path)
        assert cfg.llm.api_key == ""
        assert cfg.llm.base_url == ""
    finally:
        os.unlink(path)


@pytest.mark.parametrize(
    ("llm", "message"),
    [
        (LlmConfig(model=""), "llm.model must be non-empty"),
        (LlmConfig(request_path="completions"), "llm.request_path"),
        (LlmConfig(max_tokens=0), "llm.max_tokens must be > 0"),
        (LlmConfig(temperature=-0.1), "llm.temperature must be >= 0"),
    ],
)
def test_validate_rejects_invalid_llm_semantics(llm, message):
    cfg = SchedulerConfig(llm=llm)
    with pytest.raises(ValueError, match=message):
        cfg.validate()


@pytest.mark.parametrize(
    ("field_name", "toml_value"),
    [
        ("model", "123"),
        ("format", "123"),
        ("api_key", "123"),
        ("base_url", "123"),
        ("request_path", "123"),
        ("max_tokens", "true"),
        ("temperature", "true"),
        ("enable_thinking", "1"),
    ],
)
def test_validate_reports_llm_type_errors(field_name, toml_value, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    toml = FULL_TOML + f"\n[llm.invalid]\nunused = true\n"
    original_values = {
        "model": '"gpt-4.1"',
        "format": '"openai"',
        "api_key": '"file-key"',
        "base_url": '"https://api.example.com/v1"',
        "request_path": '"responses"',
        "max_tokens": "4096",
        "temperature": "0.5",
        "enable_thinking": "true",
    }
    if field_name == "format":
        toml = toml.replace(
            "[llm]\n",
            f"[llm]\nformat = {toml_value}\n",
            1,
        )
    else:
        original = f"{field_name} = {original_values[field_name]}"
        toml = toml.replace(original, f"{field_name} = {toml_value}", 1)
    path = _write_toml(toml)
    try:
        cfg = SchedulerConfig.from_toml(path)
        with pytest.raises(ValueError, match=rf"llm\.{field_name}"):
            cfg.validate()
    finally:
        os.unlink(path)


def test_parser_configuration_uses_safe_defaults_and_env_secrets(monkeypatch):
    monkeypatch.setenv("CRAWLER_PARSER_SAMPLE_HMAC_KEY", "sample-key")
    monkeypatch.setenv("CRAWLER_PARSER_ASSIST_RECEIPT_KEY", "assist-key")
    monkeypatch.setenv("CRAWLER_PARSER_SAMPLE_HMAC_KEY_VERSION", "v2")
    path = _write_toml(FULL_TOML)
    try:
        config = SchedulerConfig.from_toml(path)
    finally:
        os.unlink(path)

    parser_config = config.parser_configuration
    assert parser_config.sample_max_response_bytes == 10 * 1024 * 1024
    assert parser_config.ai_max_bytes == 256 * 1024
    assert parser_config.sample_hmac_key == "sample-key"
    assert parser_config.sample_hmac_key_version == "v2"
    assert parser_config.assist_receipt_key == "assist-key"
    assert "sample-key" not in repr(parser_config)
    assert "assist-key" not in repr(parser_config)


def test_parser_configuration_reads_all_non_secret_toml_fields(monkeypatch):
    monkeypatch.delenv("CRAWLER_PARSER_SAMPLE_HMAC_KEY", raising=False)
    monkeypatch.delenv("CRAWLER_PARSER_ASSIST_RECEIPT_KEY", raising=False)
    monkeypatch.delenv("CRAWLER_PARSER_SAMPLE_HMAC_KEY_VERSION", raising=False)
    parser_toml = textwrap.dedent("""\

        [parser_configuration]
        sample_bucket = "custom-samples"
        sample_max_response_bytes = 1000
        json_max_depth = 10
        json_max_nodes = 2000
        ai_max_bytes = 500
        ai_max_array_items = 3
        sample_global_limit_per_minute = 4
        sample_action_limit_per_minute = 5
        assist_global_limit_per_minute = 6
        assist_action_limit_per_minute = 7
        assist_receipt_ttl_seconds = 8
        preview_max_records = 9
        preview_max_errors = 10
        object_sse_enabled = true
        sample_hmac_key = "toml-secret"
        sample_hmac_key_version = "toml-version"
        assist_receipt_key = "toml-receipt-secret"
    """)
    path = _write_toml(FULL_TOML + parser_toml)
    try:
        parser_config = SchedulerConfig.from_toml(path).parser_configuration
    finally:
        os.unlink(path)

    assert parser_config == ParserConfigurationConfig(
        sample_bucket="custom-samples",
        sample_max_response_bytes=1000,
        json_max_depth=10,
        json_max_nodes=2000,
        ai_max_bytes=500,
        ai_max_array_items=3,
        sample_global_limit_per_minute=4,
        sample_action_limit_per_minute=5,
        assist_global_limit_per_minute=6,
        assist_action_limit_per_minute=7,
        assist_receipt_ttl_seconds=8,
        preview_max_records=9,
        preview_max_errors=10,
        object_sse_enabled=True,
    )


@pytest.mark.parametrize(
    "field_name",
    [
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
    ],
)
def test_validate_rejects_non_positive_parser_limits(field_name):
    parser_config = replace(ParserConfigurationConfig(), **{field_name: 0})
    with pytest.raises(ValueError, match=rf"parser_configuration\.{field_name}"):
        SchedulerConfig(parser_configuration=parser_config).validate()


@pytest.mark.parametrize(
    ("parser_config", "field_name"),
    [
        (ParserConfigurationConfig(sample_bucket=""), "sample_bucket"),
        (
            ParserConfigurationConfig(
                sample_max_response_bytes=100,
                ai_max_bytes=101,
            ),
            "ai_max_bytes",
        ),
        (
            ParserConfigurationConfig(sample_hmac_key_version=""),
            "sample_hmac_key_version",
        ),
        (
            ParserConfigurationConfig(object_sse_enabled="true"),  # type: ignore[arg-type]
            "object_sse_enabled",
        ),
    ],
)
def test_validate_rejects_invalid_parser_configuration(parser_config, field_name):
    with pytest.raises(ValueError, match=rf"parser_configuration\.{field_name}"):
        SchedulerConfig(parser_configuration=parser_config).validate()


@pytest.mark.parametrize("invalid_value", [True, 1.5, "10"])
def test_validate_rejects_non_integer_parser_limit(invalid_value):
    parser_config = replace(
        ParserConfigurationConfig(), sample_max_response_bytes=invalid_value
    )
    with pytest.raises(
        ValueError, match=r"parser_configuration\.sample_max_response_bytes"
    ):
        SchedulerConfig(parser_configuration=parser_config).validate()


@pytest.mark.parametrize(
    ("web_mode", "minio_secure", "object_sse_enabled", "expected"),
    [
        ("debugger", False, False, True),
        ("release", False, True, False),
        ("release", True, False, False),
        ("release", True, True, True),
    ],
)
def test_parser_configuration_storage_ready(
    web_mode, minio_secure, object_sse_enabled, expected
):
    parser_config = ParserConfigurationConfig(
        object_sse_enabled=object_sse_enabled
    )
    assert (
        parser_config.storage_ready(
            web_mode=web_mode, minio_secure=minio_secure
        )
        is expected
    )
