"""Material rows promoted by the grading cleaner."""

from datetime import datetime
from enum import IntEnum

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, GeneralBase


class MaterialAnalysisStatus(IntEnum):
    PENDING = 0
    SUCCEEDED = 1
    PROCESSING = 2
    FAILED = 3


class MaterialClean(GeneralBase, Base):
    datatype_key = "clean"
    unique_field = "content_id"
    update_fields = ["content_id", "platform"]

    __tablename__ = "t_material_clean"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键 ID"
    )
    datatype: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="clean",
        server_default="clean",
        comment="Pipeline 数据类型标识",
    )
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="内容所属平台"
    )
    content_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="平台内容 ID"
    )
    grade_rank: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="评级等级：P1=1、P2=2、P3=3、人工审核=-1"
    )
    grade_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="评级判定原因"
    )
    grade_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="评级时间"
    )
    snap_view_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="评级时播放量快照"
    )
    snap_pub_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="评级时发布时间快照"
    )
    snap_hours: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="评级时已发布小时数"
    )
    clean_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="graded",
        server_default="graded",
        comment="清洗状态：graded/manual_review/downloaded",
    )
    download_claim_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="下载领取令牌"
    )
    download_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="下载领取时间"
    )
    download_attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="下载尝试次数",
    )
    download_next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="下载下次重试时间"
    )
    download_last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="下载最近错误"
    )
    is_delete: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="删除标记：0=未删除，1=已删除",
    )
    is_analysis: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="分析状态：0=未分析，1=分析成功，2=分析中，3=分析失败",
    )
    expire_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="素材过期时间"
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), nullable=True, comment="创建时间"
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间",
    )

    __table_args__ = (
        Index(
            "uq_material_clean_platform_content",
            "platform",
            "content_id",
            unique=True,
        ),
        Index("idx_mc_expire", "expire_time"),
        Index("idx_mc_grade_rank", "grade_rank"),
        Index(
            "idx_mc_download_claim",
            "clean_status",
            "download_next_retry_at",
            "download_claimed_at",
            "download_attempt_count",
        ),
        {"schema": "public"},
    )
