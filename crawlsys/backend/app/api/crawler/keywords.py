"""Keyword management JSON API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.crawler.schemas import (
    KeywordCreate,
    KeywordList,
    KeywordRead,
    KeywordUpdate,
)
from core.repository import KeywordRepo
from models.keyword import BusiSearchKeyword
from api.deps import get_db
from storage.exceptions import AlreadyExistsError

router = APIRouter(prefix="/api/crawler/keywords", tags=["keywords"])


def _keyword_dto(keyword: BusiSearchKeyword) -> KeywordRead:
    return KeywordRead.model_validate(keyword)


async def _ensure_platform_exists(repo: KeywordRepo, platform: str) -> None:
    if not await repo.platform_exists(platform):
        raise HTTPException(status_code=404, detail="平台不存在")


async def _save_keyword(
    repo: KeywordRepo,
    keyword: BusiSearchKeyword,
) -> BusiSearchKeyword:
    try:
        return await repo.save(keyword)
    except AlreadyExistsError:
        raise HTTPException(
            status_code=409,
            detail="无法保存关键词：数据约束冲突",
        ) from None


@router.get("", response_model=KeywordList)
async def list_keywords(platform: str | None = None, db=Depends(get_db)):
    keywords = await KeywordRepo(db).find_all(platform=platform)
    return KeywordList(items=[_keyword_dto(item) for item in keywords])


@router.get("/{kid}", response_model=KeywordRead)
async def get_keyword(kid: int, db=Depends(get_db)):
    keyword = await KeywordRepo(db).find_by_id(kid)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")
    return _keyword_dto(keyword)


@router.post("", response_model=KeywordRead, status_code=status.HTTP_201_CREATED)
async def create_keyword(payload: KeywordCreate, db=Depends(get_db)):
    repo = KeywordRepo(db)
    await _ensure_platform_exists(repo, payload.platform)
    saved = await _save_keyword(
        repo,
        BusiSearchKeyword(**payload.model_dump()),
    )
    return _keyword_dto(saved)


@router.put("/{kid}", response_model=KeywordRead)
async def update_keyword(kid: int, payload: KeywordUpdate, db=Depends(get_db)):
    repo = KeywordRepo(db)
    keyword = await repo.find_by_id(kid)
    if not keyword:
        raise HTTPException(status_code=404, detail="关键词不存在")

    await _ensure_platform_exists(repo, payload.platform)
    for field, value in payload.model_dump().items():
        setattr(keyword, field, value)
    saved = await _save_keyword(repo, keyword)
    return _keyword_dto(saved)


@router.delete("/{kid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(kid: int, db=Depends(get_db)):
    if not await KeywordRepo(db).delete(kid):
        raise HTTPException(status_code=404, detail="关键词不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
