"""本地 JSON 文件解析入库脚本。

用法:
    python scripts/import_local_json.py --file data/getUserFollowing.json \
        --platform tiktok --action getUserFollowing [--config config.toml]

流程: 读取 JSON → general_parser 解析 → 过滤模型合法列 → Pipeline (Bloom 去重 + upsert) 入库。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 保证以 `python scripts/import_local_json.py` 方式运行时可导入项目包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import SchedulerConfig
from core.constants import DATATYPE_TO_MODEL
from pipeline import CrawlerPipeline
from filter import Bloom
from parser import general_parser
from storage import SQLAlchemyDB
from common.logging import get_logger

logger = get_logger(__file__)


def _to_models(parsed_items: list[dict]) -> list:
    """dict → ORM 实例，仅保留模型表中存在的列，避免 wire 格式字段（如 url）引发 TypeError。"""
    models = []
    for item in parsed_items:
        model_cls = DATATYPE_TO_MODEL.get(item.get("datatype"))
        if not model_cls:
            logger.warning("未知 datatype: %s，跳过", item.get("datatype"))
            continue
        valid_cols = {c.name for c in model_cls.__table__.columns}
        clean = {k: v for k, v in item.items() if k in valid_cols}
        # TikTok 头像签名 URL 常超过 varchar(255)，列宽不足时截断；
        # 完整 URL 已保存在 extend 字段中。
        if len(clean.get("avatar") or "") > 255:
            clean["avatar"] = clean["avatar"][:255]
        models.append(model_cls(**clean))
    return models


async def run(file: str, platform: str, action: str, config_path: str) -> None:
    data = json.loads(Path(file).read_text(encoding="utf-8"))

    parsed = list(general_parser.parse(platform, data, action, as_dto=False))
    logger.info("解析完成: %d 条记录", len(parsed))
    if not parsed:
        return

    models = _to_models(parsed)
    logger.info("转换为 ORM 模型: %d 条", len(models))
    if not models:
        return

    config = SchedulerConfig.from_toml(config_path)
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
    await db.ainit_db()

    bloom = Bloom(redis_url=config.redis.url, amode=True)
    pipeline = CrawlerPipeline(filter=bloom, store=db)

    try:
        stats = await pipeline.process_items(models)
        logger.info(
            "入库完成: inserted=%d updated=%d skipped=%d errors=%d",
            stats["inserted"], stats["updated"], stats["skipped"], stats["errors"],
        )
    finally:
        await pipeline.close()
        await bloom.aclose()
        await db.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description="本地 JSON 文件解析入库")
    ap.add_argument("--file", required=True, help="JSON 文件路径")
    ap.add_argument("--platform", required=True, help="平台标识，如 tiktok")
    ap.add_argument("--action", required=True, help="解析器 action，如 getUserFollowing")
    ap.add_argument("--config", default="config.toml", help="配置文件路径")
    args = ap.parse_args()
    asyncio.run(run(args.file, args.platform, args.action, args.config))


if __name__ == "__main__":
    main()
