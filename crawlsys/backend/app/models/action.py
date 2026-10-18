"""Action model — one row per (platform, action_name) pair."""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from .base import Base, BaseSchema
from pydantic import Field


class ActionHttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class Action(Base):
    """接口定义模型 - 对应 t_busi_action 表"""
    __tablename__ = "t_busi_action"
    __table_args__ = (
        UniqueConstraint("bs_id", "ba_action", name="uq_action_platform_action"),
        CheckConstraint("length(trim(ba_action)) > 0", name="ck_action_name_not_blank"),
        CheckConstraint(
            "ba_api_method IS NULL OR ba_api_method IN "
            "('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')",
            name="ck_action_http_method",
        ),
        CheckConstraint(
            "ba_schema_source IS NULL OR ba_schema_source IN ('synced', 'manual')",
            name="ck_action_schema_source",
        ),
        Index("idx_action_platform_enabled", "bs_id", "ba_enabled"),
        {'schema': 'public'},
    )

    ba_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bs_id: Mapped[int] = mapped_column(Integer, ForeignKey("public.t_busi_platform.bs_id"), nullable=False, comment="所属平台 ID")
    ba_action: Mapped[str] = mapped_column(String(100), nullable=False, comment="接口名，如 getUserInfo")
    ba_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="功能描述")
    ba_params_schema: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="参数定义 JSON")
    ba_api_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="平台 API 地址")
    ba_api_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="GET/POST")
    ba_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", comment="是否启用")
    ba_sample_safe: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="是否允许保存解析采样",
    )
    ba_schema_source: Mapped[Optional[str]] = mapped_column(
        String(16),
        default="synced",
        server_default="synced",
        nullable=True,
        comment="参数契约来源: synced/manual",
    )
    ba_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次同步时间",
    )
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("ba_sample_safe", False)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<Action {self.ba_action} (platform_id={self.bs_id})>"

    @validates("ba_action")
    def _normalize_action_name(self, _key: str, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ba_action 不能为空")
        return normalized

    @validates("ba_api_method")
    def _normalize_http_method(
        self,
        _key: str,
        value: str | ActionHttpMethod | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        try:
            return ActionHttpMethod(normalized).value
        except ValueError as exc:
            raise ValueError(f"不支持的 HTTP 方法: {value}") from exc

    @property
    def params_schema(self) -> dict[str, object] | list[object] | bool | None:
        """Return the stored parameter schema as JSON without leaking decode errors."""
        if not self.ba_params_schema:
            return None
        try:
            parsed = json.loads(self.ba_params_schema)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, (dict, list, bool)) else None


# ============== Pydantic DTOs ==============

class ActionBase(BaseSchema):
    bs_id: int = Field(..., description="所属平台 ID")
    ba_action: str = Field(..., max_length=100, description="接口名")
    ba_desc: Optional[str] = Field(None, description="功能描述")
    ba_params_schema: Optional[str] = Field(None, description="参数 JSON")
    ba_api_url: Optional[str] = Field(None, max_length=500, description="API URL")
    ba_api_method: Optional[str] = Field(None, max_length=10, description="GET/POST")
    ba_enabled: bool = Field(True, description="是否启用")
    ba_schema_source: Optional[str] = Field("synced", max_length=16, description="参数契约来源: synced/manual")
    ba_synced_at: Optional[datetime] = Field(None, description="最近一次同步时间")


class ActionCreate(ActionBase):
    pass


class ActionUpdate(BaseSchema):
    ba_action: Optional[str] = Field(None, max_length=100)
    ba_desc: Optional[str] = None
    ba_params_schema: Optional[str] = None
    ba_api_url: Optional[str] = None
    ba_api_method: Optional[str] = None
    ba_enabled: Optional[bool] = None
    ba_schema_source: Optional[str] = Field(None, max_length=16)
    ba_synced_at: Optional[datetime] = None


class ActionResponse(ActionBase):
    ba_id: int
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
