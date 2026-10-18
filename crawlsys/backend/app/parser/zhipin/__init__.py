"""Boss 直聘 (zhipin) 解析器 — 将 search / detail action 的 RPC 响应映射为职位记录。

RPC 成功响应外层统一为 ``{"code":0, "zpData": {...}}``：
- search:  职位列表在 ``zpData.jobList``，每条是搜索卡片（含 encryptJobId/securityId/lid）。
- detail:  职位详情在 ``zpData.jobInfo``（jobInfo 内联 brandInfo 等，扩展字段原样保留）。

两者均产出 ``datatype="job"``，由 pipeline 去重后写入 ``t_busi_job``。
唯一键取 ``encryptJobId``（detail 亦见 ``jobInfo.encryptId``，语义一致，取最先非空者）。
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .. import register


def _first(*values: Any) -> str | None:
    for value in values:
        if value not in (None, "", [], {}):
            return str(value)
    return None


def _search_record(item: dict[str, Any]) -> dict[str, Any]:
    external_id = _first(item.get("encryptJobId"), item.get("securityId"))
    if not external_id:
        return {}

    extend = {
        key: item[key]
        for key in (
            "areaDistrict", "businessDistrict", "cityName", "city",
            "brandIndustry", "brandScaleName", "brandStageName",
            "bossName", "bossTitle", "bossOnline",
            "jobExperience", "jobDegree", "jobLabels", "skills", "welfareList",
            "jobValidStatus", "jobType", "salaryDesc", "lid", "securityId",
            "expectId", "jobName", "gps", "brandLogo",
        )
        if key in item
    }

    return {
        "datatype": "job",
        "external_id": external_id,
        "title": item.get("jobName"),
        "company": item.get("brandName"),
        "location": item.get("cityName"),
        "salary": item.get("salaryDesc"),
        "platform": "zhipin",
        "url": f"https://www.zhipin.com/job_detail/{external_id}.html",
        "extend": json.dumps(extend, ensure_ascii=False),
    }


def _detail_record(data: dict[str, Any], job_info: dict[str, Any]) -> dict[str, Any]:
    external_id = _first(
        job_info.get("encryptId"),
        job_info.get("securityId"),
        data.get("securityId"),
    )
    if not external_id:
        return {}

    brand = job_info.get("brandInfo") or {}
    boss = job_info.get("bossInfo") or {}

    extend = {
        "jobInfo": job_info,
        "brandComInfo": data.get("brandComInfo"),
        "bossInfo": boss,
        "securityId": data.get("securityId"),
        "lid": data.get("lid"),
    }

    return {
        "datatype": "job",
        "external_id": external_id,
        "title": job_info.get("jobName"),
        "company": brand.get("brandName"),
        "location": job_info.get("locationName"),
        "salary": job_info.get("salaryDesc"),
        "description": job_info.get("jobDetail") or job_info.get("jobDesc"),
        "platform": "zhipin",
        "url": f"https://www.zhipin.com/job_detail/{external_id}.html",
        "extend": json.dumps(extend, ensure_ascii=False),
    }


@register("zhipin", "search")
def parse_zhipin_search(data: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """解析 zhipin search 响应：遍历 zpData.jobList 产出职位记录。"""
    if not isinstance(data, dict):
        return
    zp = data.get("zpData") or {}
    job_list = zp.get("jobList")
    if not isinstance(job_list, list):
        return
    for item in job_list:
        if not isinstance(item, dict):
            continue
        record = _search_record(item)
        if record:
            yield record


@register("zhipin", "detail")
def parse_zhipin_detail(data: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """解析 zhipin detail 响应：取 zpData.jobInfo 单条职位记录。"""
    if not isinstance(data, dict):
        return
    zp = data.get("zpData") or {}
    job_info = zp.get("jobInfo")
    if not isinstance(job_info, dict):
        return
    record = _detail_record(data, job_info)
    if record:
        yield record
