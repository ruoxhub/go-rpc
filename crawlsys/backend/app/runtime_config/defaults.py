"""Compose runtime configuration defaults from startup configuration."""
from __future__ import annotations

import tomllib
from pathlib import Path

from core.config import SchedulerConfig

from .models import (
    AnalysisVideoSettings,
    CleanerSettings,
    FilterRule,
    GradeRuleModel,
    LlmSettings,
    PlatformCleanerPolicy,
    ProxySettings,
    RpcSettings,
    SchedulerSettings,
)
from .store import RuntimeConfigDefaults


class LegacyLlmSeed:
    """迁移专用旧配置快照，不对 runtime store 暴露。"""

    def __init__(self, **values):
        self.values = values


def build_runtime_config_defaults(
    config: SchedulerConfig, config_path: str | Path | None = None
) -> RuntimeConfigDefaults:
    raw: dict = {}
    if config_path is not None and Path(config_path).is_file():
        with Path(config_path).open("rb") as file:
            raw = tomllib.load(file)

    policies = {
        platform: PlatformCleanerPolicy(
            p1=[GradeRuleModel(**item) for item in values.get("p1", [])],
            p2=[GradeRuleModel(**item) for item in values.get("p2", [])],
            p3=[GradeRuleModel(**item) for item in values.get("p3", [])],
            filters=[FilterRule(**item) for item in values.get("filters", [])],
        )
        for platform, values in raw.get("grade", {}).items()
    }
    cleaner_raw = raw.get("cleaner", {})
    cleaner = CleanerSettings.model_validate({
        **cleaner_raw,
        "enabled": cleaner_raw.get("enabled", bool(policies)),
    })
    return RuntimeConfigDefaults(
        llm=LlmSettings(),
        legacy_llm=LegacyLlmSeed(**vars(config.llm)),
        scheduler=SchedulerSettings(**vars(config.runtime)),
        rpc=RpcSettings(**vars(config.rpc)),
        analysis_video=AnalysisVideoSettings(**vars(config.analysis_video)),
        proxy=ProxySettings(**vars(config.proxy)),
        cleaner=cleaner,
        platform_policies=policies,
    )
