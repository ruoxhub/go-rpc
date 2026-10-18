"""TikTok videoDetail 解析器测试。

运行方式:
    pytest tests/parser/test_tiktok_video_detail.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

from parser import general_parser
from parser.tiktok.videoDetail import parse_video_detail

DATA_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "tiktok_video_detail.json"


def _load_sample() -> dict:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_parse_video_detail_yields_content_with_download_media_urls():
    items = list(parse_video_detail(_load_sample()))

    kinds = [it["datatype"] for it in items]
    assert "content" in kinds
    assert "media" not in kinds

    content = next(it for it in items if it["datatype"] == "content")
    # 来自 itemInfo.itemStruct.id
    assert content["content_id"] == "7666334648967925006"
    assert content["platform"] == "tiktok"
    assert content["user_id"] == "7511810578566939691"
    assert content["author"] == "cookdealz"
    # statsV2 字符串计数转为 int
    assert content["like_count"] == 13
    assert content["view_count"] == 3749
    assert content["comment_count"] == 0
    extend = json.loads(content["extend"])
    assert extend["video_url"]
    assert extend["music_url"]
    assert extend["pic_url"]


def test_parse_video_detail_extracts_ecommerce_products():
    product = {
        "product_id": 1732382240652365943,
        "title": "Summer Men's Basic Sporty Short Sleeve T-Shirt",
        "currency": "USD",
        "seller_id": 8654719205287759991,
        "source": "TikTok Shop",
        "seo_url": "https://www.tiktok.com/shop/pdp/product/1732382240652365943",
        "categories": [{"category_name": "T-shirts", "level": 3}],
        "skus": [{"sku_id": 1732382240652431479}],
    }
    anchor_item = {"id": "1732382240652365943", "extra": json.dumps(product)}
    data = {
        "itemInfo": {
            "itemStruct": {
                "id": "video-1",
                "author": {"id": "user-1"},
                "anchors": [{"extra": json.dumps([anchor_item])}],
            }
        }
    }

    items = list(parse_video_detail(data))

    content = next(it for it in items if it["datatype"] == "content")
    products = json.loads(content["extend"])["ecommerce_products"]

    assert len(products) == 1
    product = products[0]
    assert product["product_id"] == 1732382240652365943
    assert product["seller_id"] == 8654719205287759991
    assert product["currency"] == "USD"
    assert product["source"] == "TikTok Shop"
    assert product["seo_url"].startswith("https://www.tiktok.com/shop/pdp/")
    assert product["categories"][-1]["category_name"] == "T-shirts"
    assert len(product["skus"]) == 1


def test_parse_video_detail_uses_item_info_path():
    """标准详情接口返回 itemInfo.itemStruct，应从此路径解析。"""
    data = {
        "itemInfo": {
            "itemStruct": {
                "id": "999",
                "desc": "via itemStruct",
                "author": {"id": "u1", "uniqueId": "u", "nickname": "N"},
                "video": {"cover": "c", "playAddr": "v.mp4"},
                "music": {"playUrl": "a.mp3"},
                "statsV2": {"diggCount": "7"},
            }
        }
    }
    items = list(parse_video_detail(data))
    assert items[0]["content_id"] == "999"
    assert items[0]["like_count"] == 7
    assert items[0]["pub_time"] is None


def test_parse_video_detail_falls_back_to_item_list():
    """无 itemInfo 时回退到 itemList 形式。"""
    data = {
        "itemList": [
            {
                "id": "abc",
                "author": {"id": "u2"},
                "video": {"cover": "c", "playAddr": "v.mp4"},
                "statsV2": {"diggCount": "3"},
            }
        ]
    }
    items = list(parse_video_detail(data))
    assert items[0]["content_id"] == "abc"


def test_parse_video_detail_handles_empty():
    assert list(parse_video_detail({})) == []
    assert list(parse_video_detail(None)) == []


def test_general_parser_registers_video_detail():
    items = list(
        general_parser.parse("tiktok", _load_sample(), "videoDetail", as_dto=False)
    )
    assert any(it["datatype"] == "content" for it in items)
    assert not any(it["datatype"] == "media" for it in items)
