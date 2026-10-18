"""MCP 适配层服务配置测试。"""

from pathlib import Path

import pytest

from core.config import McpConfig, SchedulerConfig


def test_mcp_config_defaults():
    config = McpConfig()

    assert config.enabled is True
    assert config.allowed_hosts == (
        "192.168.1.5",
        "192.168.1.5:*",
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
    )
    assert config.allowed_origins == ()
    assert config.inline_object_limit_bytes == 10 * 1024 * 1024
    assert config.inline_object_hard_limit_bytes == 50 * 1024 * 1024
    assert config.presigned_expiry_minutes == 15


def test_checked_in_config_allows_bare_and_port_qualified_internal_hosts():
    config_path = Path(__file__).parents[2] / "config.toml"

    config = SchedulerConfig.from_toml(str(config_path))

    assert config.mcp.allowed_hosts == (
        "192.168.1.5",
        "192.168.1.5:*",
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
    )


def test_from_toml_parses_mcp_config(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[mcp]
enabled = false
allowed_hosts = ["minio.internal", "localhost"]
allowed_origins = ["http://localhost:3000"]
inline_object_limit_bytes = 1048576
inline_object_hard_limit_bytes = 2097152
presigned_expiry_minutes = 30
""",
        encoding="utf-8",
    )

    config = SchedulerConfig.from_toml(str(path))

    assert config.mcp == McpConfig(
        enabled=False,
        allowed_hosts=("minio.internal", "localhost"),
        allowed_origins=("http://localhost:3000",),
        inline_object_limit_bytes=1048576,
        inline_object_hard_limit_bytes=2097152,
        presigned_expiry_minutes=30,
    )


def test_validate_rejects_empty_mcp_allowed_hosts():
    with pytest.raises(ValueError, match="mcp.allowed_hosts"):
        SchedulerConfig(mcp=McpConfig(allowed_hosts=())).validate()


def test_validate_rejects_wildcard_mcp_allowed_host():
    with pytest.raises(ValueError, match="mcp.allowed_hosts"):
        SchedulerConfig(mcp=McpConfig(allowed_hosts=("*",))).validate()


def test_validate_rejects_non_boolean_mcp_enabled():
    with pytest.raises(ValueError, match="mcp.enabled"):
        SchedulerConfig(mcp=McpConfig(enabled="false")).validate()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_hosts", "localhost"),
        ("allowed_hosts", ("localhost", 42)),
        ("allowed_origins", "https://client.example"),
        ("allowed_origins", ("https://client.example", 42)),
    ],
)
def test_validate_requires_mcp_host_and_origin_collections_of_strings(field, value):
    config_values = {field: value}

    with pytest.raises(ValueError, match=f"mcp.{field}"):
        SchedulerConfig(mcp=McpConfig(**config_values)).validate()


def test_validate_rejects_default_limit_above_hard_limit():
    with pytest.raises(ValueError, match="mcp.inline_object_limit_bytes"):
        SchedulerConfig(
            mcp=McpConfig(
                allowed_hosts=("localhost",),
                inline_object_limit_bytes=2,
                inline_object_hard_limit_bytes=1,
            )
        ).validate()


def test_validate_rejects_hard_inline_limit_above_service_cap():
    with pytest.raises(ValueError, match="mcp.inline_object_hard_limit_bytes"):
        SchedulerConfig(
            mcp=McpConfig(
                allowed_hosts=("localhost",),
                inline_object_limit_bytes=50 * 1024 * 1024,
                inline_object_hard_limit_bytes=50 * 1024 * 1024 + 1,
            )
        ).validate()


@pytest.mark.parametrize("expiry_minutes", [0, 61])
def test_validate_requires_presigned_expiry_between_one_and_sixty_minutes(
    expiry_minutes: int,
):
    with pytest.raises(ValueError, match="mcp.presigned_expiry_minutes"):
        SchedulerConfig(
            mcp=McpConfig(
                allowed_hosts=("localhost",),
                presigned_expiry_minutes=expiry_minutes,
            )
        ).validate()
