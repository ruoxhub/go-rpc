"""Search keyword per platform."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, Integer, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class BusiSearchKeyword(Base):
    """平台搜索关键词常量 — 一行 = 一个关键词。

    任务配置只需把 ref_table 选为 't_busi_search_keyword'，
    Worker 现有 _query_source 路径会按 platform 自动过滤，
    每行产出一个 WorkItem。
    """

    __tablename__ = "t_busi_search_keyword"
    __table_args__ = (
        Index("idx_bsk_platform", "platform"),
        {"schema": "public"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="pk",
    )
    platform: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("public.t_busi_platform.bs_platform_code"),
        nullable=False,
        comment="关联平台 code",
    )
    keyword: Mapped[str] = mapped_column(
        Text, nullable=False, comment="关键词文本",
    )
    is_crawled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", comment="是否已抓取完成 (Worker mark_done 标记)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default="now()", comment="创建时间",
    )

    def __repr__(self) -> str:
        return f"<BusiSearchKeyword id={self.id} platform={self.platform!r} kw={self.keyword!r}>"
