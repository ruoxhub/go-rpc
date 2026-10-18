"""Work item sources for database rows and Redis Stream deliveries."""
from __future__ import annotations

from typing import Any, Protocol

from common.logging import get_logger
from core.sql_safety import expr, ident, limit_clause, validate_order_by, validate_where
from core.stream_queue import StreamQueue
from models.task_config import DatabaseSourceConfig, RedisStreamSourceConfig
from sqlalchemy import text

from .work_item import ItemDisposition, SourceBatch, WorkItem

logger = get_logger(__file__)


class WorkItemSource(Protocol):
    async def fetch(self) -> SourceBatch: ...

    async def complete(self, item: WorkItem) -> ItemDisposition: ...

    async def fail(
        self,
        item: WorkItem,
        error: Exception,
        *,
        deterministic: bool,
    ) -> ItemDisposition: ...


class RedisStreamWorkItemSource:
    def __init__(
        self,
        queue: StreamQueue,
        source: RedisStreamSourceConfig,
        *,
        consumer: str,
        consumer_task_id: int,
    ) -> None:
        self._queue = queue
        self._source = source
        self._consumer = consumer
        self._consumer_task_id = consumer_task_id

    async def fetch(self) -> SourceBatch:
        deliveries = await self._queue.read_batch(
            self._source,
            consumer=self._consumer,
        )
        items = [
            WorkItem(
                params=delivery.params,
                entity_id=delivery.receipt.message_id,
                receipt=delivery.receipt,
                input_error=delivery.validation_error,
            )
            for delivery in deliveries
        ]
        return SourceBatch(items=items, read=len(items), claimed=len(items))

    async def complete(self, item: WorkItem) -> ItemDisposition:
        if item.receipt is None:
            raise ValueError("Redis Stream work item is missing its receipt")
        await self._queue.ack(item.receipt)
        return ItemDisposition.SUCCEEDED

    async def fail(
        self,
        item: WorkItem,
        error: Exception,
        *,
        deterministic: bool,
    ) -> ItemDisposition:
        if item.receipt is None:
            raise ValueError("Redis Stream work item is missing its receipt")
        if deterministic or item.receipt.delivery_count >= self._source.max_deliveries:
            await self._queue.dead_letter(
                item.receipt,
                consumer_task_id=self._consumer_task_id,
                error=error,
            )
            return ItemDisposition.DEAD_LETTERED
        return ItemDisposition.RETRY


class DatabaseWorkItemSource:
    def __init__(
        self,
        db: Any,
        source: DatabaseSourceConfig | None,
        *,
        platform: str | None,
    ) -> None:
        self._db = db
        self._source = source
        self._platform = platform
        self._platform_column_cache: dict[str, bool] = {}
        self._integer_key_column_cache: dict[tuple[str, str], bool] = {}

    async def fetch(self) -> SourceBatch:
        if self._source is None:
            return SourceBatch(items=[WorkItem({})], read=1)
        source = self._source
        table = ident(source.table, "table")
        key_column = ident(source.key_column, "key_column")
        select_parts = [key_column]
        for expression, alias in source.param_map.items():
            select = self._select_expr(expression, alias)
            if alias == source.key_column:
                select_parts[0] = select
            else:
                select_parts.append(select)

        where_parts: list[str] = []
        params: dict[str, Any] = {}
        if source.filter_by_platform and await self._has_platform_column(table):
            where_parts.append("platform = :platform")
            params["platform"] = self._platform
        if source.where:
            where_parts.append(f"({validate_where(source.where)})")
        if source.completion is not None:
            completion_column = ident(source.completion.column, "completion_column")
            where_parts.append(
                f"{completion_column} IS DISTINCT FROM :completion_value"
            )
            params["completion_value"] = source.completion.value

        order_items = validate_order_by(source.order_by)
        order_sql = f" ORDER BY {', '.join(order_items)}" if order_items else ""
        where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        statement = (
            f"SELECT {', '.join(select_parts)} FROM {table}{where_sql}{order_sql} "
            f"LIMIT {limit_clause(source.limit)}"
        )
        async with self._db.asession_scope() as session:
            rows = (await session.execute(text(statement), params)).mappings().all()

        items: list[WorkItem] = []
        for row in rows:
            work_params: dict[str, Any] = {}
            for alias in source.param_map.values():
                value = row.get(alias)
                if value is not None:
                    work_params[alias] = str(value)
            value = row.get(key_column)
            if value is not None:
                work_params.setdefault(key_column, str(value))
            if work_params:
                items.append(
                    WorkItem(work_params, "" if value is None else str(value))
                )
        return SourceBatch(items=items, read=len(rows))

    async def complete(self, item: WorkItem) -> ItemDisposition:
        source = self._source
        if source is None or source.completion is None:
            return ItemDisposition.SUCCEEDED
        table = ident(source.table, "table")
        key = ident(source.key_column, "key_column")
        column = ident(source.completion.column, "completion_column")
        statement = (
            f"UPDATE {table} SET {column} = :completion_value "
            f"WHERE {key} = :entity_id"
        )
        entity_id: str | int = item.entity_id
        if item.entity_id.isdigit() and await self._key_is_integer_column(table, key):
            entity_id = int(item.entity_id)
        async with self._db.asession_scope() as session:
            await session.execute(
                text(statement),
                {
                    "completion_value": source.completion.value,
                    "entity_id": entity_id,
                },
            )
        return ItemDisposition.SUCCEEDED

    async def fail(
        self,
        item: WorkItem,
        error: Exception,
        *,
        deterministic: bool,
    ) -> ItemDisposition:
        return ItemDisposition.FAILED

    async def _has_platform_column(self, table: str) -> bool:
        cached = self._platform_column_cache.get(table)
        if cached is not None:
            return cached
        statement = text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table "
            "AND column_name = 'platform' LIMIT 1"
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(statement, {"table": table})
            present = result.scalar() is not None
        self._platform_column_cache[table] = present
        return present

    async def _key_is_integer_column(self, table: str, column: str) -> bool:
        cache_key = (table, column)
        cached = self._integer_key_column_cache.get(cache_key)
        if cached is not None:
            return cached
        statement = text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table "
            "AND column_name = :column LIMIT 1"
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(
                statement,
                {"table": table, "column": column},
            )
            data_type = result.scalar()
        is_integer = data_type in {"smallint", "integer", "bigint"}
        self._integer_key_column_cache[cache_key] = is_integer
        return is_integer

    @staticmethod
    def _select_expr(expression: str, alias: str) -> str:
        safe_expression = expr(expression, "column expression")
        safe_alias = ident(alias, "column alias")
        return f'{safe_expression} AS "{safe_alias}"'
