"""旧 LLM runtime 配置迁移及目录引用检查。"""
from __future__ import annotations

import inspect
import json
import hashlib

from sqlalchemy import select, text

from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol
from runtime_config.models import LlmSettings
from runtime_config.store import LEGACY_LLM_REQUEST_PATH_KEY, LLM_KEY

LLM_MIGRATION_MARKER_KEY = "runtime:config:llm:model-catalog-migrated"
_MIGRATION_ADVISORY_KEY = 734812905


def _advisory_lock_sql() -> str:
    return f"SELECT pg_advisory_xact_lock({_MIGRATION_ADVISORY_KEY})"


def _task_reference_sql() -> str:
    return (
        "SELECT 1 FROM public.t_crawl_task "
        "WHERE config -> 'analysis' ->> 'llm_model_id' "
        "= ANY(CAST(:ids AS TEXT[])) LIMIT 1"
    )


async def _acquire_migration_lock(session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text(_advisory_lock_sql()))


def _legacy_provider_name(
    protocol: ProviderProtocol, prefix: str, base_url: str | None, api_key: str
) -> str:
    payload = "\0".join((protocol.value, prefix, base_url or "", api_key))
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"Legacy runtime {digest}"


def _legacy_mapping(
    format_name: str, request_path: str = "chat"
) -> ProviderProtocol:
    normalized = format_name.lower()
    if normalized == "openai" and request_path == "responses":
        return ProviderProtocol.OPENAI_RESPONSES
    aliases = {
        "openai": ProviderProtocol.OPENAI_COMPLETION,
        "anthropic": ProviderProtocol.CLAUDE,
        "openai-completion": ProviderProtocol.OPENAI_COMPLETION,
        "openai-responses": ProviderProtocol.OPENAI_RESPONSES,
        "claude": ProviderProtocol.CLAUDE,
        "gemini": ProviderProtocol.GEMINI,
        "deepseek": ProviderProtocol.DEEPSEEK,
    }
    return aliases.get(normalized, ProviderProtocol.OPENAI_COMPLETION)


async def migrate_legacy_llm_settings(db, redis, legacy_seed=None) -> None:
    if await redis.astrget(LLM_MIGRATION_MARKER_KEY) is not None:
        if await redis.astrget(LEGACY_LLM_REQUEST_PATH_KEY) is None:
            seed = getattr(legacy_seed, "values", {})
            request_path = seed.get("request_path", "chat")
            if request_path not in {"chat", "responses"}:
                request_path = "chat"
            await redis.astrset(
                LEGACY_LLM_REQUEST_PATH_KEY, request_path, nx=True
            )
        return
    raw = await redis.astrget(LLM_KEY)
    if raw is None:
        values = getattr(legacy_seed, "values", None)
        if values is None:
            await redis.astrset(LLM_KEY, LlmSettings().model_dump_json())
            await redis.astrset(LEGACY_LLM_REQUEST_PATH_KEY, "chat")
            await redis.astrset(LLM_MIGRATION_MARKER_KEY, "1")
            return
        legacy = dict(values)
    else:
        try:
            current = LlmSettings.model_validate_json(raw)
        except Exception:
            legacy = json.loads(raw)
        else:
            if await redis.astrget(LEGACY_LLM_REQUEST_PATH_KEY) is None:
                seed = getattr(legacy_seed, "values", {})
                request_path = seed.get("request_path", "chat")
                if request_path not in {"chat", "responses"}:
                    request_path = "chat"
                await redis.astrset(LEGACY_LLM_REQUEST_PATH_KEY, request_path)
            await redis.astrset(LLM_MIGRATION_MARKER_KEY, "1")
            return

    protocol = _legacy_mapping(
        str(legacy.get("format", "openai")),
        str(legacy.get("request_path", "chat")),
    )
    prefix = protocol.litellm_prefix
    async with db.asession_scope() as session:
        await _acquire_migration_lock(session)
        legacy_key = str(legacy.get("api_key", ""))
        candidates = list(await session.scalars(select(LlmProvider).where(
            LlmProvider.litellm_prefix == prefix,
            LlmProvider.protocol == protocol,
        )))
        base_url = legacy.get("base_url") or None
        endpoint_candidates = [
            item for item in candidates if item.base_url == base_url
        ]
        provider = next(
            (
                item
                for item in endpoint_candidates
                if item.api_key == legacy_key
            ),
            None,
        )
        if provider is None:
            provider = next(
                (item for item in endpoint_candidates if not item.api_key),
                None,
            )
        if provider is None:
            provider = LlmProvider(
                name=_legacy_provider_name(protocol, prefix, base_url, legacy_key),
                litellm_prefix=prefix, protocol=protocol,
                base_url=base_url,
                api_key=legacy_key,
            )
            session.add(provider)
            await session.flush()
        elif not provider.api_key and legacy_key:
            provider.api_key = legacy_key
        remote_model_id = str(legacy.get("model") or "gpt-4o")
        model = (await session.scalars(select(LlmModel).where(
            LlmModel.provider_id == provider.id,
            LlmModel.remote_model_id == remote_model_id,
        ))).one_or_none()
        if model is None:
            model = LlmModel(
                provider_id=provider.id, remote_model_id=remote_model_id,
                litellm_model=f"{provider.litellm_prefix}/{remote_model_id}",
                display_name=remote_model_id,
            )
            session.add(model)
            await session.flush()
        model_id = model.id

    settings = LlmSettings(
        default_analysis_model_id=model_id,
        max_tokens=legacy.get("max_tokens", 8192),
        temperature=legacy.get("temperature", 0.0),
        enable_thinking=legacy.get("enable_thinking", False),
    )
    request_path = legacy.get("request_path", "chat")
    if request_path not in {"chat", "responses"}:
        request_path = "chat"
    await redis.astrset(LEGACY_LLM_REQUEST_PATH_KEY, request_path)
    await redis.astrset(LLM_KEY, settings.model_dump_json())
    await redis.astrset(LLM_MIGRATION_MARKER_KEY, "1")


class RuntimeConfigReferenceChecker:
    def __init__(self, db, redis, *, task_reference_checker=None):
        self._db = db
        self._redis = redis
        self._task_reference_checker = task_reference_checker or self._query_task_references

    async def _query_task_references(self, model_ids: list[int]) -> list[str]:
        if not model_ids:
            return []
        async with self._db.asession_scope() as session:
            result = await session.execute(
                text(_task_reference_sql()), {"ids": [str(item) for item in model_ids]}
            )
            return ["task.config.analysis.llm_model_id"] if result.first() else []

    async def list_references(self, provider_id: int) -> list[str]:
        async with self._db.asession_scope() as session:
            model_ids = list(await session.scalars(
                select(LlmModel.id).where(LlmModel.provider_id == provider_id)
            ))
        references: list[str] = []
        raw = await self._redis.astrget(LLM_KEY)
        if raw is not None:
            try:
                settings = LlmSettings.model_validate_json(raw)
            except Exception:
                settings = None
            if settings is not None:
                if settings.default_analysis_model_id in model_ids:
                    references.append("default_analysis_model_id")
                if settings.default_transcription_model_id in model_ids:
                    references.append("default_transcription_model_id")
        task_refs = self._task_reference_checker(model_ids)
        if inspect.isawaitable(task_refs):
            task_refs = await task_refs
        references.extend(task_refs)
        return references
