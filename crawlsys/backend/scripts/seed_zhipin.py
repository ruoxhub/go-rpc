"""Seed the Boss 直聘 (zhipin) platform: platform row, actions, keywords, tasks.

幂等：平台/动作/关键词/任务均按唯一键 upsert/跳过，可重复执行。
依赖 go-rpc 的 zhipin group 在线（任务执行时才需要，seed 本身不调用 RPC）。

用法:
    uv run python scripts/seed_zhipin.py
    uv run python scripts/seed_zhipin.py --keywords "爬虫工程师,Python后端,数据分析"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in sys.path:
    sys.path.append(_APP_DIR)

from sqlalchemy import select, text
from core.config import SchedulerConfig
from storage import SQLAlchemyDB
from models import SiteSource, PlatformStatus, Action, BusTask, BusiSearchKeyword
from models.task import TaskStatus
from models.task_config import (
    DatabaseSourceConfig,
    DatabaseSinkConfig,
    PaginationConfig,
    TaskConfig,
)

PLATFORM = "zhipin"

SEARCH_PARAMS_SCHEMA = json.dumps(
    [
        {"name": "keyword", "type": "string", "required": False, "default": None, "description": "搜索关键词"},
        {"name": "city", "type": "string", "required": False, "default": "全国", "description": "城市名称"},
        {"name": "page", "type": "number", "required": False, "default": 1, "description": "页码"},
        {"name": "size", "type": "number", "required": False, "default": 15, "description": "每页数量"},
        {"name": "experience", "type": "string", "required": False, "default": None, "description": "经验要求"},
        {"name": "degree", "type": "string", "required": False, "default": None, "description": "学历要求"},
        {"name": "salary", "type": "string", "required": False, "default": None, "description": "薪资范围"},
        {"name": "industry", "type": "string", "required": False, "default": None, "description": "行业"},
        {"name": "scale", "type": "string", "required": False, "default": None, "description": "公司规模"},
        {"name": "stage", "type": "string", "required": False, "default": None, "description": "融资阶段"},
        {"name": "jobType", "type": "string", "required": False, "default": None, "description": "工作类型"},
        {"name": "position", "type": "string", "required": False, "default": None, "description": "职位类别/方向"},
        {"name": "multiSubway", "type": "string", "required": False, "default": None, "description": "地铁线路"},
        {"name": "multiBusinessDistrict", "type": "string", "required": False, "default": None, "description": "商圈"},
        {"name": "expectInfo", "type": "string", "required": False, "default": None, "description": "求职期望信息"},
    ],
    ensure_ascii=False,
)

DETAIL_PARAMS_SCHEMA = json.dumps(
    [
        {"name": "securityId", "type": "string", "required": True, "default": None, "description": "安全ID"},
        {"name": "lid", "type": "string", "required": True, "default": None, "description": "链接ID"},
    ],
    ensure_ascii=False,
)


def _search_task_config() -> TaskConfig:
    return TaskConfig(
        pagination=PaginationConfig(
            max_pages=5,
            response_cursor_keys=["cursor", "page", "maxCursor", "nextCursor", "next_cursor"],
        ),
        sink=DatabaseSinkConfig(mode="standard"),
    )


def _detail_task_config() -> TaskConfig:
    """detail 由 search 产出写入 t_busi_job 的职位反查；本轮 seed 不启用 detail 任务。

    detail 依赖每个职位的 securityId/lid（search 响应才有），且当前 zhipin
    搜索已被风控（code=37）。先仅 seed search 常驻任务；detail 任务在 search
    数据落地、风控解除后按需补充。
    """
    return None


async def seed(db: SQLAlchemyDB, keywords: list[str]) -> None:
    async with db.asession_scope() as session:
        # 1) platform
        platform = (
            await session.execute(
                select(SiteSource).where(SiteSource.bs_platform_code == PLATFORM)
            )
        ).scalar_one_or_none()
        if platform is None:
            platform = SiteSource(
                bs_name="Boss直聘",
                bs_platform_code=PLATFORM,
                bs_url="https://www.zhipin.com/",
                bs_status=PlatformStatus.ENABLED,
                bs_concurrency=1,
                bs_rps=1.0,
                bs_burst=3,
                bs_cooldown=600,
            )
            session.add(platform)
            await session.flush()
            print(f"seeded platform {PLATFORM} bs_id={platform.bs_id}")
        else:
            print(f"platform {PLATFORM} exists bs_id={platform.bs_id}")

        # 2) actions
        action_specs = [
            ("search", "搜索职位", SEARCH_PARAMS_SCHEMA),
            ("detail", "职位详情", DETAIL_PARAMS_SCHEMA),
        ]
        for name, desc, schema in action_specs:
            action = (
                await session.execute(
                    select(Action).where(
                        Action.bs_id == platform.bs_id, Action.ba_action == name
                    )
                )
            ).scalar_one_or_none()
            if action is None:
                action = Action(
                    bs_id=platform.bs_id,
                    ba_action=name,
                    ba_desc=desc,
                    ba_params_schema=schema,
                    ba_enabled=True,
                )
                session.add(action)
                await session.flush()
                print(f"seeded action {name} ba_id={action.ba_id}")
            else:
                print(f"action {name} exists ba_id={action.ba_id}")

        # 3) keywords
        for kw in keywords:
            exists = (
                await session.execute(
                    select(BusiSearchKeyword.id).where(
                        BusiSearchKeyword.platform == PLATFORM,
                        BusiSearchKeyword.keyword == kw,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(BusiSearchKeyword(platform=PLATFORM, keyword=kw))
                print(f"seeded keyword {kw!r}")
            else:
                print(f"keyword {kw!r} exists")

        # 4) tasks: search (keyword-driven) and detail (job-driven)
        async def _upsert_task(action_name: str, config: TaskConfig) -> None:
            task = (
                await session.execute(
                    select(BusTask).where(
                        BusTask.platform == PLATFORM, BusTask.action == action_name
                    )
                )
            ).scalar_one_or_none()
            if task is None:
                session.add(
                    BusTask(
                        platform=PLATFORM,
                        action=action_name,
                        ba_id=action_name_map[action_name],
                        platform_id=platform.bs_id,
                        status=TaskStatus.PENDING,
                        config=config,
                    )
                )
                print(f"seeded task {PLATFORM}/{action_name}")
            else:
                print(f"task {PLATFORM}/{action_name} exists")

        action_name_map = {}
        rows = (
            await session.execute(
                select(Action).where(Action.bs_id == platform.bs_id)
            )
        ).scalars().all()
        for row in rows:
            action_name_map[row.ba_action] = row.ba_id

        await _upsert_task("search", _search_task_config())
        detail_config = _detail_task_config()
        if detail_config is not None:
            await _upsert_task("detail", detail_config)


async def main(keywords: list[str]) -> None:
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username, password=pg.password, host=pg.host,
        port=pg.port, database=pg.database, amode=True, driver="postgresql",
    )
    await db.aconnect()
    try:
        await seed(db, keywords)
    finally:
        await db.aclose()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seed Boss直聘 平台/动作/关键词/任务")
    p.add_argument("--keywords", default="爬虫工程师", help="逗号分隔的关键词")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    kw_list = [k.strip() for k in args.keywords.split(",") if k.strip()]
    asyncio.run(main(kw_list))
