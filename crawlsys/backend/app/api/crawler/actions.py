"""Action management JSON API routes."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.crawler.schemas import (
    ActionBatchDeleteRequest,
    ActionBatchDeleteResponse,
    ActionBatchStatusRequest,
    ActionBatchStatusResponse,
    ActionCreate,
    ActionImportRequest,
    ActionImportResponse,
    ActionList,
    ActionRead,
    ActionSyncItemDetail,
    ActionSyncRequest,
    ActionSyncResponse,
    ActionUpdate,
)
from core.repository import ActionRepo, PlatformRepo
from models.action import Action
from api.deps import get_action_parser_service, get_db
from services.action_sync import sync_actions
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.service import ActionParserService
from storage.exceptions import AlreadyExistsError

router = APIRouter(prefix="/api/crawler/actions", tags=["actions"])


def _action_dto(action: Action) -> ActionRead:
    return ActionRead.model_validate(action)


async def _save_action(repo: ActionRepo, action: Action) -> Action:
    try:
        return await repo.save(action)
    except AlreadyExistsError:
        raise HTTPException(status_code=409, detail="接口名称已存在") from None


async def _ensure_platform_exists(db, platform_id: int) -> None:
    if not await PlatformRepo(db).find_by_id(platform_id):
        raise HTTPException(status_code=404, detail="平台不存在")


@router.get("", response_model=ActionList)
async def list_actions(platform_id: int | None = None, db=Depends(get_db)):
    actions = await ActionRepo(db).find_all(platform_id=platform_id)
    return ActionList(items=[_action_dto(item) for item in actions])


@router.post("/import", response_model=ActionImportResponse)
async def import_actions(payload: ActionImportRequest, db=Depends(get_db)):
    await _ensure_platform_exists(db, payload.platform_id)
    repo = ActionRepo(db)
    created_count = 0
    updated_count = 0

    for item in payload.actions:
        params_schema = json.dumps(item.params, ensure_ascii=False) if item.params else None
        existing = await repo.find_by_name(payload.platform_id, item.name)
        if existing:
            await repo.update(
                existing.ba_id,
                ba_desc=item.description,
                ba_params_schema=params_schema,
            )
            updated_count += 1
        else:
            await _save_action(
                repo,
                Action(
                    bs_id=payload.platform_id,
                    ba_action=item.name,
                    ba_desc=item.description,
                    ba_params_schema=params_schema,
                    ba_enabled=True,
                ),
            )
            created_count += 1

    return ActionImportResponse(
        created_count=created_count,
        updated_count=updated_count,
    )


@router.post("/sync", response_model=ActionSyncResponse)
async def sync_platform_actions_endpoint(
    payload: ActionSyncRequest = ActionSyncRequest(),
    db=Depends(get_db),
):
    platform_id = payload.platform_id
    force = payload.force
    if platform_id is not None:
        await _ensure_platform_exists(db, platform_id)
    try:
        result = await sync_actions(db, platform_id=platform_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ActionSyncResponse(
        inserted_count=result["inserted_count"],
        updated_count=result["updated_count"],
        skipped_manual_count=result["skipped_manual_count"],
        total_synced=result["total_synced"],
        unknown_groups=result.get("unknown_groups", []),
        details=[ActionSyncItemDetail(**item) for item in result.get("details", [])],
    )


@router.post("/batch-status", response_model=ActionBatchStatusResponse)
async def batch_update_action_status(
    payload: ActionBatchStatusRequest,
    db=Depends(get_db),
):
    count = await ActionRepo(db).batch_update_status(
        action_ids=payload.action_ids,
        enabled=payload.enabled,
    )
    return ActionBatchStatusResponse(updated_count=count)


@router.post("/batch-delete", response_model=ActionBatchDeleteResponse)
async def batch_delete_actions(
    payload: ActionBatchDeleteRequest,
    parser_service: ActionParserService = Depends(get_action_parser_service),
):
    deleted_count = 0
    for ba_id in payload.action_ids:
        try:
            await parser_service.delete_action(ba_id)
            deleted_count += 1
        except ParserConfigurationError as exc:
            if exc.code == "action_not_found":
                continue
            raise
    return ActionBatchDeleteResponse(deleted_count=deleted_count)


@router.get("/{ba_id}", response_model=ActionRead)
async def get_action(ba_id: int, db=Depends(get_db)):
    action = await ActionRepo(db).find_by_id(ba_id)
    if not action:
        raise HTTPException(status_code=404, detail="接口不存在")
    return _action_dto(action)


@router.post("", response_model=ActionRead, status_code=status.HTTP_201_CREATED)
async def create_action(payload: ActionCreate, db=Depends(get_db)):
    await _ensure_platform_exists(db, payload.bs_id)
    repo = ActionRepo(db)
    if await repo.find_by_name(payload.bs_id, payload.ba_action):
        raise HTTPException(status_code=409, detail="接口名称已存在")
    saved = await _save_action(repo, Action(**payload.model_dump()))
    return _action_dto(saved)


@router.put("/{ba_id}", response_model=ActionRead)
async def update_action(ba_id: int, payload: ActionUpdate, db=Depends(get_db)):
    repo = ActionRepo(db)
    action = await repo.find_by_id(ba_id)
    if not action:
        raise HTTPException(status_code=404, detail="接口不存在")

    changes = payload.model_dump(exclude_unset=True)
    if "ba_action" in changes:
        duplicate = await repo.find_by_name(action.bs_id, changes["ba_action"])
        if duplicate and duplicate.ba_id != ba_id:
            raise HTTPException(status_code=409, detail="接口名称已存在")
    if "ba_params_schema" in changes and "ba_schema_source" not in changes:
        action.ba_schema_source = "manual"
    for field, value in changes.items():
        setattr(action, field, value)
    saved = await _save_action(repo, action)
    return _action_dto(saved)


@router.delete("/{ba_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(
    ba_id: int,
    parser_service: ActionParserService = Depends(get_action_parser_service),
):
    await parser_service.delete_action(ba_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
