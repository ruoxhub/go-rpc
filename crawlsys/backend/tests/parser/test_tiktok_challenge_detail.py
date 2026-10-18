"""TikTok challengeDetail 解析器与 pipeline 注册测试。

运行方式:
    pytest tests/parser/test_tiktok_challenge_detail.py -v
"""
from __future__ import annotations

from models import TkChallenge
from core.constants import (
    DATATYPE_TO_MODEL,
    UNIQUE_FIELD_MAPPING,
    UPDATE_FIELD_MAPPING,
)
from parser import general_parser
from parser.tiktok.challengeDetail import parse_challenge_detail

SAMPLE_RESPONSE = {
    "challengeInfo": {
        "challenge": {
            "id": "870345",
            "title": "menswear",
            "desc": "",
            "isCommerce": False,
            "stats": {"videoCount": 0, "viewCount": 24400000000},
        },
        "statsV2": {"videoCount": "2410696", "viewCount": "24438514924"},
    },
    "code": 0,
    "message": "success",
}


def test_parser_yields_challenge_dict():
    items = list(parse_challenge_detail(SAMPLE_RESPONSE))
    assert len(items) == 1
    it = items[0]
    assert it["datatype"] == "challenge"
    assert it["challenge_id"] == "870345"
    assert it["title"] == "menswear"
    assert it["desc"] == ""
    assert it["is_commerce"] is False
    # 优先采用 challengeInfo.statsV2 的字符串计数
    assert it["video_count"] == "2410696"
    assert it["view_count"] == "24438514924"


def test_parser_handles_missing_challenge():
    assert list(parse_challenge_detail({})) == []
    assert list(parse_challenge_detail({"challengeInfo": {}})) == []
    # 有 challengeInfo 但 challenge 无 id 也应安全跳过
    assert list(parse_challenge_detail({"challengeInfo": {"challenge": {"title": "x"}}})) == []


def test_parser_falls_back_to_challenge_stats_v2():
    """statsV2 缺失时回退到 challenge 层级的 statsV2。"""
    data = {
        "challengeInfo": {
            "challenge": {
                "id": "1",
                "title": "t",
                "statsV2": {"videoCount": "10", "viewCount": "20"},
            }
        }
    }
    it = list(parse_challenge_detail(data))[0]
    assert it["video_count"] == "10"
    assert it["view_count"] == "20"


def test_tkchallenge_registered_in_pipeline():
    """TkChallenge 必须注册到 pipeline 注册表, 否则 standard sink 写不进 tk_challenge。"""
    assert DATATYPE_TO_MODEL.get("challenge") is TkChallenge
    assert UNIQUE_FIELD_MAPPING.get("challenge") == "challenge_id"
    assert UPDATE_FIELD_MAPPING.get("challenge") == [
        "title", "desc", "is_commerce", "video_count", "view_count",
    ]


def test_parser_dict_builds_model():
    it = list(parse_challenge_detail(SAMPLE_RESPONSE))[0]
    model = TkChallenge(**it)
    assert model.challenge_id == "870345"
    assert model.title == "menswear"
    assert model.video_count == "2410696"


def test_general_parser_default_returns_challenge_dto():
    item = list(general_parser.parse("tiktok", SAMPLE_RESPONSE, "challengeDetail"))[0]

    assert item.kind == "challenge"
    assert item.data.challenge_id == "870345"
    assert item.data.title == "menswear"
