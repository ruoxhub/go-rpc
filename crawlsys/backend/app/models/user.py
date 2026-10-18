from sqlalchemy import String, Integer, Text, DateTime, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, List
from datetime import datetime
from enum import IntEnum
from pydantic import Field, field_validator

from .base import Base, GeneralBase, BaseSchema, TimeMixin, IDMixin

# ============== SQLAlchemy ORM 模型 ==============

class User(GeneralBase, Base):
    """用户模型 - 使用 SQLAlchemy 2.0 现代语法"""

    # ---- 自动注册元信息 ----
    datatype_key = "user"
    unique_field = "user_id"
    update_fields = ["username", "platform"]

    __tablename__ = "t_busi_user"

    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="平台用户 ID")
    avatar: Mapped[Optional[str]] = mapped_column(String(255), comment="用户头像地址")
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='名称')
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='用户名')
    gender: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment='性别 0: 无 1: 男 2：女')
    email: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment='邮箱')
    phone: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment='手机号')
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment='个人网站')
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='用户描述')
    education: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='教育经历')
    experience: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment='工作经验')
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='位置')
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment='城市')
    country_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment='国家代码')
    follower_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="粉丝数")
    following_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="关注数")
    content_count: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="内容数 (包括贴子、文章、视频)")
    birthday: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="生日")
    verified: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="平台认证")
    extend: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展字段 (JSON 字符串)")
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now, comment='平台注册时间（不要与 GeneralBase.created_time 系统创建时间混淆）', nullable=True)

    # 调度追踪字段
    detail_fetched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="是否已抓详情")

    __table_args__ = (
        Index('idx_base_user_platform', 'platform'),
        Index('idx_base_user_username', 'username'),
        Index('idx_base_user_user_id', 'user_id'),
        Index('idx_base_user_email', 'email'),
        Index('uq_base_user_platform_username', 'platform', 'username', unique=True),
        {'schema': 'public'}
    )

# 别名映射，保证向前兼容
BusUser = User
BaseUser = User



# ============== Pydantic DTO 定义 ==============

class GenderEnum(IntEnum):
    """性别枚举"""
    NONE = 0  # 未知
    MALE = 1  # 男
    FEMALE = 2  # 女


class UserBase(BaseSchema):
    """用户基础 Schema"""
    user_id: Optional[str] = Field(None, max_length=64, description="平台用户 ID")
    avatar: Optional[str] = Field(None, max_length=255, description="用户头像地址")
    name: Optional[str] = Field(None, max_length=255, description="名称")
    username: Optional[str] = Field(None, max_length=255, description="用户名")
    gender: Optional[GenderEnum] = Field(None, description="性别")
    email: Optional[str] = Field(None, max_length=500, description="邮箱")
    phone: Optional[str] = Field(None, max_length=500, description="手机号")
    website: Optional[str] = Field(None, max_length=500, description="个人网站")
    description: Optional[str] = Field(None, description="用户描述")
    education: Optional[str] = Field(None, description="教育经历")
    experience: Optional[str] = Field(None, description="工作经验")
    location: Optional[str] = Field(None, max_length=255, description="位置")
    city: Optional[str] = Field(None, max_length=100, description="城市")
    country_code: Optional[str] = Field(None, max_length=10, description="国家代码")
    follower_count: int = Field(default=0, description="粉丝数")
    following_count: int = Field(default=0, description="关注数")
    content_count: int = Field(default=0, description="内容数")
    birthday: Optional[str] = Field(None, max_length=20, description="生日")
    verified: Optional[str] = Field(None, max_length=255, description="平台认证")
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and '@' not in v:
            raise ValueError('无效的邮箱格式')
        return v


class UserCreate(UserBase):
    """创建用户请求"""
    pass


class UserUpdate(BaseSchema):
    """更新用户请求 - 所有字段可选"""
    user_id: Optional[str] = None
    avatar: Optional[str] = None
    name: Optional[str] = None
    username: Optional[str] = None
    gender: Optional[GenderEnum] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    education: Optional[str] = None
    experience: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    content_count: Optional[int] = None
    birthday: Optional[str] = None
    verified: Optional[str] = None
    platform: Optional[str] = None


class UserResponse(UserBase, IDMixin, TimeMixin):
    """用户响应"""
    extend: Optional[str] = None  # JSON 字符串
    created_at: Optional[datetime] = None


class UserListResponse(BaseSchema):
    """用户列表响应"""
    total: int
    items: List[UserResponse]
