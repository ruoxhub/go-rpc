import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock
from parser.parser import general_parser
from pipeline import CrawlerPipeline
from models import BusContent, BusUser

DATA_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "twitter_search_timeline.json"
TWITTER_PARSER_PACKAGE = Path(__file__).resolve().parents[2] / "app" / "parser" / "twitter"
requires_twitter_parser = pytest.mark.skipif(
    not TWITTER_PARSER_PACKAGE.is_dir(),
    reason="parser.twitter 生产解析器包尚未实现；实现后此测试会自动启用",
)


@requires_twitter_parser
def test_parse_search_timeline():
    # 读取样例 JSON 文件
    with DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    # 运行解析器
    results = list(general_parser.parse("twitter", data, "SearchTimeline", as_dto=False))

    # 验证解析结果
    assert len(results) > 0

    contents = [r for r in results if r.get("datatype") == "content"]
    users = [r for r in results if r.get("datatype") == "user"]

    assert len(contents) > 0
    assert len(users) > 0

    # 检查具体的解析字段
    first_tweet = contents[0]
    assert first_tweet["content_id"] == "2056602750427844804"
    assert first_tweet["user_id"] == "743780794997547008"
    assert "Life is short I use python" in first_tweet["content"]
    assert first_tweet["author"] == "PythonDvz"
    assert first_tweet["platform"] == "twitter"

    first_user = users[0]
    assert first_user["user_id"] == "743780794997547008"
    assert first_user["username"] == "PythonDvz"
    assert first_user["name"] == "Python Developer"

@pytest.mark.asyncio
@requires_twitter_parser
async def test_search_timeline_pipeline_insertion():
    # 读取样例数据
    with DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    # 1. 解析为 DTO/Dict，然后映射为 ORM Model
    raw_items = list(general_parser.parse("twitter", data, "SearchTimeline", as_dto=True))
    assert len(raw_items) > 0

    # 模拟 Worker 将 ParsedItem 转为 ORM 模型实例的过程
    orm_items = []
    for item in raw_items:
        # ParsedItem 的类型标记在 kind 中
        model_cls = CrawlerPipeline.DATATYPE_TO_MODEL.get(item.kind)
        if model_cls:
            # 过滤掉不存在的列/字段
            orm_data = {
                k: v for k, v in item.data.to_dict().items()
                if k in model_cls.__table__.columns
            }
            # 补充 datatype 与 platform，以便 pipeline 正确识别
            orm_data["datatype"] = item.kind
            orm_data["platform"] = "twitter"
            orm_items.append(model_cls(**orm_data))

    assert len(orm_items) > 0

    # 2. 模拟布隆过滤器和数据库写入
    mock_bloom = MagicMock()
    # 模拟 abatch_check：全部返回 False 表示都不存在，都需要 insert
    mock_bloom.abatch_check = AsyncMock(side_effect=lambda vals, prefix: {v: False for v in vals})
    mock_bloom.abatch_add = AsyncMock()

    mock_db = MagicMock()
    mock_db.abulk_upsert = AsyncMock()
    mock_db.abulk_update = AsyncMock()

    # 3. 初始化 pipeline 并进行处理
    pipeline = CrawlerPipeline(filter=mock_bloom, store=mock_db)
    stats = await pipeline.process_items(orm_items)

    # 4. 验证入库统计
    assert stats["inserted"] > 0
    assert stats["errors"] == 0
    assert stats["skipped"] == 0

    # 5. 验证是否调用了 db 的幂等批量写入
    mock_db.abulk_upsert.assert_called_once()
    mock_bloom.abatch_add.assert_called()
