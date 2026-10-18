"""Web 层共享的平台查询辅助。"""
from __future__ import annotations

from core.repository import PlatformRepo


async def load_active_platforms(db) -> list:
    """加载未软删除的平台列表，供所有需要"选择平台"下拉框的路由复用。"""
    repo = PlatformRepo(db)
    return await repo.find_all_active()