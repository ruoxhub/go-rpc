"""TikTok 话题 (TkChallenge) 解析与入库测试。

运行方式:
    # 仅解析/校验 (无需数据库)
    pytest tests/models/test_tiktok.py -k "parse or schema" -v

    # 含真实入库往返 (需可达的 PostgreSQL)
    # 默认读取项目 config.toml 的 [postgresql] 段；也可用环境变量覆盖:
    #   TEST_DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db pytest tests/models/test_tiktok.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models.tiktok import TkChallenge, TkChallengeCreate, TkChallengeResponse

# 用户提供的真实接口返回样例
SAMPLE_RESPONSE = {
    "challengeInfo": {
        "challenge": {
            "coverLarger": "",
            "coverMedium": "",
            "coverThumb": "",
            "desc": "",
            "id": "870345",
            "isCommerce": False,
            "profileLarger": "",
            "profileMedium": "",
            "profileThumb": "",
            "stats": {"videoCount": 0, "viewCount": 24400000000},
            "title": "menswear",
        },
        "challengeAnnouncement": {"body": "", "title": ""},
        "stats": {"videoCount": 0, "viewCount": 24400000000},
        "statsV2": {"videoCount": "2410696", "viewCount": "24438514924"},
    },
    "clientId": "vhbvh9a0t",
    "code": 0,
    "extra": {"fatal_item_ids": [], "logid": "x", "now": 1784613662000},
    "group": "tiktok",
    "log_pb": {"impr_id": "x"},
    "message": "success",
    "shareMeta": {"desc": "Watch awesome short videos", "title": "#menswear on TikTok"},
    "statusCode": 0,
    "status_code": 0,
    "status_msg": "",
    "trace_id": "04e5c3ebb25afb5c89f2225025d4fbca",
}


def _expected_obj() -> TkChallenge:
    return TkChallenge.from_api_response(SAMPLE_RESPONSE)


# ===================== 解析 =====================

def test_from_api_response_parses_sample():
    obj = _expected_obj()
    assert obj.challenge_id == "870345"
    assert obj.title == "menswear"
    assert obj.desc == ""            # 空字符串, 可入库 (nullable Text)
    assert obj.is_commerce is False
    # statsV2 在 challengeInfo 层级, 解析逻辑应正确回退取到
    assert obj.video_count == "2410696"
    assert obj.view_count == "24438514924"


def test_from_api_response_handles_missing_stats_v2():
    """当接口未返回 statsV2 时, 统计字段应为 None 而非报错。"""
    data = {"challengeInfo": {"challenge": {"id": "1", "title": "t"}}}
    obj = TkChallenge.from_api_response(data)
    assert obj.challenge_id == "1"
    assert obj.video_count is None
    assert obj.view_count is None


# ===================== Pydantic 校验 =====================

def test_create_schema_validates_parsed_obj():
    obj = _expected_obj()
    dto = TkChallengeCreate.model_validate(obj, from_attributes=True)
    assert dto.challenge_id == "870345"
    assert dto.title == "menswear"
    assert dto.video_count == "2410696"
    assert dto.view_count == "24438514924"


def test_response_schema_serializes():
    # Response schema 含 IDMixin(id:int)/TimeMixin, 仅对持久化后的行有效
    resp = TkChallengeResponse.model_validate({
        "id": 1,
        "created_time": None,
        "updated_time": None,
        "challenge_id": "870345",
        "title": "menswear",
        "desc": "",
        "is_commerce": False,
        "video_count": "2410696",
        "view_count": "24438514924",
    })
    dumped = resp.model_dump()
    assert dumped["id"] == 1
    assert dumped["challenge_id"] == "870345"
    assert "created_time" in dumped


# ===================== 入库 (真实 PostgreSQL) =====================

def _db_url() -> str | None:
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url
    cfg = Path(__file__).resolve().parents[2] / "config.toml"
    if cfg.exists():
        try:
            import tomllib

            raw = tomllib.load(cfg.open("rb")).get("postgresql", {})
            if raw.get("username") and raw.get("database"):
                pw = os.environ.get("CRAWLER_PG_PASSWORD", raw.get("password", ""))
                return (
                    f"postgresql+psycopg2://{raw['username']}:{pw}"
                    f"@{raw.get('host','localhost')}:{raw.get('port',5432)}/{raw['database']}"
                )
        except Exception:
            return None
    return None


@pytest.fixture(scope="module")
def engine():
    url = _db_url()
    if not url:
        pytest.skip("未配置 PostgreSQL (设置 TEST_DATABASE_URL 或在 config.toml 配置 [postgresql])")
    try:
        eng = create_engine(url, pool_pre_ping=True)
        eng.connect().close()
    except Exception as e:
        pytest.skip(f"PostgreSQL 不可达, 跳过入库测试: {type(e).__name__}: {e}")
    # 确保表存在 (幂等)
    TkChallenge.__table__.create(eng, checkfirst=True)
    yield eng
    eng.dispose()


def test_insert_and_read_roundtrip(engine):
    cid = "870345"
    # 幂等: 先清理可能存在的旧行, 避免唯一约束冲突
    with Session(engine) as s:
        old = s.scalar(select(TkChallenge).where(TkChallenge.challenge_id == cid))
        if old:
            s.delete(old)
            s.commit()

    with Session(engine) as s:
        s.add(TkChallenge.from_api_response(SAMPLE_RESPONSE))
        s.commit()

    with Session(engine) as s:
        row = s.scalar(select(TkChallenge).where(TkChallenge.challenge_id == cid))
        assert row is not None
        assert row.title == "menswear"
        assert row.video_count == "2410696"
        assert row.view_count == "24438514924"
        assert row.is_commerce is False
        # 清理, 保持测试可重复
        s.delete(row)
        s.commit()
