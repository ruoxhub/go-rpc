# -*- coding: utf-8 -*-
"""Asynchronous SQLAlchemy implementation."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
)

from sqlalchemy import (
    and_,
    delete,
    func,
    select,
    update,
    text,
    UniqueConstraint,
    exists as sql_exists,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ._base import (
    _BaseAlchemyHelper,
    Base,
    logger,
    convert_sql_error,
)

T = TypeVar("T")


def _resolve_upsert_index_elements(model_cls: type, unique_field: str) -> List[str]:
    """解析 ON CONFLICT 的真实冲突目标列。

    模型仅声明逻辑单列唯一键 ``unique_field``（供 pipeline 去重使用），
    但数据库中的实际唯一约束往往是复合键（如 ``(platform, content_id)``）。
    PostgreSQL 的 ``ON CONFLICT (col)`` 必须精确匹配某个唯一/排除约束，
    否则报 ``InvalidColumnReferenceError``（content_id 仅有非唯一索引即触发）。

    因此这里从表元数据中找出「包含 unique_field 的唯一约束/唯一索引」，
    以其全部列作为冲突目标；找不到时再尝试「platform + 某列」的复合唯一约束，
    最后才退化为 [unique_field]（保持旧行为，但仍可能触发约束错误）。
    """
    table = model_cls.__table__

    # 1) 唯一索引（Index(..., unique=True)）包含 unique_field
    for idx in table.indexes:
        if getattr(idx, "unique", False) and unique_field in {c.name for c in idx.columns}:
            return [c.name for c in idx.columns]
    # 2) 显式 UniqueConstraint 包含 unique_field
    for cons in table.constraints:
        if isinstance(cons, UniqueConstraint) and unique_field in {c.name for c in cons.columns}:
            return [c.name for c in cons.columns]
    # 3) 退化保护：unique_field 未直接出现在任何唯一约束中（如 user：
    #    真实唯一键为 (platform, username)），但存在 (platform, 某列) 复合唯一约束，
    #    此时使用该复合约束，避免 ON CONFLICT (unique_field) 因无对应约束而报错。
    for idx in table.indexes:
        cols = {c.name for c in idx.columns}
        if getattr(idx, "unique", False) and "platform" in cols and unique_field not in cols:
            return [c.name for c in idx.columns]
    for cons in table.constraints:
        cols = {c.name for c in cons.columns}
        if isinstance(cons, UniqueConstraint) and "platform" in cols and unique_field not in cols:
            return [c.name for c in cons.columns]

    return [unique_field]


def _build_non_null_upsert_set(model_cls: type, stmt: Any, set_cols: List[str]) -> Dict[str, Any]:
    return {
        c: func.coalesce(stmt.excluded[c], getattr(model_cls, c))
        for c in set_cols
    }


class AsyncSQLImpl:
    """Asynchronous SQLAlchemy implementation."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    @asynccontextmanager
    async def asession_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous session context manager."""
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Async transaction failed ({type(e).__name__})")
                # 只有 SQL 错误才转换；业务异常（如 CatalogConflictError）必须原样
                # 上抛，否则调用方会把 404/409 当作 503 返回。
                if isinstance(e, SQLAlchemyError):
                    raise convert_sql_error(e)
                raise

    # ------------------- Asynchronous CRUD -------------------
    async def aadd(self, obj: Any) -> None:
        """Add a single object asynchronously."""
        async with self.asession_scope() as s:
            s.add(obj)

    async def aadds(self, objs: List[Any]) -> None:
        """Batch add objects asynchronously."""
        async with self.asession_scope() as s:
            s.add_all(objs)

    async def aquery(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Query multiple records asynchronously."""
        async with self.asession_scope() as s:
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if order_by:
                stmt = stmt.order_by(
                    *_BaseAlchemyHelper.build_order(class_model, order_by)
                )
            if limit:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)
            result = await s.scalars(stmt)
            return list(result.all())

    async def aquery_one(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[T]:
        """Query a single record asynchronously."""
        async with self.asession_scope() as s:
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            result = await s.scalars(stmt)
            return result.first()

    async def acount(
        self,
        class_model: Type[Base],
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records asynchronously."""
        async with self.asession_scope() as s:
            stmt = select(func.count()).select_from(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            result = await s.scalar(stmt)
            return result or 0

    async def amerge(self, obj: Any) -> None:
        """Merge an object (update or insert) asynchronously."""
        async with self.asession_scope() as s:
            await s.merge(obj)

    async def aexecute_sql(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[List[Any], int]:
        """Execute raw SQL asynchronously."""
        async with self.asession_scope() as s:
            result = await s.execute(text(sql), params or {})
            if result.returns_rows:  # type: ignore[attr-defined]
                return list(result.fetchall())
            else:
                return result.rowcount  # type: ignore[attr-defined]

    async def abulk_insert(
        self,
        objs: List[Any],
        batch_size: int = 1000,
    ) -> None:
        """Batch insert objects asynchronously.

        Args:
            objs: List of objects to insert
            batch_size: Batch size, default 1000
        """
        if not objs:
            return
        async with self.asession_scope() as s:
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                await s.run_sync(
                    lambda sync_session, b=batch: sync_session.bulk_save_objects(
                        b, return_defaults=False, preserve_order=False
                    )
                )

    async def abulk_upsert(
        self,
        objs: List[Any],
        batch_size: int = 1000,
    ) -> None:
        """批量幂等写入 (INSERT ... ON CONFLICT DO UPDATE)。

        用于在布隆过滤器漏判（Redis 不可用/被清空/历史数据已存在）时，
        仍能安全地写入而不触发唯一约束冲突导致整个任务失败。冲突目标取自
        各模型的 ``unique_field`` 注册映射，更新列取自 ``update_fields`` 映射。

        - 若某 datatype 未注册 unique_field：退化为普通批量插入（保持旧行为）。
        - 若已注册 unique_field 但无 update_fields：使用 ON CONFLICT DO NOTHING。
        """
        if not objs:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        # 延迟导入，避免 storage -> core.constants -> models 的循环依赖
        from core.constants import UNIQUE_FIELD_MAPPING, UPDATE_FIELD_MAPPING

        async with self.asession_scope() as session:
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                # 按模型类分组（pg_insert 单语句只能针对一张表）
                by_class: Dict[type, List[Any]] = {}
                for obj in batch:
                    by_class.setdefault(obj.__class__, []).append(obj)

                for model_cls, items in by_class.items():
                    datatype = getattr(items[0], "datatype", None)
                    unique_field = UNIQUE_FIELD_MAPPING.get(datatype) if datatype else None
                    if not unique_field:
                        # 无冲突目标，退化为普通插入
                        await session.run_sync(
                            lambda sync_session, b=items: sync_session.bulk_save_objects(
                                b, return_defaults=False, preserve_order=False
                            )
                        )
                        continue

                    # 解析真实的 ON CONFLICT 冲突目标（可能是复合唯一键，
                    # 如 content 的 (platform, content_id)），避免无对应约束报错。
                    index_elements = _resolve_upsert_index_elements(model_cls, unique_field)

                    update_fields = UPDATE_FIELD_MAPPING.get(datatype) or []
                    # 排除主键与所有冲突列（冲突列已在 index_elements 中，不能出现在 SET）
                    pk_name = model_cls.__table__.primary_key.columns.keys()[0] \
                        if model_cls.__table__.primary_key.columns else "id"
                    set_cols = [
                        c for c in update_fields
                        if c not in index_elements and c != pk_name
                        and c in model_cls.__table__.columns
                    ]

                    stmt = pg_insert(model_cls)
                    if set_cols:
                        stmt = stmt.on_conflict_do_update(
                            index_elements=index_elements,
                            set_=_build_non_null_upsert_set(model_cls, stmt, set_cols),
                        )
                    else:
                        stmt = stmt.on_conflict_do_nothing(
                            index_elements=index_elements,
                        )

                    bind_params = []
                    for obj in items:
                        param = {}
                        for col in model_cls.__table__.columns:
                            val = getattr(obj, col.name, None)
                            if val is not None:
                                param[col.name] = val
                        bind_params.append(param)
                    await session.execute(stmt, bind_params)

    async def abulk_upsert_jobs(
        self,
        jobs: List[Any],
    ) -> int:
        """PostgreSQL native batch upsert (ON CONFLICT (platform, external_id) DO UPDATE).

        Args:
            jobs: List of Job model instances
        """
        if not jobs:
            return 0
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        job_cls = jobs[0].__class__
        stmt = pg_insert(job_cls)

        # Exclude primary key (id) and created_at from update
        update_dict = {
            col.name: stmt.excluded[col.name]
            for col in job_cls.__table__.columns
            if col.name not in ["id", "created_at"]
        }

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=["platform", "external_id"],
            set_=update_dict
        )

        async with self.asession_scope() as session:
            bind_params = []
            for job in jobs:
                param = {}
                for col in job_cls.__table__.columns:
                    val = getattr(job, col.name, None)
                    if val is not None:
                        param[col.name] = val
                bind_params.append(param)

            await session.execute(upsert_stmt, bind_params)

        return len(jobs)

    async def apaginate(
        self,
        class_model: Type[T],
        page: int = 1,
        page_size: int = 20,
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
    ) -> tuple[List[T], int]:
        """Paginated query asynchronously.

        Returns:
            (items, total) tuple
        """
        async with self.asession_scope() as s:
            stmt_count = select(func.count()).select_from(class_model)
            stmt_count = _BaseAlchemyHelper.apply_filters(
                stmt_count, class_model, filter
            )
            total = await s.scalar(stmt_count) or 0
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if order_by:
                stmt = stmt.order_by(
                    *_BaseAlchemyHelper.build_order(class_model, order_by)
                )
            offset = (page - 1) * page_size
            stmt = stmt.limit(page_size).offset(offset)
            result = await s.scalars(stmt)
            items = list(result.all())
            return items, total

    async def aexists(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a record exists asynchronously (optimized with EXISTS subquery)."""
        async with self.asession_scope() as s:
            subq = select(class_model)
            subq = _BaseAlchemyHelper.apply_filters(subq, class_model, filter)
            stmt = select(sql_exists(subq))
            result = await s.scalar(stmt)
            return result or False

    async def abulk_update(
        self,
        class_model: Type[Base],
        data: List[Dict[str, Any]],
        key_fields: List[str],
        batch_size: int = 500,
    ) -> int:
        """Batch update based on business unique keys asynchronously.

        Uses Core SQL to execute updates one by one, bypassing ORM primary key restrictions.
        """
        if not data:
            return 0

        total_updated = 0
        processed_count = 0
        pk_columns = list(class_model.__table__.primary_key.columns)
        primary_key = pk_columns[0].name if pk_columns else None

        async with AsyncSession(self.engine, expire_on_commit=False) as s:
            try:
                for item in data:
                    where_params = {
                        k: item.get(k) for k in key_fields if item.get(k) is not None
                    }
                    if len(where_params) != len(key_fields):
                        continue

                    set_params = {
                        k: v
                        for k, v in item.items()
                        if k not in key_fields and k != primary_key
                    }
                    if not set_params:
                        continue

                    stmt = (
                        update(class_model)
                        .where(
                            and_(
                                *[
                                    getattr(class_model, k) == v
                                    for k, v in where_params.items()
                                ]
                            )
                        )
                        .values(**set_params)
                        .execution_options(synchronize_session=None)
                    )

                    result = await s.execute(stmt)
                    total_updated += (
                        result.rowcount if hasattr(result, "rowcount") else 1
                    )
                    processed_count += 1

                    if processed_count % batch_size == 0:
                        await s.commit()
                await s.commit()
            except Exception as e:
                await s.rollback()
                logger.error(f"Async batch update failed ({type(e).__name__})")
                raise convert_sql_error(e)

        return total_updated

    async def aaggregate(
        self,
        class_model: Type[Base],
        aggregations: Dict[str, tuple],
        filter: Optional[Dict[str, Any]] = None,
        group_by: Optional[List[str]] = None,
    ) -> List[Any]:
        """Aggregate query asynchronously.

        Args:
            aggregations: Aggregation config, format: {alias: (field, func)}
                         Supported functions: count, sum, avg, min, max
            filter: Filter conditions
            group_by: Group by fields
        """
        async with self.asession_scope() as s:
            agg_columns = []
            for alias, (field, agg_func) in aggregations.items():
                col = _BaseAlchemyHelper._build_aggregation_column(
                    class_model, field, agg_func, alias
                )
                if col is not None:
                    agg_columns.append(col)

            if group_by:
                for field in group_by:
                    if hasattr(class_model, field):
                        agg_columns.append(getattr(class_model, field))

            stmt = select(*agg_columns)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if group_by:
                stmt = stmt.group_by(
                    *[
                        getattr(class_model, f)
                        for f in group_by
                        if hasattr(class_model, f)
                    ]
                )
            result = await s.execute(stmt)
            return result.fetchall()

    @asynccontextmanager
    async def atransaction(self, auto_commit: bool = False):
        """Asynchronous manual transaction context manager."""
        async with AsyncSession(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                if auto_commit:
                    await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Async manual transaction failed ({type(e).__name__})")
                raise convert_sql_error(e)

    async def aupdate(
        self,
        class_model: Type[Base],
        filter: Dict[str, Any],
        update_data: Dict[str, Any],
    ) -> int:
        """Update records asynchronously.

        Returns:
            Number of updated rows
        """
        async with self.asession_scope() as s:
            stmt = (
                update(class_model)
                .where(and_(*_BaseAlchemyHelper.build_conditions(class_model, filter)))
                .values(**update_data)
            )
            result = await s.execute(stmt)
            return result.rowcount if hasattr(result, "rowcount") else 0

    async def adelete(
        self, class_model: Type[Base], filter: Dict[str, Any]
    ) -> int:
        """Delete records asynchronously.

        Returns:
            Number of deleted rows
        """
        async with self.asession_scope() as s:
            stmt = delete(class_model).where(
                and_(*_BaseAlchemyHelper.build_conditions(class_model, filter))
            )
            result = await s.execute(stmt)
            return result.rowcount if hasattr(result, "rowcount") else 0

    async def aget(self, class_model: Type[T], pk: Any) -> Optional[T]:
        """Get a record by primary key asynchronously."""
        async with self.asession_scope() as s:
            return await s.get(class_model, pk)

    def get_pool_status(self) -> Dict[str, Any]:
        return _BaseAlchemyHelper._get_pool_status(self.engine)

    async def aremove_duplicates(
        self,
        class_model: Type[Base],
        duplicate_fields: List[str],
        keep: Literal["first", "last"] = "first",
        order_by_field: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_window_function: bool = False,
    ) -> int:
        """Asynchronous version of ``remove_duplicates``."""
        delete_sql = _BaseAlchemyHelper._build_remove_duplicates_sql(
            class_model, duplicate_fields, keep, order_by_field, use_window_function
        )
        async with self.asession_scope() as s:
            result = await s.execute(text(delete_sql))
            return result.rowcount

    async def ainit_db(self, drop_existing: bool = False):
        """Initialize database tables asynchronously.

        Args:
            drop_existing: If True, drop existing tables first
        """
        try:
            async with self.engine.begin() as conn:
                if drop_existing:
                    logger.warning("Dropping all existing tables...")
                    await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Async database tables initialized successfully.")
        except SQLAlchemyError as e:
            logger.error(f"Async database initialization failed: {e}")
            raise

    async def amigrate_db(self) -> None:
        """Apply idempotent schema migrations for columns that exist in the ORM
        model but may be missing from an already-created table.

        ``Base.metadata.create_all`` only creates *new* tables, so columns added
        to an existing table after first deployment (e.g. the looping task fields
        ``loop_enabled`` / ``loop_interval_seconds`` / ``next_run_at``) are never
        applied by ``ainit_db``. Running this after ``ainit_db`` keeps existing
        databases working without a manual migration step.

        Uses ``ADD COLUMN IF NOT EXISTS`` so it is safe to run on every startup
        and on a fresh database. Restricted to PostgreSQL because the
        ``IF NOT EXISTS`` DDL clause here is backend-specific; non-PG backends
        (e.g. sqlite test setups) are skipped to avoid syntax errors.
        """
        if self.engine.url.get_backend_name() != "postgresql":
            return
        llm_provider_format_migration = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "migrate_llm_provider_formats.sql"
        ).read_text(encoding="utf-8")
        migrations = [
            """
            CREATE TABLE IF NOT EXISTS public.t_video_clean_cursor (
                id BIGSERIAL PRIMARY KEY,
                consumer_key VARCHAR(128) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                policy_hash VARCHAR(64) NOT NULL,
                watermark_ts TIMESTAMP NOT NULL,
                watermark_id BIGINT NOT NULL DEFAULT 0,
                updated_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_video_clean_cursor_consumer_platform "
            "ON public.t_video_clean_cursor (consumer_key, platform)",
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS download_claim_token VARCHAR(64)",
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS download_claimed_at TIMESTAMP",
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS download_attempt_count "
            "INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS download_next_retry_at TIMESTAMP",
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS download_last_error TEXT",
            "CREATE INDEX IF NOT EXISTS idx_mc_download_claim "
            "ON public.t_material_clean "
            "(clean_status, download_next_retry_at, download_claimed_at, "
            "download_attempt_count)",
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS loop_enabled BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS loop_interval_seconds INTEGER",
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP",
            "ALTER TABLE public.t_crawl_task "
            "ADD COLUMN IF NOT EXISTS priority SMALLINT NOT NULL DEFAULT 2",
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_task_priority_range'
                      AND conrelid = 'public.t_crawl_task'::regclass
                ) THEN
                    ALTER TABLE public.t_crawl_task
                        ADD CONSTRAINT ck_task_priority_range
                        CHECK (priority BETWEEN 0 AND 4);
                END IF;
            END
            $$
            """,
            "ALTER TABLE public.t_material_clean "
            "ADD COLUMN IF NOT EXISTS is_analysis SMALLINT NOT NULL DEFAULT 0",
            "COMMENT ON COLUMN public.t_material_clean.is_analysis "
            "IS '分析状态：0=未分析，1=分析成功，2=分析中，3=分析失败'",
            "ALTER TABLE public.t_video_analysis_result "
            "ADD COLUMN IF NOT EXISTS llm_model_id INTEGER",
            "ALTER TABLE public.t_video_analysis_result "
            "ALTER COLUMN model TYPE VARCHAR(500)",
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_video_analysis_llm_model'
                      AND conrelid = 'public.t_video_analysis_result'::regclass
                ) THEN
                    ALTER TABLE public.t_video_analysis_result
                        ADD CONSTRAINT fk_video_analysis_llm_model
                        FOREIGN KEY (llm_model_id) REFERENCES public.t_llm_model (id);
                END IF;
            END
            $$
            """,
            "CREATE INDEX IF NOT EXISTS idx_video_analysis_llm_model_id "
            "ON public.t_video_analysis_result (llm_model_id)",
            llm_provider_format_migration,
        ]
        async with self.asession_scope() as session:
            for ddl in migrations:
                await session.execute(text(ddl))

    async def aclose(self):
        """Dispose the underlying engine."""
        await self.engine.dispose()
