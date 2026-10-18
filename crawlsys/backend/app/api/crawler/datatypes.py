"""系统数据类型（ORM / DTO 模型元数据）管理与查询路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.deps import get_db
from core.repository import DatatypeRepo
from models.datatype import (
    SysDatatypeList,
    SysDatatypeRead,
    SysDatatypeStatusUpdate,
    SysDatatypeSyncResponse,
)
from storage import SQLAlchemyDB

router = APIRouter(prefix="/api/crawler/datatypes", tags=["datatypes"])


@router.get("", response_model=SysDatatypeList)
async def list_datatypes(
    is_active: bool | None = Query(None, description="按是否启用过滤"),
    db: SQLAlchemyDB = Depends(get_db),
) -> SysDatatypeList:
    """查询已落库持久化的数据类型（ORM/DTO 模型）元数据列表。

    若数据表为空，会自动执行首次从代码内省落库同步。
    """
    repo = DatatypeRepo(db)
    items = await repo.find_all(is_active=is_active)
    if not items:
        # 初次查询时如果尚未执行 seed/sync，自动触发同步
        await repo.sync_from_code()
        items = await repo.find_all(is_active=is_active)

    return SysDatatypeList(
        items=[SysDatatypeRead.model_validate(item) for item in items],
        total=len(items),
    )


@router.get("/{datatype_key}", response_model=SysDatatypeRead)
async def get_datatype(
    datatype_key: str,
    db: SQLAlchemyDB = Depends(get_db),
) -> SysDatatypeRead:
    """获取指定数据类型的完整元数据（包含物理字段、DTO字段、去重键与更新列等）。"""
    repo = DatatypeRepo(db)
    item = await repo.find_by_key(datatype_key)
    if not item:
        # 尝试进行一次同步以防新增了代码但未落库
        await repo.sync_from_code()
        item = await repo.find_by_key(datatype_key)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据类型 '{datatype_key}' 不存在",
        )
    return SysDatatypeRead.model_validate(item)


@router.post(
    "/sync",
    response_model=SysDatatypeSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_datatypes(
    db: SQLAlchemyDB = Depends(get_db),
) -> SysDatatypeSyncResponse:
    """手动触发：将代码中已注册的所有 ORM 模型与 DTO 结构重新内省并同步至数据库。"""
    repo = DatatypeRepo(db)
    synced_count, keys = await repo.sync_from_code()
    return SysDatatypeSyncResponse(
        success=True,
        synced_count=synced_count,
        datatypes=keys,
    )


@router.patch("/{datatype_key}/status", response_model=SysDatatypeRead)
async def update_datatype_status(
    datatype_key: str,
    payload: SysDatatypeStatusUpdate,
    db: SQLAlchemyDB = Depends(get_db),
) -> SysDatatypeRead:
    """启用或停用指定数据类型；未同步或不存在时返回 404。"""
    repo = DatatypeRepo(db)
    record = await repo.update_status(datatype_key, payload.is_active)
    if not record:
        # 尝试同步后再更新，兼容新增代码但尚未落库的情况
        await repo.sync_from_code()
        record = await repo.update_status(datatype_key, payload.is_active)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"数据类型 '{datatype_key}' 不存在",
        )
    return SysDatatypeRead.model_validate(record)


__all__ = ["router"]
