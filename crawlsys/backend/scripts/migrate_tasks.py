"""One-time migration: import BILIBILI_TASKS into t_busi_action + t_crawl_task.

Usage:
    cd crawler && python -m scripts.migrate_tasks
Idempotent — safe to run multiple times.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import SchedulerConfig
from storage import SQLAlchemyDB
from models.platform import platformSource
from models.action import Action
from models.task import BusTask, TaskStatus
from sqlalchemy import select

BILIBILI_ACTIONS = [
    {
        "action": "getFeedRcmd",
        "desc": "获取首页推荐视频流",
        "api_url": "https://api.bilibili.com/x/web-interface/index/top/rcmd",
        "method": "GET",
        "task": {},
    },
    {
        "action": "getContent",
        "desc": "获取视频详细信息",
        "api_url": "https://api.bilibili.com/x/web-interface/view",
        "method": "GET",
        "task": {
            "ref_table": "t_busi_content",
            "ref_where": "is_detail IS NOT true",
            "params_columns": "content_id",
            "entity_column": "content_id",
            "post_update_column": "is_detail",
        },
    },
    {
        "action": "getVideoSubtitle",
        "desc": "获取视频字幕",
        "api_url": "https://api.bilibili.com/x/player/v2",
        "method": "GET",
        "task": {
            "ref_table": "t_busi_content",
            "ref_where": "is_detail = true AND subtitle_fetched IS NOT true AND extend::json->>'aid' IS NOT NULL AND extend::json->>'cid' IS NOT NULL",
            "params_columns": "content_id, extend::json->>'aid' as aid, extend::json->>'cid' as cid",
            "entity_column": "content_id",
            "result_column": "content",
            "post_update_column": "subtitle_fetched",
        },
    },
    {
        "action": "getComment",
        "desc": "获取视频评论",
        "api_url": "https://api.bilibili.com/x/v2/reply/main",
        "method": "GET",
        "task": {
            "ref_table": "t_busi_content",
            "ref_where": "is_detail = true AND comment_fetched IS NOT true AND extend::json->>'aid' IS NOT NULL",
            "params_columns": "content_id, extend::json->>'aid' as aid",
            "entity_column": "content_id",
            "post_update_column": "comment_fetched",
        },
    },
    {
        "action": "getUserInfo",
        "desc": "获取用户信息",
        "api_url": "https://api.bilibili.com/x/space/acc/info",
        "method": "GET",
        "task": {
            "ref_table": "t_busi_content",
            "ref_where": "user_id IS NOT NULL AND user_id != '' AND user_id NOT IN (SELECT user_id FROM t_busi_user WHERE platform = 'bilibili')",
            "params_columns": "DISTINCT user_id",
            "entity_column": "user_id",
            "post_update_column": "detail_fetched",
            "post_update_table": "t_busi_user",
        },
    },
]


async def migrate():
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username, password=pg.password,
        host=pg.host, port=pg.port, database=pg.database,
        amode=True, driver="postgresql",
    )
    await db.aconnect()
    await db.ainit_db()

    async with db.asession_scope() as session:
        result = await session.execute(
            select(platformSource).where(platformSource.bs_name == "bilibili")
        )
        platform = result.scalar_one_or_none()
        if not platform:
            print("ERROR: bilibili platform not found in t_busi_platform. Create it first.")
            return

        bs_id = platform.bs_id
        print(f"Found bilibili platform: bs_id={bs_id}")

        for item in BILIBILI_ACTIONS:
            action_name = item["action"]

            result = await session.execute(
                select(Action).where(Action.bs_id == bs_id, Action.ba_action == action_name)
            )
            action_obj = result.scalar_one_or_none()
            if not action_obj:
                action_obj = Action(
                    bs_id=bs_id,
                    ba_action=action_name,
                    ba_desc=item.get("desc"),
                    ba_api_url=item.get("api_url"),
                    ba_api_method=item.get("method"),
                    ba_enabled=True,
                )
                session.add(action_obj)
                await session.flush()
                print(f"  Created action: {action_name} (ba_id={action_obj.ba_id})")
            else:
                print(f"  Action exists: {action_name} (ba_id={action_obj.ba_id})")

            result = await session.execute(
                select(BusTask).where(BusTask.platform == "bilibili", BusTask.action == action_name)
            )
            task_obj = result.scalar_one_or_none()
            task_cfg = item["task"]
            if not task_obj:
                task_obj = BusTask(
                    platform="bilibili",
                    action=action_name,
                    ba_id=action_obj.ba_id,
                    status=TaskStatus.PENDING,
                    **{k: v for k, v in task_cfg.items()},
                )
                session.add(task_obj)
                print(f"    Created task for {action_name}")
            else:
                if not task_obj.ba_id:
                    task_obj.ba_id = action_obj.ba_id
                    print(f"    Updated task ba_id for {action_name}")
                else:
                    print(f"    Task exists for {action_name}")

    print("Migration complete.")
    await db.aclose()


if __name__ == "__main__":
    asyncio.run(migrate())
