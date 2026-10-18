"""Runtime settings endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from core.repository import PlatformRepo, TaskRepo
from llm.catalog import CatalogConflictError, CatalogNotFoundError
from models.platform import PlatformStatus
from storage.exceptions import RedisOperationError
from runtime_config.store import (
    RuntimeConfigReadError,
    RuntimeConfigStore,
    RuntimeConfigUpdateError,
    proxy_configured,
    summarize_proxy,
)
from api.deps import get_db, get_runtime_config_store
from api.deps import get_llm_catalog

from .schemas import (
    AnalysisVideoSettings,
    CleanerSettings,
    CleanerSettingsResponse,
    LlmSettingsResponse,
    LlmSettingsUpdate,
    PlatformCleanerPolicy,
    PlatformSettingsResponse,
    ProxySettingsResponse,
    ProxySettingsUpdate,
    RpcSettings,
    SchedulerSettings,
    SchedulerSettingsResponse,
    SettingsResponse,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])
_SCHEDULER_INACTIVE_FIELDS = ["worker_id", "batch_size", "graceful_shutdown_seconds"]
_CLEANER_INACTIVE_FIELDS = ["poll_interval", "watermark_key"]
_CONFIG_ERRORS = (
    RuntimeConfigReadError,
    RuntimeConfigUpdateError,
    RedisOperationError,
)


def get_platform_repo(db=Depends(get_db)) -> PlatformRepo:
    return PlatformRepo(db)


def get_task_repo(db=Depends(get_db)) -> TaskRepo:
    return TaskRepo(db)


def _llm(value) -> LlmSettingsResponse:
    return LlmSettingsResponse(**value.model_dump())


def _proxy(value) -> ProxySettingsResponse:
    return ProxySettingsResponse(
        url_configured=proxy_configured(value), target=summarize_proxy(value)
    )


def _scheduler(value) -> SchedulerSettingsResponse:
    return SchedulerSettingsResponse(**value.model_dump(), inactive_fields=_SCHEDULER_INACTIVE_FIELDS)


def _cleaner(value) -> CleanerSettingsResponse:
    return CleanerSettingsResponse(
        **value.model_dump(), inactive_fields=_CLEANER_INACTIVE_FIELDS
    )


async def _platforms(store, repo) -> list[PlatformSettingsResponse]:
    rows = await repo.find_all_active()
    result = []
    for row in rows:
        code = row.bs_platform_code
        if not code:
            continue
        policy = await store.get_platform_policy(code)
        result.append(PlatformSettingsResponse(
            platform=code, configured=policy is not None, policy=policy
        ))
    return result


@router.get("", response_model=SettingsResponse)
async def get_settings(
    store: RuntimeConfigStore = Depends(get_runtime_config_store),
    repo: PlatformRepo = Depends(get_platform_repo),
):
    try:
        return SettingsResponse(
            llm=_llm(await store.get_llm()),
            scheduler=_scheduler(await store.get_scheduler()),
            rpc=await store.get_rpc(),
            analysis_video=await store.get_analysis_video(),
            proxy=_proxy(await store.get_proxy()),
            cleaner=_cleaner(await store.get_cleaner()),
            platforms=await _platforms(store, repo),
        )
    except _CONFIG_ERRORS:
        raise HTTPException(503, "运行时配置服务暂不可用") from None


async def _safe_update(call, render=lambda value: value):
    try:
        return render(await call)
    except _CONFIG_ERRORS:
        raise HTTPException(503, "运行时配置服务暂不可用") from None


@router.put("/llm", response_model=LlmSettingsResponse)
async def put_llm(
    value: LlmSettingsUpdate,
    store=Depends(get_runtime_config_store),
    catalog=Depends(get_llm_catalog),
):
    model_ids = [
        model_id
        for field in ("default_analysis_model_id", "default_transcription_model_id")
        if field in value.model_fields_set
        for model_id in [getattr(value, field)]
        if model_id is not None
    ]
    try:
        async with catalog.reference_guard(model_ids):
            return await _safe_update(store.update_llm(value), _llm)
    except CatalogNotFoundError:
        raise HTTPException(422, "LLM model not found") from None
    except CatalogConflictError:
        raise HTTPException(409, "LLM model is not usable") from None


@router.put("/scheduler", response_model=SchedulerSettingsResponse)
async def put_scheduler(
    value: SchedulerSettings,
    store=Depends(get_runtime_config_store),
    repo: TaskRepo = Depends(get_task_repo),
):
    async def _persist_and_recompute():
        current = await store.get_scheduler()
        saved = await store.replace_scheduler(value)
        if saved.timezone != current.timezone:
            await repo.recompute_cron_schedules(
                timezone_name=saved.timezone, now=datetime.now(timezone.utc)
            )
        return saved

    return await _safe_update(_persist_and_recompute(), _scheduler)


@router.put("/scheduler/rpc", response_model=RpcSettings)
async def put_rpc(value: RpcSettings, store=Depends(get_runtime_config_store)):
    return await _safe_update(store.replace_rpc(value))


@router.put("/analysis/video", response_model=AnalysisVideoSettings)
async def put_video(value: AnalysisVideoSettings, store=Depends(get_runtime_config_store)):
    return await _safe_update(store.replace_analysis_video(value))


@router.put("/proxy", response_model=ProxySettingsResponse)
async def put_proxy(value: ProxySettingsUpdate, store=Depends(get_runtime_config_store)):
    return await _safe_update(store.update_proxy(value), _proxy)


@router.put("/cleaner", response_model=CleanerSettingsResponse)
async def put_cleaner(value: CleanerSettings, store=Depends(get_runtime_config_store)):
    return await _safe_update(store.replace_cleaner(value), _cleaner)


@router.put("/platforms/{platform}", response_model=PlatformSettingsResponse)
async def put_platform(
    platform: str,
    value: PlatformCleanerPolicy,
    store=Depends(get_runtime_config_store),
    repo: PlatformRepo = Depends(get_platform_repo),
):
    try:
        row = await repo.find_by_code(platform)
        if row is None or row.bs_status == PlatformStatus.DELETED:
            raise HTTPException(404, "平台不存在")
        policy = await store.replace_platform_policy(platform, value)
        return PlatformSettingsResponse(platform=platform, configured=True, policy=policy)
    except HTTPException:
        raise
    except _CONFIG_ERRORS:
        raise HTTPException(503, "运行时配置服务暂不可用") from None
