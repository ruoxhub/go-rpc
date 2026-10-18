"""Task management JSON API routes."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, text
from starlette.responses import JSONResponse

from api.crawler.schemas import (
    ActionSchemaResponse,
    LlmModelMetadataResponse,
    SchedulePreviewRequest,
    SchedulePreviewResponse,
    TableColumnsResponse,
    TaskBatchStatusRequest,
    TaskBatchStatusResponse,
    TaskCreate,
    TaskList,
    TaskPriorityUpdate,
    TaskRead,
    TaskRetryPolicy,
    TaskSchedule,
    TaskScheduleInfo,
    TaskUpdate,
)
from core.repository import ActionRepo, PlatformRepo, TaskRepo
from core.task_config_merge import merge_task_config
from core.task_model_validation import validate_explicit_task_model
from core.task_schedule import ScheduleRule, cron_preview, next_schedule_at
from llm.catalog import LlmCatalog
from llm.model_factory import ModelUnavailableError
from models.task import BusTask, TaskStatus
from models.action import Action
from models.action_parser import ActionParserRevision
from models.llm_provider import LlmModel, LlmProvider
from models.task_config import (
    DatabaseSourceConfig,
    SinkConfig,
    SourceConfig,
    TaskConfig,
)
from api.deps import get_db, get_llm_catalog, get_runtime_config_store
from parser.compatibility import SinkCompatibilityError, validate_sink_compatibility
from parser.definition import validate_parser_definition
from storage.exceptions import AlreadyExistsError, SQLOperationError

router = APIRouter(prefix="/api/crawler/tasks", tags=["tasks"])

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
_EXPR_RE = re.compile(r"^[a-zA-Z0-9_.:'()\- >]+$")


def _parse_params_columns(
    raw: str | None,
    key_column: str | None,
) -> tuple[dict[str, str], list[str]]:
    """Parse the legacy column expression into source configuration fields."""
    if not raw:
        return {}, []
    param_map: dict[str, str] = {}
    extras: list[str] = []
    for token in (item.strip() for item in raw.split(",") if item.strip()):
        token = re.sub(
            r"^\s*DISTINCT\s+",
            "",
            token,
            flags=re.IGNORECASE,
        ).strip()
        if " as " in token.lower():
            column, alias = re.split(
                r"\s+as\s+",
                token,
                maxsplit=1,
                flags=re.IGNORECASE,
            )
            column, alias = column.strip(), alias.strip()
        else:
            column = alias = token
        if not _IDENT_RE.fullmatch(alias):
            raise ValueError(f"Invalid column alias: {alias!r}")
        if not _EXPR_RE.fullmatch(column):
            raise ValueError(f"Invalid SQL expression: {column!r}")
        param_map[column] = alias
        if key_column and alias != key_column and column != key_column:
            if column not in extras:
                extras.append(column)
    return param_map, extras


def _legacy_source(payload: TaskCreate | TaskUpdate):
    """Build a database source from the legacy flat request fields."""
    if (
        payload.ref_table
        or payload.entity_column
        or payload.ref_where
        or payload.params_columns
    ):
        if not payload.ref_table or not payload.entity_column:
            raise ValueError("配置数据源时必须同时填写查询表和主键列")
        param_map, extras = _parse_params_columns(
            payload.params_columns,
            payload.entity_column,
        )
        return SourceConfig(
            table=payload.ref_table,
            where=payload.ref_where or None,
            key_column=payload.entity_column,
            param_map=param_map,
            extra_columns=extras,
        )
    return None


def _legacy_sink(payload: TaskCreate | TaskUpdate):
    """Build a database sink from the legacy flat request fields."""
    return SinkConfig(
        mode=payload.sink_mode,
        result_column=payload.result_column or None,
        mark_done_column=payload.post_update_column or None,
        mark_done_table=payload.post_update_table or None,
    )


def _public_task_parts(payload: TaskCreate | TaskUpdate):
    """Build structured I/O sections while preserving legacy requests."""
    source = (
        payload.source
        if "source" in payload.model_fields_set
        else _legacy_source(payload)
    )
    sink = (
        payload.sink
        if "sink" in payload.model_fields_set
        else _legacy_sink(payload)
    )
    return source, sink or SinkConfig()


def _apply_loop_settings(
    task: BusTask,
    loop_enabled: bool,
    loop_interval_seconds: int | None,
) -> None:
    task.loop_enabled = loop_enabled
    if loop_enabled:
        task.loop_interval_seconds = (
            loop_interval_seconds
            if loop_interval_seconds is not None and loop_interval_seconds > 0
            else None
        )
        if task.status == TaskStatus.DONE:
            task.status = TaskStatus.PENDING
    else:
        task.loop_interval_seconds = None
        task.next_run_at = None


def _legacy_schedule_from_loop(
    loop_enabled: bool,
    loop_interval_seconds: int | None,
) -> TaskSchedule:
    """兼容期：旧 loop 请求转换为结构化调度配置。"""
    if loop_enabled:
        return TaskSchedule(
            type="interval",
            interval_seconds=loop_interval_seconds,
        )
    return TaskSchedule(type="manual")


def _apply_schedule(
    task: BusTask,
    schedule: TaskSchedule,
    retry_policy: TaskRetryPolicy,
    *,
    now: datetime,
    timezone_name: str,
) -> None:
    """将结构化调度/重试配置写入任务字段并计算下次运行时间。"""
    task.schedule_type = schedule.type
    task.cron_expression = schedule.cron if schedule.type == "cron" else None
    task.run_once_at = schedule.run_at if schedule.type == "once" else None
    task.schedule_start_at = schedule.start_at
    task.schedule_end_at = schedule.end_at
    task.max_runs = schedule.max_runs
    if schedule.type == "interval":
        task.loop_enabled = True
        task.loop_interval_seconds = schedule.interval_seconds
    else:
        task.loop_enabled = False
        task.loop_interval_seconds = None

    task.retry_max_attempts = retry_policy.max_attempts
    task.retry_delay_seconds = retry_policy.initial_delay_seconds
    task.retry_backoff_multiplier = retry_policy.backoff_multiplier
    task.retry_max_delay_seconds = retry_policy.max_delay_seconds

    task.next_run_at = next_schedule_at(
        ScheduleRule(
            type=schedule.type,
            interval_seconds=schedule.interval_seconds,
            cron_expression=schedule.cron,
            run_at=schedule.run_at,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            max_runs=schedule.max_runs,
        ),
        now=now,
        timezone_name=timezone_name,
    )


def _task_dto(task: BusTask) -> TaskRead:
    dto = TaskRead.model_validate(task)
    dto.schedule = TaskScheduleInfo(
        type=task.schedule_type or TaskScheduleType.MANUAL.value,
        cron=task.cron_expression,
        run_at=task.run_once_at,
        interval_seconds=task.loop_interval_seconds,
        start_at=task.schedule_start_at,
        end_at=task.schedule_end_at,
        max_runs=task.max_runs,
    )
    dto.retry_policy = TaskRetryPolicy(
        max_attempts=task.retry_max_attempts,
        initial_delay_seconds=task.retry_delay_seconds,
        backoff_multiplier=task.retry_backoff_multiplier,
        max_delay_seconds=task.retry_max_delay_seconds,
    )
    return dto


async def _table_columns(db, table_name: str) -> list[str]:
    if not _IDENT_RE.fullmatch(table_name):
        raise HTTPException(status_code=422, detail="数据表名称无效")
    async with db.asession_scope() as session:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table_name "
                "ORDER BY column_name"
            ),
            {"table_name": table_name},
        )
        return [row[0] for row in result.fetchall()]


async def _resolve_action(db, ba_id: int):
    action = await ActionRepo(db).find_by_id(ba_id)
    if not action:
        raise HTTPException(status_code=404, detail="接口不存在")
    platform = await PlatformRepo(db).find_by_id(action.bs_id)
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    return action, platform


async def _config_from_payload(
    db,
    catalog: LlmCatalog,
    payload: TaskCreate | TaskUpdate,
    *,
    existing: TaskConfig | None = None,
    creating: bool,
) -> TaskConfig:
    try:
        source, sink = _public_task_parts(payload)
        config = merge_task_config(
            existing,
            executor=payload.executor,
            executor_explicit="executor" in payload.model_fields_set,
            execution_mode=payload.execution_mode,
            execution_mode_explicit=(
                "execution_mode" in payload.model_fields_set
            ),
            llm_model_id=payload.llm_model_id,
            llm_model_explicit="llm_model_id" in payload.model_fields_set,
            source=source,
            sink=sink,
            creating=creating,
            download=payload.download,
            download_explicit="download" in payload.model_fields_set,
        )
        if config.executor == "video_analysis" and config.analysis is not None:
            if "review_route" in payload.model_fields_set:
                config.analysis.review_route = payload.review_route
        elif config.analysis is not None:
            config.analysis.review_route = None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    if isinstance(config.source, DatabaseSourceConfig):
        columns = await _table_columns(db, config.source.table)
        if not columns:
            raise HTTPException(status_code=422, detail="数据表不存在")
        if config.source.key_column not in columns:
            raise HTTPException(status_code=422, detail="主键列不存在")
        if (
            config.source.completion is not None
            and config.source.completion.column not in columns
        ):
            raise HTTPException(status_code=422, detail="完成标记列不存在")
    if (
        payload.llm_model_id is not None
        and config.executor != "video_analysis"
    ):
        raise HTTPException(status_code=422, detail="只有视频分析任务可以指定模型")
    try:
        await validate_explicit_task_model(
            catalog,
            config,
            explicit="llm_model_id" in payload.model_fields_set,
        )
    except ModelUnavailableError:
        raise HTTPException(status_code=422, detail="指定的分析模型不存在或不可用") from None
    except SQLOperationError:
        raise HTTPException(status_code=503, detail="模型目录暂时不可用") from None
    return config


async def _save_task(
    db,
    repo: TaskRepo,
    task: BusTask,
    *,
    action_ids: set[int],
    allow_legacy_return: bool = False,
) -> BusTask | JSONResponse:
    try:
        async with db.asession_scope() as session:
            await session.execute(
                select(Action)
                .where(Action.ba_id.in_(sorted(action_ids)))
                .order_by(Action.ba_id)
                .with_for_update()
            )
            revision = (
                await session.execute(
                    select(ActionParserRevision)
                    .where(
                        ActionParserRevision.ba_id == task.ba_id,
                        ActionParserRevision.status == "published",
                    )
                    .order_by(ActionParserRevision.revision_no.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if revision is not None:
                definition = validate_parser_definition(revision.definition)
                try:
                    validate_sink_compatibility(definition, task.config)
                except SinkCompatibilityError:
                    sink = task.config.sink
                    return JSONResponse(
                        status_code=422,
                        content={
                            "code": "parser_sink_incompatible",
                            "message": "parser output is incompatible with task sink",
                            "details": {
                                "ba_id": task.ba_id,
                                "output": {"mode": definition.output.mode},
                                "sink": {
                                    "type": sink.type,
                                    "mode": getattr(sink, "mode", None),
                                },
                            },
                        },
                    )
            saved = await repo.save_in_session(session, task)
    except AlreadyExistsError:
        raise HTTPException(status_code=409, detail="平台接口任务已存在") from None
    if isinstance(saved, BusTask):
        return saved
    if saved is None and not allow_legacy_return:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("", response_model=TaskList)
async def list_tasks(platform: str | None = None, db=Depends(get_db)):
    tasks = await TaskRepo(db).find_all(platform=platform)
    return TaskList(items=[_task_dto(item) for item in tasks])


@router.post("/schedule/preview", response_model=SchedulePreviewResponse)
async def preview_schedule(
    payload: SchedulePreviewRequest,
    store=Depends(get_runtime_config_store),
):
    settings = await store.get_scheduler()
    occurrences = cron_preview(
        payload.cron,
        now=datetime.now(timezone.utc),
        timezone_name=settings.timezone,
    )
    return SchedulePreviewResponse(
        timezone=settings.timezone,
        occurrences=occurrences,
    )


@router.get("/meta/table-columns", response_model=TableColumnsResponse)
async def get_table_columns(table_name: str, db=Depends(get_db)):
    return TableColumnsResponse(columns=await _table_columns(db, table_name.strip()))


@router.get(
    "/meta/action-schemas/{action_id}",
    response_model=ActionSchemaResponse,
)
async def get_action_schema(action_id: int, db=Depends(get_db)):
    repo = ActionRepo(db)
    if not await repo.find_by_id(action_id):
        raise HTTPException(status_code=404, detail="接口不存在")
    action_schema = await repo.get_schema(action_id)
    return ActionSchemaResponse(
        schema=action_schema if action_schema is not None else [],
    )


@router.get("/meta/llm-models", response_model=LlmModelMetadataResponse)
async def get_usable_llm_models(db=Depends(get_db)):
    async with db.asession_scope() as session:
        result = await session.scalars(
            select(LlmModel)
            .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
            .where(
                LlmProvider.enabled.is_(True),
                LlmModel.enabled.is_(True),
                LlmModel.remote_available.is_(True),
            )
            .order_by(LlmModel.display_name, LlmModel.id)
        )
        return LlmModelMetadataResponse(llm_models=list(result))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db=Depends(get_db),
    catalog: LlmCatalog = Depends(get_llm_catalog),
    store=Depends(get_runtime_config_store),
):
    action, platform = await _resolve_action(db, payload.ba_id)
    task = BusTask(
        platform=platform.bs_platform_code,
        platform_id=platform.bs_id,
        action=action.ba_action,
        ba_id=action.ba_id,
        priority=payload.priority.db_value,
        config=await _config_from_payload(db, catalog, payload, creating=True),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    settings = await store.get_scheduler()
    if "schedule" in payload.model_fields_set:
        schedule = payload.schedule
    elif payload.loop_enabled:
        schedule = _legacy_schedule_from_loop(
            payload.loop_enabled,
            payload.loop_interval_seconds or settings.default_loop_interval_seconds,
        )
    else:
        schedule = TaskSchedule(type="manual")
    _apply_schedule(
        task,
        schedule,
        payload.retry_policy,
        now=datetime.now(timezone.utc),
        timezone_name=settings.timezone,
    )
    saved = await _save_task(
        db,
        TaskRepo(db),
        task,
        action_ids={task.ba_id},
        allow_legacy_return=True,
    )
    if isinstance(saved, JSONResponse):
        return saved
    return _task_dto(saved)


@router.post("/start-all", response_model=TaskBatchStatusResponse)
async def start_all_tasks(
    payload: TaskBatchStatusRequest,
    db=Depends(get_db),
):
    count = await TaskRepo(db).batch_set_status(
        platform=payload.platform,
        status=TaskStatus.PENDING,
    )
    return TaskBatchStatusResponse(updated_count=count)


@router.post("/pause-all", response_model=TaskBatchStatusResponse)
async def pause_all_tasks(
    payload: TaskBatchStatusRequest,
    db=Depends(get_db),
):
    count = await TaskRepo(db).batch_set_status(
        platform=payload.platform,
        status=TaskStatus.PAUSED,
        skip_running=True,
    )
    return TaskBatchStatusResponse(updated_count=count)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, db=Depends(get_db)):
    task = await TaskRepo(db).find_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_dto(task)


@router.patch("/{task_id}/priority", response_model=TaskRead)
async def update_task_priority(
    task_id: int,
    payload: TaskPriorityUpdate,
    db=Depends(get_db),
):
    task = await TaskRepo(db).update_priority(task_id, payload.priority)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_dto(task)


@router.put("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db=Depends(get_db),
    catalog: LlmCatalog = Depends(get_llm_catalog),
    store=Depends(get_runtime_config_store),
):
    repo = TaskRepo(db)
    task = await repo.find_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status == TaskStatus.RUNNING.value:
        raise HTTPException(status_code=409, detail="运行中的任务不能更新")
    previous_ba_id = task.ba_id
    action, platform = await _resolve_action(db, payload.ba_id)
    task.ba_id = action.ba_id
    task.action = action.ba_action
    task.platform = platform.bs_platform_code
    task.platform_id = platform.bs_id
    if "priority" in payload.model_fields_set:
        task.priority = payload.priority.db_value
    task.config = await _config_from_payload(
        db,
        catalog,
        payload,
        existing=task.config,
        creating=False,
    )
    schedule_fields = {"schedule", "loop_enabled", "loop_interval_seconds"}
    if schedule_fields & payload.model_fields_set:
        settings = await store.get_scheduler()
        if "schedule" in payload.model_fields_set:
            schedule = payload.schedule
        elif payload.loop_enabled:
            schedule = _legacy_schedule_from_loop(
                payload.loop_enabled,
                payload.loop_interval_seconds or settings.default_loop_interval_seconds,
            )
        else:
            schedule = TaskSchedule(type="manual")
        _apply_schedule(
            task,
            schedule,
            payload.retry_policy,
            now=datetime.now(timezone.utc),
            timezone_name=settings.timezone,
        )
    task.updated_at = datetime.now()
    saved = await _save_task(
        db,
        repo,
        task,
        action_ids={ba_id for ba_id in (previous_ba_id, task.ba_id) if ba_id is not None},
    )
    if isinstance(saved, JSONResponse):
        return saved
    return _task_dto(saved)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db=Depends(get_db)):
    repo = TaskRepo(db)
    if not await repo.find_by_id(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    await repo.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/start", response_model=TaskRead)
async def start_task(
    task_id: int,
    db=Depends(get_db),
    store=Depends(get_runtime_config_store),
):
    repo = TaskRepo(db)
    task = await repo.find_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    settings = await store.get_scheduler()
    next_run_at = next_schedule_at(
        ScheduleRule(
            type=task.schedule_type or TaskScheduleType.MANUAL.value,
            interval_seconds=task.loop_interval_seconds,
            cron_expression=task.cron_expression,
            run_at=task.run_once_at,
            start_at=task.schedule_start_at,
            end_at=task.schedule_end_at,
            max_runs=task.max_runs,
        ),
        now=datetime.now(timezone.utc),
        timezone_name=settings.timezone,
    )
    if not await repo.resume(task_id, next_run_at=next_run_at):
        raise HTTPException(status_code=409, detail="任务状态更新冲突")
    updated = await repo.find_by_id(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_dto(updated)


@router.post("/{task_id}/run-now", status_code=status.HTTP_204_NO_CONTENT)
async def run_task_now(task_id: int, db=Depends(get_db)):
    repo = TaskRepo(db)
    if not await repo.find_by_id(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not await repo.request_run_now(task_id):
        raise HTTPException(status_code=409, detail="任务已达执行次数上限")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(task_id: int, db=Depends(get_db)):
    repo = TaskRepo(db)
    if not await repo.find_by_id(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    if not await repo.pause(task_id):
        raise HTTPException(status_code=409, detail="任务状态更新冲突")
    updated = await repo.find_by_id(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _task_dto(updated)
