"""Crawler JSON API 路由聚合。"""
from fastapi import APIRouter

from api.crawler import (
    action_parsers,
    actions,
    datatype_rows,
    datatypes,
    keywords,
    platforms,
    tasks,
)


router = APIRouter()
router.include_router(platforms.router)
router.include_router(actions.router)
router.include_router(action_parsers.router)
router.include_router(action_parsers.capabilities_router)
router.include_router(keywords.router)
router.include_router(tasks.router)
router.include_router(datatypes.router)
router.include_router(datatype_rows.router)
