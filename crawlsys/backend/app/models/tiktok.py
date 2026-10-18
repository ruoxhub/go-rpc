"""TikTok 话题/挑战 (Challenge) 数据模型 - SQLAlchemy ORM + Pydantic Schemas"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pydantic import Field

from .base import Base, GeneralBase, BaseSchema, IDMixin, TimeMixin


# ============== SQLAlchemy ORM 模型 ==============

class TkChallenge(GeneralBase, Base):
    """TikTok 话题 (Challenge / Hashtag) 模型。

    数据来源于 TikTok challenge 详情接口，原始 JSON 形如:
    {
        "challengeInfo": {
            "challenge": {
                "id": "870345", "title": "menswear", "desc": "...",
                "isCommerce": false, "stats": {...}, "statsV2": {...}
            },
            "challengeAnnouncement": {"body": "", "title": ""},
            "stats": {...}, "statsV2": {...}
        },
        "clientId": "...", "group": "tiktok", "shareMeta": {...}, ...
    }
    """

    __tablename__ = "tk_challenge"

    # 注册到 pipeline 注册表：经 standard sink 的 _to_models 路由到 tk_challenge
    datatype_key = "challenge"
    unique_field = "challenge_id"
    update_fields = ["title", "desc", "is_commerce", "video_count", "view_count"]

    # ---------- 话题标识 ----------
    challenge_id: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="话题 ID",
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="话题标题 (hashtag)",
    )
    desc: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="话题描述",
    )
    is_commerce: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否商业话题",
    )

    # ---------- 统计 (statsV2, 字符串) ----------
    video_count: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="视频数 (statsV2)",
    )
    view_count: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="播放/浏览数 (statsV2)",
    )



    __table_args__ = (
        Index("idx_tk_challenge_title", "title"),
        Index("uq_tk_challenge_id", "challenge_id", unique=True),
        {"schema": "public"},
    )

    @classmethod
    def from_api_response(cls, data: dict) -> "TkChallenge":
        """从 TikTok challenge 详情接口原始 JSON 构造实例。

        Args:
            data: 接口返回的完整 JSON (dict)。
        """
        challenge_info = data.get("challengeInfo", {}) or {}
        challenge = challenge_info.get("challenge", {}) or {}
        # stats = challenge.get("stats", {}) or {}
        stats_v2 = challenge_info.get("statsV2", {}) or challenge.get("statsV2", {}) or {}
        # announcement = challenge_info.get("challengeAnnouncement", {}) or {}
        # share_meta = data.get("shareMeta", {}) or {}

        return cls(
            challenge_id=str(challenge.get("id", "")),
            title=challenge.get("title"),
            desc=challenge.get("desc"),
            is_commerce=bool(challenge.get("isCommerce", False)),
            video_count=str(stats_v2.get("videoCount", "")) if stats_v2.get("videoCount") is not None else None,
            view_count=str(stats_v2.get("viewCount", "")) if stats_v2.get("viewCount") is not None else None,
        )

    def __repr__(self) -> str:
        return f"<TkChallenge id={self.challenge_id!r} title={self.title!r}>"


# ============== Pydantic DTO 定义 ==============

class TkChallengeBase(BaseSchema):
    """TikTok 话题基础 Schema"""
    challenge_id: str = Field(..., max_length=64, description="话题 ID")
    title: Optional[str] = Field(None, max_length=255, description="话题标题")
    desc: Optional[str] = Field(None, description="话题描述")
    is_commerce: bool = Field(default=False, description="是否商业话题")
    video_count: Optional[str] = Field(None, max_length=32, description="视频数 (statsV2)")
    view_count: Optional[str] = Field(None, max_length=32, description="播放/浏览数 (statsV2)")


class TkChallengeCreate(TkChallengeBase):
    """创建 TikTok 话题请求"""
    pass


class TkChallengeUpdate(BaseSchema):
    """更新 TikTok 话题请求"""
    title: Optional[str] = None
    desc: Optional[str] = None
    is_commerce: Optional[bool] = None
    video_count: Optional[int] = None
    view_count: Optional[int] = None



class TkChallengeResponse(TkChallengeBase, IDMixin, TimeMixin):
    """TikTok 话题响应"""
    pass


class TkChallengeListResponse(BaseSchema):
    """TikTok 话题列表响应"""
    total: int
    items: List[TkChallengeResponse]


class TkCategory(Base):
    """TikTok Shop 分类标签。"""

    __tablename__ = "tk_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="TikTok Shop 分类 ID",
    )
    label: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="分类标签",
    )
    parent_category_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("public.tk_category.category_id", ondelete="RESTRICT"),
        nullable=True,
        comment="父分类 ID；一级分类为空",
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="分类层级，从 1 开始",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="同级分类顺序，从 0 开始",
    )

    __table_args__ = (
        Index("idx_tk_category_parent_sort", "parent_category_id", "sort_order"),
        {"schema": "public"},
    )

    def __repr__(self) -> str:
        return f"<TkCategory category_id={self.category_id!r} label={self.label!r}>"
