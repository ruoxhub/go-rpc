"""Public, secret-free runtime settings schemas."""
from pydantic import BaseModel

from runtime_config.models import (
    AnalysisVideoSettings,
    CleanerSettings,
    LlmSettings,
    LlmSettingsUpdate,
    PlatformCleanerPolicy,
    ProxySettingsUpdate,
    RpcSettings,
    SchedulerSettings,
)


class LlmSettingsResponse(LlmSettings):
    pass


class ProxySettingsResponse(BaseModel):
    url_configured: bool
    target: str


class SchedulerSettingsResponse(SchedulerSettings):
    inactive_fields: list[str]


class CleanerSettingsResponse(CleanerSettings):
    inactive_fields: list[str]


class PlatformSettingsResponse(BaseModel):
    platform: str
    configured: bool
    policy: PlatformCleanerPolicy | None


class SettingsResponse(BaseModel):
    llm: LlmSettingsResponse
    scheduler: SchedulerSettingsResponse
    rpc: RpcSettings
    analysis_video: AnalysisVideoSettings
    proxy: ProxySettingsResponse
    cleaner: CleanerSettingsResponse
    platforms: list[PlatformSettingsResponse]


__all__ = [
    "AnalysisVideoSettings", "CleanerSettings", "LlmSettingsUpdate",
    "PlatformCleanerPolicy", "ProxySettingsUpdate", "RpcSettings",
    "SchedulerSettings", "LlmSettingsResponse", "ProxySettingsResponse",
    "CleanerSettingsResponse",
    "SchedulerSettingsResponse", "PlatformSettingsResponse", "SettingsResponse",
]
