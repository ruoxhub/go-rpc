from sqlalchemy import String, Integer, Text, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, List
from datetime import datetime
from enum import IntEnum
from pydantic import Field

from .base import Base, GeneralBase, BaseSchema, TimeMixin, IDMixin

# ============== SQLAlchemy ORM 模型 ==============

class Media(GeneralBase, Base):
    """媒体模型 - 使用 SQLAlchemy 2.0 现代语法"""

    # ---- 自动注册元信息 ----
    datatype_key = "media"
    unique_field = "media_id"
    update_fields = ["media_id", "platform"]

    __tablename__ = "t_busi_media"

    # 关联字段
    media_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment='媒体 ID')
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='用户 ID')
    content_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='视频 ID')
    # 媒体信息
    type: Mapped[Optional[int]] = mapped_column(Integer, comment='1:video 2:photo 3:gif 4:audio', nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment='媒体资源链接')
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")
    pub_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), comment='发布时间', nullable=True)
    extend: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展字段 (JSON 字符串)")
    __table_args__ = (
        Index('idx_base_media_content_id', 'content_id'),
        Index('idx_base_media_user_id', 'user_id'),
        Index('idx_base_media_platform', 'platform'),
        Index('idx_base_media_media_id', 'media_id'),
        Index('uq_base_media_platform_media_id', 'platform', 'media_id', unique=True),
        {'schema': 'public'}
    )

# 别名映射，保证向前兼容
BusMedia = Media
BaseMedia = Media




# ============== Pydantic DTO 定义 ==============

class MediaTypeEnum(IntEnum):
    """媒体类型枚举"""
    VIDEO = 1
    PHOTO = 2
    GIF = 3
    AUDIO = 4


class MediaSchema(BaseSchema):
    """媒体基础 Schema"""
    media_id: Optional[str] = Field(None, max_length=32, description="媒体 ID")
    user_id: Optional[str] = Field(None, max_length=64, description="用户 ID")
    content_id: Optional[str] = Field(None, max_length=64, description="内容 ID")
    type: Optional[MediaTypeEnum] = Field(None, description="媒体类型")
    url: Optional[str] = Field(None, max_length=1024, description="网页地址")
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")


class MediaCreate(MediaSchema):
    """创建媒体请求"""
    pass


class MediaResponse(MediaSchema, IDMixin, TimeMixin):
    """媒体响应"""
    pub_time: Optional[datetime] = None
    extend: Optional[str] = None


class MediaListResponse(BaseSchema):
    """媒体列表响应"""
    total: int
    items: List[MediaResponse]
