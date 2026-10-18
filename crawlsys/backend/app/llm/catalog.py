"""LLM 提供商与模型目录的持久化操作。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from models.llm_provider import LlmModel, LlmProvider, ProviderProtocol
from storage.sql import SQLAlchemyDB
from storage.exceptions import AlreadyExistsError

# 唯一约束冲突：sqlite/直接 flush 时是 IntegrityError，经过
# asession_scope -> convert_sql_error 包装后是 AlreadyExistsError。
_DUPLICATE_ERRORS = (IntegrityError, AlreadyExistsError)


@dataclass(frozen=True)
class DiscoveredModel:
    """提供商远端发现的模型。"""

    remote_model_id: str
    display_name: str


@dataclass(frozen=True)
class SyncCounts:
    """同步计数；updated 是本次重新发现的既有模型数，而非字段变化数。"""

    created: int
    updated: int
    unavailable: int


class CatalogNotFoundError(LookupError):
    """请求的目录实体不存在。"""


class CatalogConflictError(RuntimeError):
    """目录实体仍被其他配置引用。"""


class CatalogReferenceChecker(Protocol):
    """隔离尚未落入当前 schema 的模型引用检查。"""

    async def list_references(self, provider_id: int) -> list[str]: ...


def _naive_utcnow() -> datetime:
    """t_llm_* 的时间列是 TIMESTAMP WITHOUT TIME ZONE，按 UTC 存 naive 值。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _is_duplicate_name(error: Exception) -> bool:
    """唯一约束冲突；session 会把 IntegrityError 包装成 AlreadyExistsError。"""
    if isinstance(error, _DUPLICATE_ERRORS):
        return True
    return isinstance(getattr(error, "original_error", None), IntegrityError)


class LlmCatalog:
    """LLM provider/model 目录 repository。"""

    def __init__(
        self,
        db: SQLAlchemyDB,
        *,
        reference_checker: CatalogReferenceChecker,
    ) -> None:
        self._db = db
        self._reference_checker = reference_checker

    async def get_provider(self, provider_id: int) -> LlmProvider | None:
        async with self._db.asession_scope() as session:
            return await session.get(LlmProvider, provider_id)

    async def require_provider(self, provider_id: int) -> LlmProvider:
        provider = await self.get_provider(provider_id)
        if provider is None:
            raise CatalogNotFoundError(f"LLM provider {provider_id} not found")
        return provider

    async def list_providers(self) -> list[LlmProvider]:
        async with self._db.asession_scope() as session:
            result = await session.scalars(select(LlmProvider).order_by(LlmProvider.id))
            return list(result)

    async def create_provider(self, **values: object) -> LlmProvider:
        try:
            async with self._db.asession_scope() as session:
                protocol = ProviderProtocol(values["protocol"])
                values["protocol"] = protocol
                values["litellm_prefix"] = protocol.litellm_prefix
                provider = LlmProvider(**values)
                session.add(provider)
                await session.flush()
                return provider
        except (IntegrityError, AlreadyExistsError) as error:
            if _is_duplicate_name(error):
                raise CatalogConflictError("LLM provider name already exists") from None
            raise

    async def update_provider(self, provider_id: int, **values: object) -> LlmProvider:
        provider: LlmProvider | None = None
        try:
            async with self._db.asession_scope() as session:
                provider = await session.get(LlmProvider, provider_id)
                if provider is not None:
                    if "protocol" in values:
                        protocol = ProviderProtocol(values["protocol"])
                        values["protocol"] = protocol
                        values["litellm_prefix"] = protocol.litellm_prefix
                        models = await session.scalars(
                            select(LlmModel).where(LlmModel.provider_id == provider_id)
                        )
                        for model in models:
                            model.litellm_model = (
                                f"{protocol.litellm_prefix}/{model.remote_model_id}"
                            )
                    for key, value in values.items():
                        setattr(provider, key, value)
                    await session.flush()
                    # updated_at 由数据库 now() 生成，flush 后仍是过期状态；
                    # 会话关闭后调用方再读会抛 DetachedInstanceError，这里先取回。
                    await session.refresh(provider)
        except (IntegrityError, AlreadyExistsError) as error:
            if _is_duplicate_name(error):
                raise CatalogConflictError("LLM provider name already exists") from None
            raise
        if provider is None:
            raise CatalogNotFoundError(f"LLM provider {provider_id} not found")
        return provider

    async def delete_provider(self, provider_id: int) -> None:
        async with self._db.asession_scope() as session:
            provider = (
                await session.scalars(
                    select(LlmProvider)
                    .where(LlmProvider.id == provider_id)
                    .with_for_update()
                )
            ).one_or_none()
            if provider is None:
                raise CatalogNotFoundError(f"LLM provider {provider_id} not found")
            references = await self._reference_checker.list_references(provider_id)
            if references:
                raise CatalogConflictError(
                    f"LLM provider {provider_id} is still referenced by: "
                    + ", ".join(references)
                )
            await session.execute(
                delete(LlmModel).where(LlmModel.provider_id == provider_id)
            )
            await session.delete(provider)

    @asynccontextmanager
    async def reference_guard(self, model_ids: list[int]):
        unique_ids = sorted(set(model_ids))
        if not unique_ids:
            yield
            return
        async with self._db.asession_scope() as session:
            result = await session.execute(
                select(LlmModel, LlmProvider)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(LlmModel.id.in_(unique_ids))
                .order_by(LlmProvider.id, LlmModel.id)
                .with_for_update()
            )
            rows = list(result.all())
            if len(rows) != len(unique_ids):
                raise CatalogNotFoundError("LLM model not found")
            if any(
                not model.enabled
                or not model.remote_available
                or not provider.enabled
                for model, provider in rows
            ):
                raise CatalogConflictError("LLM model is not usable")
            yield

    async def set_model_enabled(self, model_id: int, enabled: bool) -> LlmModel:
        model: LlmModel | None = None
        async with self._db.asession_scope() as session:
            model = await session.get(LlmModel, model_id)
            if model is not None:
                model.enabled = enabled
        if model is None:
            raise CatalogNotFoundError(f"LLM model {model_id} not found")
        return model

    async def get_model(
        self, model_id: int
    ) -> tuple[LlmModel, LlmProvider] | None:
        async with self._db.asession_scope() as session:
            result = await session.execute(
                select(LlmModel, LlmProvider)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(LlmModel.id == model_id)
            )
            return result.one_or_none()

    async def get_models(
        self, model_ids: list[int]
    ) -> dict[int, tuple[LlmModel, LlmProvider]]:
        unique_ids = set(model_ids)
        if not unique_ids:
            return {}
        async with self._db.asession_scope() as session:
            result = await session.execute(
                select(LlmModel, LlmProvider)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(LlmModel.id.in_(unique_ids))
            )
            return {model.id: (model, provider) for model, provider in result.all()}

    async def list_models(
        self, provider_id: int, usable_only: bool = False
    ) -> list[LlmModel]:
        statement = select(LlmModel).where(LlmModel.provider_id == provider_id)
        if usable_only:
            statement = statement.where(
                LlmModel.enabled.is_(True), LlmModel.remote_available.is_(True)
            )
        async with self._db.asession_scope() as session:
            result = await session.scalars(
                statement.order_by(LlmModel.remote_model_id, LlmModel.id)
            )
            return list(result)

    async def replace_discovered_models(
        self, provider_id: int, discovered_models: list[DiscoveredModel]
    ) -> SyncCounts:
        provider: LlmProvider | None = None
        counts = SyncCounts(created=0, updated=0, unavailable=0)
        async with self._db.asession_scope() as session:
            provider = (
                await session.scalars(
                    select(LlmProvider)
                    .where(LlmProvider.id == provider_id)
                    .with_for_update()
                )
            ).one_or_none()
            if provider is not None:
                result = await session.scalars(
                    select(LlmModel).where(LlmModel.provider_id == provider_id)
                )
                existing = {model.remote_model_id: model for model in result}
                discovered = {
                    model.remote_model_id: model for model in discovered_models
                }
                now = _naive_utcnow()
                created = 0
                updated = 0

                for remote_id, item in discovered.items():
                    model = existing.get(remote_id)
                    if model is None:
                        session.add(
                            LlmModel(
                                provider_id=provider_id,
                                remote_model_id=remote_id,
                                litellm_model=f"{provider.litellm_prefix}/{remote_id}",
                                display_name=item.display_name,
                                enabled=True,
                                remote_available=True,
                                last_discovered_at=now,
                            )
                        )
                        created += 1
                        continue
                    model.display_name = item.display_name
                    model.litellm_model = f"{provider.litellm_prefix}/{remote_id}"
                    model.remote_available = True
                    model.last_discovered_at = now
                    updated += 1

                unavailable = 0
                for remote_id, model in existing.items():
                    if remote_id not in discovered and model.remote_available:
                        model.remote_available = False
                        unavailable += 1

                provider.last_sync_status = "success"
                provider.last_sync_at = now
                provider.last_sync_error = None
                counts = SyncCounts(created, updated, unavailable)

        if provider is None:
            raise CatalogNotFoundError(f"LLM provider {provider_id} not found")
        return counts

    async def record_sync_success(self, provider_id: int) -> None:
        await self._record_sync(provider_id, status="success", error=None)

    async def record_sync_failure(self, provider_id: int, error: str) -> None:
        await self._record_sync(provider_id, status="failed", error=error)

    async def _record_sync(
        self, provider_id: int, *, status: str, error: str | None
    ) -> None:
        provider: LlmProvider | None = None
        async with self._db.asession_scope() as session:
            provider = await session.get(LlmProvider, provider_id)
            if provider is not None:
                provider.last_sync_status = status
                provider.last_sync_at = _naive_utcnow()
                provider.last_sync_error = error
        if provider is None:
            raise CatalogNotFoundError(f"LLM provider {provider_id} not found")

    async def ensure_provider_deletable(self, provider_id: int) -> None:
        await self.require_provider(provider_id)
        references = await self._reference_checker.list_references(provider_id)
        if references:
            joined = ", ".join(references)
            raise CatalogConflictError(
                f"LLM provider {provider_id} is still referenced by: {joined}"
            )
