from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import Field
from sqlalchemy import DateTime, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GeneralBase, BaseSchema, IDMixin, TimeMixin


class JobType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    REMOTE = "remote"


class Platform(str, Enum):
    BOSS = "boss"
    LIEPIN = "liepin"
    LAGOU = "lagou"
    ZHILIAN = "zhilian"
    JOB51 = "51job"
    YUPAO = "yupao"
    MOCK = "mock"


class BusJob(GeneralBase, Base):
    """职位招聘 ORM 模型。"""

    # ---- 自动注册元信息 ----
    datatype_key = "job"
    unique_field = "external_id"
    update_fields = [
        "external_id", "platform", "title", "company",
        "location", "description", "url", "salary", "extend"
    ]

    __tablename__ = "t_busi_job"

    external_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True, comment="平台职位 ID")
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="发布者用户 ID")
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="职位标题")
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="公司名称")
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="工作地点")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="职位描述")
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="链接")
    salary: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="薪资")
    platform: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True, comment="所属平台")
    pub_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="发布时间")
    extend: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展字段 (JSON 字符串)")

    __table_args__ = (
        Index("idx_base_job_external_id", "external_id"),
        Index("idx_base_job_platform", "platform"),
        Index("uq_base_job_platform_external_id", "platform", "external_id", unique=True),
    )


# 兼容别名
Job = BusJob
BaseJob = BusJob


# ============== Pydantic DTO 定义 ==============

class JobBase(BaseSchema):
    """职位基础 Schema — 字段长度对齐 ORM Job 列定义。"""
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")
    external_id: Optional[str] = Field(None, max_length=100, description="平台职位 ID")
    user_id: Optional[str] = Field(None, max_length=64, description="发布者用户 ID")
    title: Optional[str] = Field(None, max_length=512, description="职位标题")
    company: Optional[str] = Field(None, max_length=255, description="公司名称")
    location: Optional[str] = Field(None, max_length=255, description="工作城市")
    salary: Optional[str] = Field(None, max_length=128, description="薪资描述")
    description: Optional[str] = Field(None, description="职位描述")
    url: Optional[str] = Field(None, max_length=1024, description="原始 URL")
    pub_time: Optional[datetime] = Field(None, description="发布时间")
    extend: Optional[str] = Field(None, description="扩展字段")


class JobCreate(JobBase):
    """创建职位请求"""
    pass


class JobResponse(JobBase, IDMixin):
    """职位响应"""
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class JobListResponse(BaseSchema):
    """职位列表响应"""
    total: int
    items: List[JobResponse]

