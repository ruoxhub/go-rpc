"""Cleaner configuration parsed from config.toml."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from .engine import GradeRule, PlatformThresholds


def _parse_rules(raw_rules: list[dict[str, Any]]) -> list[GradeRule]:
    return [
        GradeRule(
            max_hours=float(item["max_hours"]),
            min_views=int(item["min_views"]),
        )
        for item in raw_rules
    ]


@dataclass(frozen=True)
class CleanerConfig:
    enabled: bool = True
    poll_interval: float = 3600.0
    batch_size: int = 1000
    max_batches_per_platform: int = 10
    ttl_days: int = 14
    watermark_key: str = "cleaner:grade:watermark"
    suspect_seconds: float = 120.0
    thresholds: dict[str, PlatformThresholds] = field(default_factory=dict)

    @property
    def platforms(self) -> list[str]:
        return sorted(self.thresholds)

    @classmethod
    def from_raw(
        cls,
        cleaner_raw: dict[str, Any],
        grade_raw: dict[str, Any],
    ) -> "CleanerConfig":
        thresholds = {
            platform: PlatformThresholds(
                p1=_parse_rules(platform_raw.get("p1", [])),
                p2=_parse_rules(platform_raw.get("p2", [])),
                p3=_parse_rules(platform_raw.get("p3", [])),
            )
            for platform, platform_raw in grade_raw.items()
        }
        return cls(
            enabled=bool(cleaner_raw.get("enabled", False)),
            poll_interval=float(cleaner_raw.get("poll_interval", 3600.0)),
            batch_size=int(cleaner_raw.get("batch_size", 1000)),
            max_batches_per_platform=int(
                cleaner_raw.get("max_batches_per_platform", 10)
            ),
            ttl_days=int(cleaner_raw.get("ttl_days", 14)),
            watermark_key=str(
                cleaner_raw.get("watermark_key", "cleaner:grade:watermark")
            ),
            suspect_seconds=float(cleaner_raw.get("suspect_seconds", 120.0)),
            thresholds=thresholds,
        )

    @classmethod
    def from_toml(cls, path: str) -> "CleanerConfig":
        with open(path, "rb") as file:
            raw = tomllib.load(file)
        return cls.from_raw(raw.get("cleaner", {}), raw.get("grade", {}))

    def validate(self) -> None:
        errors: list[str] = []
        for field_name in (
            "poll_interval",
            "batch_size",
            "max_batches_per_platform",
            "ttl_days",
            "suspect_seconds",
        ):
            if getattr(self, field_name) <= 0:
                errors.append(f"cleaner.{field_name} must be > 0")
        if not self.watermark_key:
            errors.append("cleaner.watermark_key is required")
        if self.enabled and not self.thresholds:
            errors.append("enabled cleaner requires at least one grade platform")
        for platform, thresholds in self.thresholds.items():
            rules = thresholds.p1 + thresholds.p2 + thresholds.p3
            if not rules:
                errors.append(f"grade.{platform} requires at least one rule")
            for rule in rules:
                if rule.max_hours <= 0:
                    errors.append(f"grade.{platform}.max_hours must be > 0")
                if rule.min_views < 0:
                    errors.append(f"grade.{platform}.min_views must be >= 0")
        if errors:
            raise ValueError("Cleaner config validation failed:\n  " + "\n  ".join(errors))
