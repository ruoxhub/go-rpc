"""Boss 直聘 (zhipin) parser unit tests."""
from __future__ import annotations

import pytest

import parser.zhipin  # noqa: F401  - register parsers
from parser.parser import general_parser


SEARCH_PAYLOAD = {
    "code": 0,
    "zpData": {
        "hasMore": True,
        "jobList": [
            {
                "jobName": "爬虫工程师（需本科学历）",
                "brandName": "中策大数据",
                "cityName": "深圳",
                "salaryDesc": "8-12K",
                "encryptJobId": "d64d714882904f7f0nJ92t-9EFBS",
                "securityId": "lK0VRDN63IPHr-Z1v5I-0blcRWvukihs9vzOmG0i4CGaMFCrS3PLbBbZsxc5FAJBWJGrOa2Bo-07QlFM2z9ftahZGiX-Q0bGnVWkU6cqgB19NNZQsow47sM0POmFQLdOoQ-XrHONIioW0qAdqoGL_PI_s7PS9hB32DyxKsc2f8sWEcJEF8AzJCXOAn-Nr7nKLqZnpsmvRYVF4Oq-ZN2Gt5BUfGe-WmCdL0gJN2gWs3bTuwfibaKJZN-v0C_Whkepjv3VS8WUkiI8l_Hf_gBSp47OMhbwabuOqdCn8SAJ_3yisqPFvL27bqOEcnwgfP_l-i8erVY~",
                "lid": "4hhKYXa2eaR.search.1",
                "jobExperience": "1-3年",
                "jobDegree": "本科",
                "brandIndustry": "互联网",
                "bossName": "蔡女士",
                "skills": ["爬虫开发经验", "Python"],
            }
        ]
    },
}

DETAIL_PAYLOAD = {
    "code": 0,
    "zpData": {
        "securityId": "sec-detail-1",
        "lid": "lid-detail-1",
        "jobInfo": {
            "encryptId": "detail-abc",
            "jobName": "后端工程师",
            "locationName": "上海",
            "salaryDesc": "20-25K",
            "jobDetail": "负责后端服务开发",
            "experienceName": "3-5年",
            "degreeName": "本科",
            "brandInfo": {"brandName": "测试科技"},
        },
        "brandComInfo": {"industryName": "互联网", "scaleName": "100-499人"},
        "bossInfo": {"name": "李经理", "title": "HR"},
    },
}


def _search():
    return list(
        general_parser.parse("zhipin", SEARCH_PAYLOAD, "search", as_dto=False)
    )


def _detail():
    return list(
        general_parser.parse("zhipin", DETAIL_PAYLOAD, "detail", as_dto=False)
    )


def test_search_produces_job_with_core_fields():
    records = _search()
    assert len(records) == 1
    job = records[0]
    assert job["datatype"] == "job"
    assert job["external_id"] == "d64d714882904f7f0nJ92t-9EFBS"
    assert job["title"] == "爬虫工程师（需本科学历）"
    assert job["company"] == "中策大数据"
    assert job["location"] == "深圳"
    assert job["salary"] == "8-12K"
    assert job["platform"] == "zhipin"
    assert job["url"].startswith("https://www.zhipin.com/job_detail/")
    assert "爬虫开发经验" in job["extend"]


def test_search_skips_missing_job_list():
    records = list(
        general_parser.parse(
            "zhipin", {"code": 37, "zpData": {"name": "x", "seed": "y", "ts": 1}},
            "search", as_dto=False,
        )
    )
    assert records == []


def test_search_skips_item_without_external_id():
    payload = {
        "code": 0,
        "zpData": {
            "jobList": [{"jobName": "无ID职位", "brandName": "公司"}]
        },
    }
    records = list(
        general_parser.parse("zhipin", payload, "search", as_dto=False)
    )
    assert records == []


def test_detail_produces_job_with_description():
    records = _detail()
    assert len(records) == 1
    job = records[0]
    assert job["datatype"] == "job"
    assert job["external_id"] == "detail-abc"
    assert job["company"] == "测试科技"
    assert job["location"] == "上海"
    assert job["salary"] == "20-25K"
    assert job["description"] == "负责后端服务开发"


def test_detail_requires_job_info():
    records = list(
        general_parser.parse("zhipin", {"code": 0, "zpData": {}}, "detail", as_dto=False)
    )
    assert records == []


def test_dto_wrapping_validates_against_job_dto():
    # as_dto=True 走 JobDTO 校验，字段应能成功映射
    records = list(
        general_parser.parse("zhipin", DETAIL_PAYLOAD, "detail", as_dto=True)
    )
    assert len(records) == 1
    item = records[0]
    assert item.kind == "job"
    assert item.data.external_id == "detail-abc"
