"""Seed an enabled platform into t_busi_platform.

The scheduler refuses to start when there are no enabled platforms
(bs_status='1' AND bs_platform_code IS NOT NULL). Because the JSON API
service is started only *after* that check, you cannot configure a platform
through the API on a fresh database — hence this seed script.

Usage:
    uv run python scripts/seed_platform.py --code bilibili --name B站
    uv run python scripts/seed_platform.py --code douyin --name 抖音
    uv run python scripts/seed_platform.py            # defaults: bilibili / B站

The platform code must match what the go-rpc engine and your tasks use.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Match the official backend entrypoint when run as `python scripts/seed_platform.py`.
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in sys.path:
    sys.path.append(_APP_DIR)

from core.config import SchedulerConfig
from storage import SQLAlchemyDB
from models import SiteSource, PlatformStatus
from common.logging import get_logger

logger = get_logger(__file__)


async def seed(
    code: str,
    name: str,
    url: str | None = None,
    concurrency: int = 1,
    rps: float = 1.0,
    burst: int = 3,
    cooldown: int = 300,
) -> None:
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql

    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    await db.aconnect()

    try:
        # Idempotent: skip if a platform with the same code already exists.
        existing = await SiteSource.load_quota_by_code(db, code)
        if existing is not None:
            logger.info("Platform '%s' already exists (bs_status=%s); nothing to do.", code, PlatformStatus.ENABLED)
            return

        platform = SiteSource(
            bs_name=name,
            bs_platform_code=code,
            bs_url=url,
            bs_status=PlatformStatus.ENABLED,
            bs_concurrency=concurrency,
            bs_rps=rps,
            bs_burst=burst,
            bs_cooldown=cooldown,
        )
        async with db.asession_scope() as session:
            session.add(platform)
            await session.commit()

        logger.info(
            "Seeded enabled platform: code=%s name=%s (concurrency=%d rps=%.2f burst=%d cooldown=%ds)",
            code, name, concurrency, rps, burst, cooldown,
        )
    finally:
        await db.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed an enabled platform into t_busi_platform.")
    parser.add_argument("--code", default="bilibili", help="Platform code (bs_platform_code), e.g. bilibili/douyin")
    parser.add_argument("--name", default="B站", help="Platform display name (bs_name)")
    parser.add_argument("--url", default=None, help="Optional site URL (bs_url)")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument("--burst", type=int, default=3)
    parser.add_argument("--cooldown", type=int, default=300)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    asyncio.run(seed(
        code=args.code,
        name=args.name,
        url=args.url,
        concurrency=args.concurrency,
        rps=args.rps,
        burst=args.burst,
        cooldown=args.cooldown,
    ))


if __name__ == "__main__":
    main()
