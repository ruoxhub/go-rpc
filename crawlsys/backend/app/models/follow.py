from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import List, Optional

from pydantic import Field

from .base import Base, GeneralBase, BaseSchema, TimeMixin, IDMixin

class Follow(GeneralBase, Base):
    """用户关联模型"""

    # ---- 自动注册元信息 ----
    datatype_key = "follow"
    unique_field = "follow_id"
    update_fields = ["follow_id", "follow_name", "platform"]

    __tablename__ = "t_busi_follow"

    user_id: Mapped[Optional[str]] = mapped_column(String(64), comment='用户 ID', nullable=True)
    follow_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关注或粉丝的 ID', nullable=True)
    follow_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='关注或粉丝的名称')
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")

    __table_args__ = (
        Index('idx_base_follow_user_id', 'user_id'),
        Index('idx_base_follow_follow_id', 'follow_id'),
        Index('idx_base_follow_platform', 'platform'),
        Index('uq_base_follow_unique', 'platform', 'user_id', 'follow_id', unique=True),
        {'schema': 'public'}
    )

# 别名映射，保证向前兼容
BusFollow = Follow
BaseFollow = Follow


# ============== Pydantic DTO 定义 ==============

class FollowBase(BaseSchema):
    """用户关系基础 Schema — 字段长度对齐 ORM Follow 列定义。"""
    user_id: Optional[str] = Field(None, max_length=64, description="用户 ID")
    follow_id: Optional[str] = Field(None, max_length=64, description="关注或粉丝 ID")
    follow_name: Optional[str] = Field(None, max_length=255, description="关注或粉丝名称")
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")


class FollowSchema(FollowBase):
    """用户关系 Schema"""
    pass


class FollowResponse(FollowBase, IDMixin, TimeMixin):
    """用户关系响应"""
    pass


class FollowListResponse(BaseSchema):
    """用户关系列表响应"""
    total: int
    items: List[FollowResponse]

