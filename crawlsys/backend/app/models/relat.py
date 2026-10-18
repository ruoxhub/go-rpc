from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from .base import Base, GeneralBase

class Contentrelat(GeneralBase, Base):
    """内容关联模型"""

    __tablename__ = "t_busi_content_relat"

    content_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='帖子 id')
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='用户 id')
    relat_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='关联该帖子的用户 id')
    relat_content_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='关联该帖子的贴子 id')
    relat_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment='关联类型 1:转发 2:评论 3:喜欢')
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")

    __table_args__ = (
        Index('idx_base_content_relat_content_id', 'content_id'),
        Index('idx_base_content_relat_user_id', 'user_id'),
        Index('idx_base_content_relat_platform', 'platform'),
        Index(
            'uq_base_content_relat_unique',
            'platform', 'relat_type', 'user_id', 'content_id', 'relat_user_id', 'relat_content_id',
            unique=True,
        ),
        {'schema': 'public'}
    )

# 别名映射，保证向前兼容
BusContentRelat = Contentrelat
BaseContentRelat = Contentrelat
BusPostRelation = Contentrelat  # deprecated: 使用 BusContentRelat
BasePostRelation = Contentrelat  # deprecated: 使用 BaseContentRelat

