"""Work item processing strategies for RPC invocation and direct publication."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from core.param_schema import (
    ActionParamsValidationError,
    InvalidActionParamSchema,
    validate_action_params,
)
from core.sink_handlers import ResultSinkRouter, SinkResult, SinkValidationError
from go_rpc import BlockedRpcError, RateLimitedRpcError, RetryableRpcError
from models import BusTask
from models.task_config import DatabaseSourceConfig, TaskConfig
from services.parser_configuration.repository import ActionRuntimeDefinition

from .work_item import ItemResult, WorkItem


class WorkItemValidationError(ValueError):
    """A deterministic work item error that should not be retried."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class WorkItemProcessor(Protocol):
    async def process(
        self,
        task: BusTask,
        item: WorkItem,
        runtime: ActionRuntimeDefinition | None = None,
    ) -> ItemResult: ...


class InvokeActionProcessor:
    def __init__(
        self,
        *,
        rpc: Any,
        limiter_for: Callable[[str], Any],
        sink_router: ResultSinkRouter,
    ) -> None:
        self._rpc = rpc
        self._limiter_for = limiter_for
        self._sink_router = sink_router

    async def process(
        self,
        task: BusTask,
        item: WorkItem,
        runtime: ActionRuntimeDefinition | None = None,
    ) -> ItemResult:
        if runtime is not None:
            self._validate_params(runtime.params_schema, item.params)
        parser_definition = runtime.parser_definition if runtime else None
        parser_revision_id = runtime.parser_revision_id if runtime else None
        config = self._config(task)
        if config.pagination is None:
            raw = await self._invoke(task, item.params)
            return ItemResult(
                await self._persist(
                    task=task,
                    source=self._database_source(config),
                    sink=config.sink,
                    raw=raw,
                    item=item,
                    parser_definition=parser_definition,
                    parser_revision_id=parser_revision_id,
                )
            )

        pagination = config.pagination
        cursor = pagination.initial_cursor
        visited = {cursor}
        pages = 0
        result = SinkResult()
        while True:
            params = {**item.params, pagination.cursor_param: cursor}
            raw = self._normalize_page(await self._invoke(task, params))
            if not raw.get("itemList"):
                break
            result += await self._persist(
                task=task,
                source=self._database_source(config),
                sink=config.sink,
                raw=raw,
                item=item,
                parser_definition=parser_definition,
                parser_revision_id=parser_revision_id,
            )
            pages += 1
            if pagination.max_pages and pages >= pagination.max_pages:
                break
            if raw.get("hasMore") is False:
                break
            next_cursor = self._next_cursor(raw, pagination.response_cursor_keys)
            if next_cursor is None or next_cursor in visited:
                break
            visited.add(next_cursor)
            cursor = next_cursor
        return ItemResult(result)

    async def _persist(self, **kwargs: Any) -> SinkResult:
        try:
            return await self._sink_router.persist(**kwargs)
        except SinkValidationError as error:
            raise WorkItemValidationError(error.code) from None

    async def _invoke(self, task: BusTask, params: dict[str, Any]) -> dict[str, Any]:
        limiter = self._limiter_for(task.platform)
        try:
            async with limiter:
                result = await self._rpc.invoke(task.platform, task.action, params)
            limiter.record_success()
            return result
        except RateLimitedRpcError as error:
            limiter.record_rate_limit(error.retry_after_seconds)
            raise
        except BlockedRpcError:
            limiter.record_block()
            raise
        except RetryableRpcError:
            limiter.record_transient_failure()
            raise

    @staticmethod
    def _validate_params(schema: Any, params: dict[str, Any]) -> None:
        try:
            validate_action_params(schema, params)
        except ActionParamsValidationError as error:
            raise WorkItemValidationError(
                f"invalid work item params at path {error.path} ({error.validator})"
            ) from None
        except InvalidActionParamSchema:
            raise WorkItemValidationError("invalid work item params schema") from None

    @staticmethod
    def _normalize_page(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        normalized = dict(raw)
        if "itemList" not in normalized and "item_list" in normalized:
            normalized["itemList"] = normalized["item_list"]
        if "hasMore" not in normalized and "has_more" in normalized:
            normalized["hasMore"] = bool(normalized["has_more"])
        return normalized

    @staticmethod
    def _next_cursor(raw: dict[str, Any], keys: list[str]) -> int | None:
        for key in keys:
            value = raw.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _config(task: BusTask) -> TaskConfig:
        if isinstance(task.config, TaskConfig):
            return task.config
        return TaskConfig.model_validate(task.config or {})

    @staticmethod
    def _database_source(config: TaskConfig) -> DatabaseSourceConfig | None:
        return (
            config.source if isinstance(config.source, DatabaseSourceConfig) else None
        )


class PublishSourceProcessor:
    def __init__(self, *, sink_router: ResultSinkRouter) -> None:
        self._sink_router = sink_router

    async def process(
        self,
        task: BusTask,
        item: WorkItem,
        runtime: ActionRuntimeDefinition,
    ) -> ItemResult:
        config = InvokeActionProcessor._config(task)
        try:
            result = await self._sink_router.publish_work_item(
                task=task,
                sink=config.sink,
                item=item,
                params_schema=runtime.params_schema,
            )
        except SinkValidationError as error:
            raise WorkItemValidationError(error.code) from None
        return ItemResult(result)
