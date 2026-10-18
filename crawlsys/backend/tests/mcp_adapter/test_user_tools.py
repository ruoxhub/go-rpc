"""用户 MCP 适配工具测试。"""

from datetime import datetime

import pytest

from core.config import McpConfig
from mcp_adapter.context import McpAppResources
from mcp_adapter.schemas import ToolErrorCode, ToolResponse, encode_cursor
from mcp_adapter.user_tools import get_user, list_users
from models.user import User


async def add_user(
    db,
    *,
    platform: str = "tiktok",
    user_id: str,
    username: str | None = None,
    created_time: datetime | None = None,
    extend: str = '{"private": true}',
):
    when = created_time or datetime(2026, 8, 6, 9, 0)
    async with db.asession_scope() as session:
        row = User(
            platform=platform,
            user_id=user_id,
            username=username or f"user-{user_id}",
            name=f"name {user_id}",
            gender=1,
            email=f"{user_id}@example.com",
            avatar=f"https://example.test/avatar/{user_id}.png",
            follower_count=10,
            following_count=5,
            content_count=3,
            verified="blue",
            created_at=when,
            created_time=when,
            updated_time=when,
            extend=extend,
        )
        session.add(row)
        await session.flush()
        return row.id


@pytest.fixture
def resources(user_db):
    return McpAppResources(db=user_db, minio=object(), config=McpConfig())


@pytest.mark.asyncio
async def test_get_user_uses_exact_platform_and_user_id(resources, user_db):
    when = datetime(2026, 8, 6, 10, 0)
    await add_user(user_db, platform="tiktok", user_id="shared", created_time=when)
    await add_user(user_db, platform="youtube", user_id="shared", created_time=when)

    response = await get_user(resources, "youtube", "shared")

    assert isinstance(response, ToolResponse)
    assert response.data.platform == "youtube"
    assert response.data.user_id == "shared"
    assert response.data.username == "user-shared"
    assert response.data.follower_count == 10
    assert response.data.extend == '{"private": true}'


@pytest.mark.asyncio
async def test_get_user_returns_safe_not_found_error(resources):
    response = await get_user(resources, "tiktok", "missing")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.USER_NOT_FOUND


@pytest.mark.asyncio
async def test_list_users_filters_platform_and_username(resources, user_db):
    when = datetime(2026, 8, 6, 10, 0)
    await add_user(user_db, platform="tiktok", user_id="first", username="Alice", created_time=when)
    await add_user(user_db, platform="youtube", user_id="second", username="Bob", created_time=when)

    response = await list_users(resources, platform="tiktok", username="ali")

    assert isinstance(response, ToolResponse)
    assert [item.user_id for item in response.data] == ["first"]
    assert response.data[0].model_dump() == {
        "id": response.data[0].id,
        "platform": "tiktok",
        "user_id": "first",
        "avatar": f"https://example.test/avatar/first.png",
        "name": "name first",
        "username": "Alice",
        "follower_count": 10,
        "following_count": 5,
        "content_count": 3,
        "verified": "blue",
        "created_time": when,
        "updated_time": when,
    }


@pytest.mark.asyncio
async def test_list_users_uses_keyset_pagination_for_duplicate_timestamps(resources, user_db):
    newest = datetime(2026, 8, 6, 12, 0)
    duplicate = datetime(2026, 8, 6, 11, 0)
    oldest = await add_user(user_db, user_id="oldest", created_time=datetime(2026, 8, 6, 10, 0))
    second = await add_user(user_db, user_id="duplicate-low", created_time=duplicate)
    third = await add_user(user_db, user_id="duplicate-high", created_time=duplicate)
    fourth = await add_user(user_db, user_id="newest", created_time=newest)

    first_page = await list_users(resources, limit=2)
    second_page = await list_users(resources, limit=2, cursor=first_page.meta["next_cursor"])

    assert [item.id for item in first_page.data] == [fourth, third]
    assert first_page.meta == {"has_more": True, "limit": 2, "next_cursor": first_page.meta["next_cursor"]}
    assert [item.id for item in second_page.data] == [second, oldest]
    assert second_page.meta == {"has_more": False, "limit": 2, "next_cursor": None}


@pytest.mark.asyncio
async def test_list_users_rejects_a_cursor_from_another_tool(resources):
    cursor = encode_cursor("content-list-v1", datetime(2026, 8, 6, 10, 0), 1)

    response = await list_users(resources, cursor=cursor)

    assert response.ok is False
    assert response.error.code is ToolErrorCode.INVALID_CURSOR


@pytest.mark.asyncio
async def test_list_users_selects_only_summary_columns(resources, user_db):
    await add_user(user_db, user_id="summary", created_time=datetime(2026, 8, 6, 10, 0))
    user_db.statements.clear()

    await list_users(resources)

    query = next(statement for statement in user_db.statements if statement.startswith("SELECT"))
    selected_columns = query.split("FROM", maxsplit=1)[0]
    assert "t_busi_user.description" not in selected_columns
    assert "t_busi_user.extend" not in selected_columns
