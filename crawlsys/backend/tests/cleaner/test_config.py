from pathlib import Path

import pytest

from cleaner.config import CleanerConfig
from cleaner.engine import GradeRule


ENABLED_TOML = """
[cleaner]
enabled = true
poll_interval = 60
batch_size = 100
max_batches_per_platform = 4
ttl_days = 14
watermark_key = "cleaner:test:watermark"
suspect_seconds = 90

[[grade.tiktok.p1]]
max_hours = 24
min_views = 8000

[[grade.tiktok.p1]]
max_hours = 72
min_views = 50000

[[grade.tiktok.p2]]
max_hours = 24
min_views = 5000

[[grade.tiktok.p3]]
max_hours = 168
min_views = 80000
"""


def test_from_toml_parses_cleaner_and_thresholds(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(ENABLED_TOML, encoding="utf-8")

    config = CleanerConfig.from_toml(str(path))

    assert config.enabled is True
    assert config.poll_interval == 60
    assert config.batch_size == 100
    assert config.max_batches_per_platform == 4
    assert config.ttl_days == 14
    assert config.watermark_key == "cleaner:test:watermark"
    assert config.suspect_seconds == 90
    assert config.platforms == ["tiktok"]
    assert config.thresholds["tiktok"].p1 == [
        GradeRule(24.0, 8000),
        GradeRule(72.0, 50000),
    ]


def test_missing_cleaner_section_is_disabled_for_compatibility(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[postgresql]\nusername = 'u'\n", encoding="utf-8")

    config = CleanerConfig.from_toml(str(path))

    assert config.enabled is False
    assert config.platforms == []
    config.validate()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("poll_interval", 0),
        ("batch_size", 0),
        ("max_batches_per_platform", 0),
        ("ttl_days", 0),
        ("suspect_seconds", 0),
    ],
)
def test_validate_rejects_non_positive_values(field_name, value):
    values = {
        "enabled": False,
        "poll_interval": 3600.0,
        "batch_size": 1000,
        "max_batches_per_platform": 10,
        "ttl_days": 14,
        "watermark_key": "cleaner:grade:watermark",
        "suspect_seconds": 120.0,
        "thresholds": {},
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        CleanerConfig(**values).validate()


def test_enabled_cleaner_requires_platform_rules():
    with pytest.raises(ValueError, match="at least one grade platform"):
        CleanerConfig(enabled=True).validate()


def test_each_platform_requires_at_least_one_rule():
    config = CleanerConfig.from_raw(
        {"enabled": True},
        {"tiktok": {"p1": [], "p2": [], "p3": []}},
    )

    with pytest.raises(ValueError, match="grade.tiktok"):
        config.validate()


def test_platforms_are_sorted_for_deterministic_cycles():
    config = CleanerConfig.from_raw(
        {"enabled": True},
        {
            "tiktok": {"p1": [{"max_hours": 24, "min_views": 8000}]},
            "bilibili": {"p3": [{"max_hours": 168, "min_views": 80000}]},
        },
    )

    assert config.platforms == ["bilibili", "tiktok"]
