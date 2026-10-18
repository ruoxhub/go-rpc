# -*- coding: utf-8 -*-
"""SQLAlchemy storage sub-package.

Provides :class:`SQLAlchemyDB` – the unified manager supporting both
synchronous and asynchronous SQLAlchemy engines.
"""
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
)
from contextlib import contextmanager, asynccontextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from storage.base import BaseStore
from common.decorators import require_sync, require_async

from ._base import _BaseAlchemyHelper, Base, logger
from .sync import SyncSQLImpl
from ._async import AsyncSQLImpl

# Re-export Base for backward compatibility (storage.__init__ imports it from here)
__all__ = ["SQLAlchemyDB", "Base"]

T = TypeVar("T")


class SQLAlchemyDB(BaseStore):
    """Unified manager supporting both sync and async SQLAlchemy engines."""

    _impl: Any  # Union[SyncSQLImpl, AsyncSQLImpl] - determined at runtime by amode

    def __init__(
        self,
        username: str,
        password: str,
        host: str,
        port: int,
        database: str,
        *,
        amode: bool = False,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        pool_pre_ping: bool = True,
        driver: Literal["mysql", "postgresql", "sqlite", "mssql", "oracle"] = "mysql",
    ):
        super().__init__(amode=amode)
        self.url = _BaseAlchemyHelper._parse_database_url(
            driver, username, password, host, port, database, amode
        )

        engine_kwargs: Dict[str, Any] = {"echo": echo}
        if driver != "sqlite":
            engine_kwargs.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
            )

        if amode:
            engine = create_async_engine(self.url, **engine_kwargs)
            self._impl = AsyncSQLImpl(engine)
        else:
            engine = create_engine(self.url, **engine_kwargs)
            self._impl = SyncSQLImpl(engine)

        logger.info(
            f"{'Async' if amode else 'Sync'} SQLAlchemy engine initialized: {self.url.get_backend_name()}"
        )

    # ------------------- BaseStore Abstract Methods -------------------
    def connect(self):
        """Establish database connection (already done in __init__)."""
        self._connected = True

    async def aconnect(self):
        """Establish async database connection (already done in __init__)."""
        self._connected = True

    def ping(self) -> bool:
        """Check database connection status synchronously."""
        if self.is_async:
            raise RuntimeError("Sync ping is not available in async mode, use aping")
        try:
            with self._impl.session_scope() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    async def aping(self) -> bool:
        """Check database connection status asynchronously."""
        if not self.is_async:
            raise RuntimeError("Async aping is not available in sync mode, use ping")
        try:
            async with self._impl.asession_scope() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    @property
    def engine(self) -> Union[Engine, AsyncEngine]:
        """Get the underlying engine."""
        return self._impl.engine

    # ------------------- Session contexts -------------------
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Synchronous session context manager."""
        if self.is_async:
            raise RuntimeError("Current instance is in async mode, use asession_scope()")
        with self._impl.session_scope() as session:
            yield session

    @asynccontextmanager
    async def asession_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous session context manager."""
        if not self.is_async:
            raise RuntimeError("Current instance is in sync mode, use session_scope()")
        async with self._impl.asession_scope() as session:
            yield session

    # ------------------- Synchronous CRUD (delegates to SyncSQLImpl) -------------------
    @require_sync("add")
    def add(self, obj: Any):
        """Add a single object synchronously."""
        return self._impl.add(obj)

    @require_sync("adds")
    def adds(self, objs: List[Any]):
        """Batch add objects synchronously."""
        return self._impl.adds(objs)

    @require_sync("query")
    def query(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Query multiple records synchronously."""
        return self._impl.query(class_model, filter, order_by, limit, offset)

    @require_sync("query_one")
    def query_one(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[T]:
        """Query a single record synchronously."""
        return self._impl.query_one(class_model, filter)

    @require_sync("count")
    def count(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records synchronously."""
        return self._impl.count(class_model, filter)

    @require_sync("merge")
    def merge(self, obj: Any) -> None:
        """Merge an object (update or insert) synchronously."""
        return self._impl.merge(obj)

    @require_sync("execute_sql")
    def execute_sql(
        self, sql: str, params: Optional[Dict[str, Any]] = None
    ) -> Union[List[Any], int]:
        """Execute raw SQL synchronously."""
        return self._impl.execute_sql(sql, params)

    @require_sync("bulk_insert")
    def bulk_insert(self, objs: List[Any], batch_size: int = 1000) -> None:
        """Batch insert objects synchronously."""
        return self._impl.bulk_insert(objs, batch_size)

    @require_sync("paginate")
    def paginate(
        self,
        class_model: Type[T],
        page: int = 1,
        page_size: int = 20,
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
    ) -> tuple[List[T], int]:
        """Paginated query synchronously."""
        return self._impl.paginate(class_model, page, page_size, filter, order_by)

    def get_pool_status(self) -> Dict[str, Any]:
        """Get connection pool status.

        Note: This method works in both sync and async modes since pool status is retrieved synchronously.
        """
        return self._impl.get_pool_status()

    @require_sync("exists")
    def exists(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a record exists synchronously."""
        return self._impl.exists(class_model, filter)

    @require_sync("bulk_update")
    def bulk_update(
        self,
        class_model: Type[Base],
        data: List[Dict[str, Any]],
        key_fields: List[str],
        batch_size: int = 500,
    ) -> int:
        """Batch update synchronously."""
        return self._impl.bulk_update(class_model, data, key_fields, batch_size)

    @require_sync("aggregate")
    def aggregate(
        self,
        class_model: Type[Base],
        aggregations: Dict[str, tuple],
        filter: Optional[Dict[str, Any]] = None,
        group_by: Optional[List[str]] = None,
    ) -> List[Any]:
        """Aggregate query synchronously."""
        return self._impl.aggregate(class_model, aggregations, filter, group_by)

    @contextmanager
    def transaction(self, auto_commit: bool = False):
        """Synchronous manual transaction context manager."""
        if self.is_async:
            raise RuntimeError(
                "Sync transaction is not available in async mode, use atransaction"
            )
        with self._impl.transaction(auto_commit) as session:
            yield session

    @require_sync("update")
    def update(
        self,
        class_model: Type[Base],
        filter: Dict[str, Any],
        update_data: Dict[str, Any],
    ) -> int:
        """Update records synchronously."""
        return self._impl.update(class_model, filter, update_data)

    @require_sync("delete")
    def delete(self, class_model: Type[Base], filter: Dict[str, Any]) -> int:
        """Delete records synchronously."""
        return self._impl.delete(class_model, filter)

    @require_sync("get")
    def get(self, class_model: Type[T], pk: Any) -> Optional[T]:
        """Get a record by primary key synchronously."""
        return self._impl.get(class_model, pk)

    # ------------------- Asynchronous CRUD -------------------
    @require_async("add")
    async def aadd(self, obj: Any) -> None:
        """Add a single object asynchronously."""
        return await self._impl.aadd(obj)

    @require_async("adds")
    async def aadds(self, objs: List[Any]) -> None:
        """Batch add objects asynchronously."""
        return await self._impl.aadds(objs)

    @require_async("query")
    async def aquery(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Query multiple records asynchronously."""
        return await self._impl.aquery(
            class_model, filter, order_by, limit, offset
        )

    @require_async("query_one")
    async def aquery_one(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[T]:
        """Query a single record asynchronously."""
        return await self._impl.aquery_one(class_model, filter)

    @require_async("count")
    async def acount(
        self,
        class_model: Type[Base],
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records asynchronously."""
        return await self._impl.acount(class_model, filter)

    @require_async("merge")
    async def amerge(self, obj: Any) -> None:
        """Merge an object (update or insert) asynchronously."""
        return await self._impl.amerge(obj)

    @require_async("execute_sql")
    async def aexecute_sql(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Union[List[Any], int]:
        """Execute raw SQL asynchronously."""
        return await self._impl.aexecute_sql(sql, params)

    @require_async("bulk_insert")
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
        return await self._impl.abulk_insert(objs, batch_size)

    @require_async("abulk_upsert_jobs")
    async def abulk_upsert_jobs(
        self,
        jobs: List[Any],
    ) -> int:
        """Batch upsert jobs asynchronously (PostgreSQL only)."""
        return await self._impl.abulk_upsert_jobs(jobs)

    @require_async("abulk_upsert")
    async def abulk_upsert(
        self,
        objs: List[Any],
        batch_size: int = 1000,
    ) -> None:
        """批量幂等写入 (INSERT ... ON CONFLICT)，防止唯一约束冲突导致任务失败。"""
        return await self._impl.abulk_upsert(objs, batch_size)

    @require_async("paginate")
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
        return await self._impl.apaginate(
            class_model, page, page_size, filter, order_by
        )

    @require_async("exists")
    async def aexists(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a record exists asynchronously (optimized with EXISTS subquery)."""
        return await self._impl.aexists(class_model, filter)

    @require_async("bulk_update")
    async def abulk_update(
        self,
        class_model: Type[Base],
        data: List[Dict[str, Any]],
        key_fields: List[str],
        batch_size: int = 500,
    ) -> int:
        """Batch update asynchronously based on business unique keys.

        Uses Core SQL to execute updates one by one, bypassing ORM primary key restrictions.

        Args:
            class_model: SQLAlchemy model class
            data: List of dicts to update
            key_fields: Fields for WHERE condition (business unique key)
            batch_size: Batch commit size, default 500

        Returns:
            Number of updated rows
        """
        return await self._impl.abulk_update(
            class_model, data, key_fields, batch_size
        )

    @require_async("aggregate")
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
        return await self._impl.aaggregate(
            class_model, aggregations, filter, group_by
        )

    @asynccontextmanager
    async def atransaction(self, auto_commit: bool = False):
        """Asynchronous manual transaction context manager."""
        if not self.is_async:
            raise RuntimeError(
                "Async transaction is not available in sync mode, use transaction"
            )
        async with self._impl.atransaction(auto_commit) as session:
            yield session

    @require_async("update")
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
        return await self._impl.aupdate(class_model, filter, update_data)

    @require_async("delete")
    async def adelete(
        self, class_model: Type[Base], filter: Dict[str, Any]
    ) -> int:
        """Delete records asynchronously.

        Returns:
            Number of deleted rows
        """
        return await self._impl.adelete(class_model, filter)

    @require_async("get")
    async def aget(self, class_model: Type[T], pk: Any) -> Optional[T]:
        """Get a record by primary key asynchronously."""
        return await self._impl.aget(class_model, pk)

    # ------------------- Additional utilities (delegates to impl) -------------------
    @require_sync("remove_duplicates")
    def remove_duplicates(
        self,
        class_model: Type[Base],
        duplicate_fields: List[str],
        keep: Literal["first", "last"] = "first",
        order_by_field: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_window_function: bool = False,
    ) -> int:
        """Remove duplicate rows based on ``duplicate_fields``.

        Args:
            class_model: SQLAlchemy model class
            duplicate_fields: Fields to check for duplicates
            keep: Retention strategy, 'first' keeps min id, 'last' keeps max id
            order_by_field: Order field (for window function mode)
            filters: Filter conditions (reserved, not yet implemented)
            use_window_function: Whether to use window functions (recommended for large tables)

        Returns:
            Number of deleted rows
        """
        return self._impl.remove_duplicates(
            class_model,
            duplicate_fields,
            keep,
            order_by_field,
            filters,
            use_window_function,
        )

    @require_async("aremove_duplicates")
    async def aremove_duplicates(
        self,
        class_model: Type[Base],
        duplicate_fields: List[str],
        keep: Literal["first", "last"] = "first",
        order_by_field: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_window_function: bool = False,
    ) -> int:
        """Asynchronous version of ``remove_duplicates``.

        Args:
            class_model: SQLAlchemy model class
            duplicate_fields: Fields to check for duplicates
            keep: Retention strategy, 'first' keeps min id, 'last' keeps max id
            order_by_field: Order field (for window function mode)
            filters: Filter conditions (reserved, not yet implemented)
            use_window_function: Whether to use window functions (recommended for large tables)

        Returns:
            Number of deleted rows
        """
        return await self._impl.aremove_duplicates(
            class_model,
            duplicate_fields,
            keep,
            order_by_field,
            filters,
            use_window_function,
        )

    @require_sync("init_db")
    def init_db(self, drop_existing: bool = False):
        """Create all tables defined in ``Base`` metadata."""
        return self._impl.init_db(drop_existing)

    @require_async("ainit_db")
    async def ainit_db(self, drop_existing: bool = False):
        """Initialize database tables asynchronously."""
        return await self._impl.ainit_db(drop_existing)

    @require_async("amigrate_db")
    async def amigrate_db(self) -> None:
        """Apply idempotent schema migrations for existing tables.

        Keeps already-created tables in sync with the ORM model (e.g. after
        new columns are added). Safe to call on every startup.
        """
        return await self._impl.amigrate_db()

    @require_sync("close")
    def close(self):
        """Dispose the underlying engine."""
        return self._impl.close()

    @require_async("aclose")
    async def aclose(self):
        """Dispose the underlying engine."""
        return await self._impl.aclose()
