"""Read-only MCP adapter tools for collected content."""

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select

from mcp_adapter.context import McpAppResources
from mcp_adapter.errors import map_tool_error
from mcp_adapter.observability import observe_tool_call
from mcp_adapter.schemas import (
    ContentDetail,
    ContentSummary,
    PageMeta,
    ToolResponse,
    decode_cursor,
    encode_cursor,
)
from models.content import Content


_CONTENT_LIST_CURSOR_KIND = "content-list-v1"
_NULL_PUB_TIME_CURSOR_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)


@observe_tool_call("get_content", resource="content")
async def get_content(
    resources: McpAppResources,
    platform: str,
    content_id: str,
):
    """Return one content record identified by its platform-local id."""
    try:
        async with resources.db.asession_scope() as session:
            content = await session.scalar(
                select(Content).where(
                    Content.platform == platform,
                    Content.content_id == content_id,
                )
            )
        if content is None:
            raise FileNotFoundError
        return ToolResponse(data=ContentDetail.model_validate(content))
    except Exception as exc:
        return map_tool_error(exc, resource="content")


@observe_tool_call("list_contents", resource="content")
async def list_contents(
    resources: McpAppResources,
    platform: str | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    limit: int = 20,
    cursor: str | None = None,
):
    """Return published content summaries in stable newest-first cursor order."""
    try:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        cursor_position = (
            decode_cursor(_CONTENT_LIST_CURSOR_KIND, cursor) if cursor is not None else None
        )
        filters = []
        if platform is not None:
            filters.append(Content.platform == platform)
        if published_from is not None:
            filters.append(Content.pub_time >= published_from)
        if published_to is not None:
            filters.append(Content.pub_time <= published_to)
        if cursor_position is not None:
            cursor_time, cursor_id = cursor_position
            if cursor_time == _NULL_PUB_TIME_CURSOR_TIMESTAMP:
                filters.append(
                    and_(
                        Content.pub_time.is_(None),
                        Content.id < cursor_id,
                    )
                )
            else:
                filters.append(
                    or_(
                        Content.pub_time < cursor_time,
                        Content.pub_time.is_(None),
                        and_(Content.pub_time == cursor_time, Content.id < cursor_id),
                    )
                )

        statement = (
            select(
                Content.id,
                Content.platform,
                Content.content_id,
                Content.data_type.label("content_type"),
                Content.title,
                Content.description.label("desc"),
                Content.user_id.label("author_id"),
                Content.pub_time,
                Content.created_time,
                Content.updated_time,
            )
            .where(*filters)
            .order_by(Content.pub_time.desc().nulls_last(), Content.id.desc())
            .limit(limit + 1)
        )
        async with resources.db.asession_scope() as session:
            rows = list((await session.execute(statement)).all())

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = (
            encode_cursor(
                _CONTENT_LIST_CURSOR_KIND,
                page_rows[-1]._mapping["pub_time"] or _NULL_PUB_TIME_CURSOR_TIMESTAMP,
                page_rows[-1]._mapping["id"],
            )
            if has_more
            else None
        )
        return ToolResponse(
            data=[_to_content_summary(row) for row in page_rows],
            meta=PageMeta(
                has_more=has_more,
                limit=limit,
                next_cursor=next_cursor,
            ).model_dump(),
        )
    except Exception as exc:
        return map_tool_error(exc, resource="content")


def _to_content_summary(row) -> ContentSummary:
    content = row._mapping
    return ContentSummary(
        id=content["id"],
        platform=content["platform"] or "",
        content_id=content["content_id"] or "",
        content_type=content["content_type"] or "",
        title=content["title"],
        desc=content["desc"],
        author_id=content["author_id"],
        pub_time=content["pub_time"],
        created_time=content["created_time"],
        updated_time=content["updated_time"],
    )
