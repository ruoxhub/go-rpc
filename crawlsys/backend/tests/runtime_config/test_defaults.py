"""Runtime defaults composition tests."""
from core.config import SchedulerConfig
from runtime_config.defaults import build_runtime_config_defaults


def test_defaults_load_platform_policy_and_filters_from_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cleaner]
enabled = true

[grade.tiktok]
[[grade.tiktok.filters]]
field = "extend_data.aigcLabelType"
operator = ">"
value = 0
[[grade.tiktok.p1]]
max_hours = 24.0
min_views = 8000
""",
        encoding="utf-8",
    )

    defaults = build_runtime_config_defaults(SchedulerConfig(), path)

    assert defaults.platform_policies["tiktok"].p1[0].min_views == 8000
    assert defaults.platform_policies["tiktok"].filters[0].field == "extend_data.aigcLabelType"
    assert "thresholds" not in defaults.cleaner.model_dump()


def test_defaults_without_toml_remain_valid():
    defaults = build_runtime_config_defaults(SchedulerConfig())
    assert defaults.cleaner.enabled is False
    assert defaults.platform_policies == {}
    assert "thresholds" not in defaults.cleaner.model_dump()


def test_cleaner_toml_without_grade_has_no_global_thresholds(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[cleaner]
enabled = true
batch_size = 25
""",
        encoding="utf-8",
    )

    defaults = build_runtime_config_defaults(SchedulerConfig(), path)

    assert defaults.cleaner.enabled is True
    assert defaults.cleaner.batch_size == 25
    assert defaults.platform_policies == {}
    assert "thresholds" not in defaults.cleaner.model_dump()
