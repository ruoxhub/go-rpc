from sqlalchemy import String, Integer, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, List
from datetime import datetime
from pydantic import Field

from .base import Base, GeneralBase, BaseSchema, TimeMixin, IDMixin

# ============== SQLAlchemy ORM 模型 ==============

class Comment(GeneralBase, Base):
    """评论模型 - 使用 SQLAlchemy 2.0 现代语法"""

    # ---- 自动注册元信息 ----
    datatype_key = "comment"
    unique_field = "comment_id"
    update_fields = ["comment_id", "platform"]

    __tablename__ = "t_busi_comment"

    # 关联字段
    content_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='评论所在的内容关联 id')
    parent_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='上级用户 id')
    parent_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='上级用户名')
    parent_comment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='上级评论 id')
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='评论的用户 id')
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='用户名')
    comment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='评论 id')
    # 内容字段
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='评论帖子的内容')
    # 统计字段
    like_count: Mapped[int] = mapped_column(Integer, default=0, comment='爱心数')
    reply_count: Mapped[int] = mapped_column(Integer, default=0, comment='回复数')
    # 时间字段
    pub_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='发布时间')
    extend: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展字段 (JSON 字符串)")
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")

    __table_args__ = (
        Index('idx_base_comment_content_id', 'content_id'),
        Index('idx_base_comment_user_id', 'user_id'),
        Index('idx_base_comment_platform', 'platform'),
        Index('idx_base_comment_comment_id', 'comment_id'),
        Index('uq_base_comment_platform_comment_id', 'platform', 'comment_id', unique=True),
        {'schema': 'public'}
    )

# 别名映射，保证向前兼容
BusComment = Comment
BaseComment = Comment



# ============== Pydantic DTO 定义 ==============

class CommentSchema(BaseSchema):
    """评论 Schema"""
    content_id: Optional[str] = Field(None, max_length=64, description="内容 ID")
    parent_comment_id: Optional[str] = Field(None, max_length=64, description="父评论 ID")
    parent_user_id: Optional[str] = Field(None, max_length=64, description="上级用户 ID")
    parent_name: Optional[str] = Field(None, max_length=255, description="上级用户名")
    user_id: Optional[str] = Field(None, max_length=64, description="用户 ID")
    username: Optional[str] = Field(None, max_length=255, description="用户名")
    comment_id: Optional[str] = Field(None, max_length=64, description="评论 ID")
    content: Optional[str] = Field(None, description="评论内容")
    like_count: int = Field(default=0, description="点赞数")
    reply_count: int = Field(default=0, description="回复数")
    pub_time: Optional[datetime] = Field(None, description="发布时间")
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")


class CommentResponse(CommentSchema, IDMixin, TimeMixin):
    """评论响应"""
    extend: Optional[str] = None


class CommentListResponse(BaseSchema):
    """评论列表响应"""
    total: int
    items: List[CommentResponse]
