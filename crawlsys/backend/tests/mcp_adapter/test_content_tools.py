"""内容 MCP 适配工具测试。"""

from datetime import datetime

import pytest

from core.config import McpConfig
from mcp_adapter.context import McpAppResources
from mcp_adapter.content_tools import get_content, list_contents
from mcp_adapter.schemas import ToolErrorCode, ToolResponse, encode_cursor
from models.content import Content


async def add_content(
    db,
    *,
    platform: str = "tiktok",
    content_id: str,
    pub_time: datetime | None,
    title: str | None = None,
    content: str = "full body",
    extend: str = '{"private": true}',
):
    async with db.asession_scope() as session:
        row = Content(
            platform=platform,
            content_id=content_id,
            data_type="3",
            title=title or content_id,
            content=content,
            description=f"description {content_id}",
            user_id=f"author-{content_id}",
            extend=extend,
            pub_time=pub_time,
            created_time=pub_time or datetime(2026, 8, 6, 9, 0),
            updated_time=pub_time or datetime(2026, 8, 6, 9, 0),
        )
        session.add(row)
        await session.flush()
        return row.id


@pytest.fixture
def resources(content_db):
    return McpAppResources(db=content_db, minio=object(), config=McpConfig())


@pytest.mark.asyncio
async def test_get_content_uses_exact_platform_and_content_id(resources, content_db):
    when = datetime(2026, 8, 6, 10, 0)
    await add_content(content_db, platform="tiktok", content_id="shared", pub_time=when)
    await add_content(content_db, platform="youtube", content_id="shared", pub_time=when)

    response = await get_content(resources, "youtube", "shared")

    assert isinstance(response, ToolResponse)
    assert response.data.platform == "youtube"
    assert response.data.content_id == "shared"
    assert response.data.content == "full body"
    assert response.data.extend == '{"private": true}'


@pytest.mark.asyncio
async def test_get_content_returns_safe_not_found_error(resources):
    response = await get_content(resources, "tiktok", "missing")

    assert response.ok is False
    assert response.error.code is ToolErrorCode.CONTENT_NOT_FOUND


@pytest.mark.asyncio
async def test_list_contents_filters_platform_and_uses_summary_only(resources, content_db):
    when = datetime(2026, 8, 6, 10, 0)
    await add_content(content_db, platform="tiktok", content_id="first", pub_time=when)
    await add_content(content_db, platform="youtube", content_id="second", pub_time=when)

    response = await list_contents(resources, platform="tiktok")

    assert isinstance(response, ToolResponse)
    assert [item.content_id for item in response.data] == ["first"]
    assert response.data[0].model_dump() == {
        "id": response.data[0].id,
        "platform": "tiktok",
        "content_id": "first",
        "content_type": "3",
        "title": "first",
        "desc": "description first",
        "author_id": "author-first",
        "pub_time": when,
        "created_time": when,
        "updated_time": when,
    }


@pytest.mark.asyncio
async def test_list_contents_filters_published_time_with_closed_interval(resources, content_db):
    start = datetime(2026, 8, 6, 10, 0)
    await add_content(content_db, content_id="before", pub_time=datetime(2026, 8, 6, 9, 59))
    await add_content(content_db, content_id="start", pub_time=start)
    await add_content(content_db, content_id="end", pub_time=datetime(2026, 8, 6, 11, 0))
    await add_content(content_db, content_id="after", pub_time=datetime(2026, 8, 6, 11, 1))
    await add_content(content_db, content_id="no-time", pub_time=None)

    response = await list_contents(
        resources,
        published_from=start,
        published_to=datetime(2026, 8, 6, 11, 0),
    )

    assert [item.content_id for item in response.data] == ["end", "start"]


@pytest.mark.asyncio
async def test_list_contents_uses_keyset_pagination_for_duplicate_timestamps(resources, content_db):
    newest = datetime(2026, 8, 6, 12, 0)
    duplicate = datetime(2026, 8, 6, 11, 0)
    oldest = await add_content(content_db, content_id="oldest", pub_time=datetime(2026, 8, 6, 10, 0))
    second = await add_content(content_db, content_id="duplicate-low", pub_time=duplicate)
    third = await add_content(content_db, content_id="duplicate-high", pub_time=duplicate)
    fourth = await add_content(content_db, content_id="newest", pub_time=newest)

    first_page = await list_contents(resources, limit=2)
    second_page = await list_contents(resources, limit=2, cursor=first_page.meta["next_cursor"])

    assert [item.id for item in first_page.data] == [fourth, third]
    assert first_page.meta == {"has_more": True, "limit": 2, "next_cursor": first_page.meta["next_cursor"]}
    assert [item.id for item in second_page.data] == [second, oldest]
    assert second_page.meta == {"has_more": False, "limit": 2, "next_cursor": None}


@pytest.mark.asyncio
async def test_list_contents_rejects_a_cursor_from_another_tool(resources):
    cursor = encode_cursor("analysis-list-v1", datetime(2026, 8, 6, 10, 0), 1)

    response = await list_contents(resources, cursor=cursor)

    assert response.ok is False
    assert response.error.code is ToolErrorCode.INVALID_CURSOR


@pytest.mark.asyncio
async def test_list_contents_includes_null_publish_times_after_dated_content(resources, content_db):
    dated = await add_content(
        content_db,
        content_id="dated",
        pub_time=datetime(2026, 8, 6, 10, 0),
    )
    null_time = await add_content(content_db, content_id="null-time", pub_time=None)

    response = await list_contents(resources)

    assert [item.id for item in response.data] == [dated, null_time]


@pytest.mark.asyncio
async def test_list_contents_pages_from_dated_content_into_null_publish_time_section(resources, content_db):
    dated = await add_content(
        content_db,
        content_id="dated",
        pub_time=datetime(2026, 8, 6, 10, 0),
    )
    null_low_id = await add_content(content_db, content_id="null-low", pub_time=None)
    null_high_id = await add_content(content_db, content_id="null-high", pub_time=None)

    first_page = await list_contents(resources, limit=1)
    second_page = await list_contents(resources, limit=1, cursor=first_page.meta["next_cursor"])
    third_page = await list_contents(resources, limit=1, cursor=second_page.meta["next_cursor"])

    assert [item.id for item in first_page.data] == [dated]
    assert [item.id for item in second_page.data] == [null_high_id]
    assert [item.id for item in third_page.data] == [null_low_id]
    assert third_page.meta["has_more"] is False


@pytest.mark.asyncio
async def test_list_contents_selects_only_summary_columns(resources, content_db):
    await add_content(content_db, content_id="summary", pub_time=datetime(2026, 8, 6, 10, 0))
    content_db.statements.clear()

    await list_contents(resources)

    query = next(statement for statement in content_db.statements if statement.startswith("SELECT"))
    selected_columns = query.split("FROM", maxsplit=1)[0]
    assert "t_busi_content.content," not in selected_columns
    assert "t_busi_content.extend" not in selected_columns
