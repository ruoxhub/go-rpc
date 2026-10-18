"""Read-only MCP adapter tools for captured platform users."""

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select

from mcp_adapter.context import McpAppResources
from mcp_adapter.errors import map_tool_error
from mcp_adapter.observability import observe_tool_call
from mcp_adapter.schemas import (
    PageMeta,
    ToolResponse,
    UserDetail,
    UserSummary,
    decode_cursor,
    encode_cursor,
)
from models.user import User


_USER_LIST_CURSOR_KIND = "user-list-v1"
_NULL_CREATED_TIME_CURSOR_TIMESTAMP = datetime.min.replace(tzinfo=timezone.utc)


@observe_tool_call("get_user", resource="user")
async def get_user(
    resources: McpAppResources,
    platform: str,
    user_id: str,
):
    """Return one user record identified by its platform-local id."""
    try:
        async with resources.db.asession_scope() as session:
            user = await session.scalar(
                select(User).where(
                    User.platform == platform,
                    User.user_id == user_id,
                )
            )
        if user is None:
            raise FileNotFoundError
        return ToolResponse(data=UserDetail.model_validate(user))
    except Exception as exc:
        return map_tool_error(exc, resource="user")


@observe_tool_call("list_users", resource="user")
async def list_users(
    resources: McpAppResources,
    platform: str | None = None,
    username: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
):
    """Return user summaries in stable newest-first cursor order."""
    try:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        cursor_position = (
            decode_cursor(_USER_LIST_CURSOR_KIND, cursor) if cursor is not None else None
        )
        filters = []
        if platform is not None:
            filters.append(User.platform == platform)
        if username is not None:
            filters.append(User.username.ilike(f"%{username}%"))
        if cursor_position is not None:
            cursor_time, cursor_id = cursor_position
            if cursor_time == _NULL_CREATED_TIME_CURSOR_TIMESTAMP:
                filters.append(
                    and_(
                        User.created_time.is_(None),
                        User.id < cursor_id,
                    )
                )
            else:
                filters.append(
                    or_(
                        User.created_time < cursor_time,
                        User.created_time.is_(None),
                        and_(User.created_time == cursor_time, User.id < cursor_id),
                    )
                )

        statement = (
            select(
                User.id,
                User.platform,
                User.user_id,
                User.avatar,
                User.name,
                User.username,
                User.follower_count,
                User.following_count,
                User.content_count,
                User.verified,
                User.created_time,
                User.updated_time,
            )
            .where(*filters)
            .order_by(User.created_time.desc().nulls_last(), User.id.desc())
            .limit(limit + 1)
        )
        async with resources.db.asession_scope() as session:
            rows = list((await session.execute(statement)).all())

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = (
            encode_cursor(
                _USER_LIST_CURSOR_KIND,
                page_rows[-1]._mapping["created_time"] or _NULL_CREATED_TIME_CURSOR_TIMESTAMP,
                page_rows[-1]._mapping["id"],
            )
            if has_more
            else None
        )
        return ToolResponse(
            data=[_to_user_summary(row) for row in page_rows],
            meta=PageMeta(
                has_more=has_more,
                limit=limit,
                next_cursor=next_cursor,
            ).model_dump(),
        )
    except Exception as exc:
        return map_tool_error(exc, resource="user")


def _to_user_summary(row) -> UserSummary:
    user = row._mapping
    return UserSummary(
        id=user["id"],
        platform=user["platform"],
        user_id=user["user_id"],
        avatar=user["avatar"],
        name=user["name"],
        username=user["username"],
        follower_count=user["follower_count"],
        following_count=user["following_count"],
        content_count=user["content_count"],
        verified=user["verified"],
        created_time=user["created_time"],
        updated_time=user["updated_time"],
    )