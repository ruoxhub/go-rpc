"""Platform quota JSON API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.crawler.schemas import (
    PlatformCreate,
    PlatformList,
    PlatformRead,
    PlatformUpdate,
)
from core.repository import PlatformRepo
from models.platform import platformSource
from api.deps import get_db
from storage.exceptions import AlreadyExistsError

router = APIRouter(prefix="/api/crawler/platforms", tags=["platforms"])


def _platform_dto(platform: platformSource) -> PlatformRead:
    return PlatformRead.model_validate(platform)


async def _save_platform(repo: PlatformRepo, platform: platformSource) -> platformSource:
    try:
        return await repo.save(platform)
    except AlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="平台名称或代码已存在",
        ) from None


async def _ensure_unique(
    repo: PlatformRepo,
    payload: PlatformCreate | PlatformUpdate,
    *,
    exclude_id: int | None = None,
) -> None:
    by_code = await repo.find_by_code(payload.bs_platform_code)
    if by_code and by_code.bs_id != exclude_id:
        raise HTTPException(status_code=409, detail="平台代码已存在")

    by_name = await repo.find_by_name(payload.bs_name)
    if by_name and by_name.bs_id != exclude_id:
        raise HTTPException(status_code=409, detail="平台名称已存在")


@router.get("", response_model=PlatformList)
async def list_platforms(include_deleted: bool = False, db=Depends(get_db)):
    platforms = await PlatformRepo(db).find_all(include_deleted=include_deleted)
    return PlatformList(items=[_platform_dto(item) for item in platforms])


@router.get("/{bs_id}", response_model=PlatformRead)
async def get_platform(bs_id: int, db=Depends(get_db)):
    platform = await PlatformRepo(db).find_by_id(bs_id)
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    return _platform_dto(platform)


@router.post("", response_model=PlatformRead, status_code=status.HTTP_201_CREATED)
async def create_platform(payload: PlatformCreate, db=Depends(get_db)):
    repo = PlatformRepo(db)
    await _ensure_unique(repo, payload)
    platform = platformSource(**payload.model_dump())
    saved = await _save_platform(repo, platform)
    return _platform_dto(saved)


@router.put("/{bs_id}", response_model=PlatformRead)
async def update_platform(bs_id: int, payload: PlatformUpdate, db=Depends(get_db)):
    repo = PlatformRepo(db)
    platform = await repo.find_by_id(bs_id)
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")

    await _ensure_unique(repo, payload, exclude_id=bs_id)
    for field, value in payload.model_dump().items():
        setattr(platform, field, value)
    saved = await _save_platform(repo, platform)
    return _platform_dto(saved)


@router.delete("/{bs_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(bs_id: int, db=Depends(get_db)):
    if not await PlatformRepo(db).soft_delete(bs_id):
        raise HTTPException(status_code=404, detail="平台不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bs_id}/restore", response_model=PlatformRead)
async def restore_platform(bs_id: int, db=Depends(get_db)):
    repo = PlatformRepo(db)
    if not await repo.restore(bs_id):
        raise HTTPException(status_code=404, detail="平台不存在")
    platform = await repo.find_by_id(bs_id)
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    return _platform_dto(platform)
