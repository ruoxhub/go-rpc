from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from typing import Optional, List, ClassVar
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict

# ============== SQLAlchemy ORM 基类 ==============

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 基础类"""
    pass


# ============== 模型注册表（由 GeneralBase 子类自动注册）==============
# 业务模型在类体内声明 datatype_key / unique_field / update_fields 即可自动注册，
# 无需在 core/constants.py 手动维护映射表。不声明 datatype_key 的子类不会被注册。

DATATYPE_TO_MODEL: dict[str, type] = {}
UNIQUE_FIELD_MAPPING: dict[str, str] = {}
UPDATE_FIELD_MAPPING: dict[str, list[str]] = {}


class GeneralBase:
    """通用基础字段"""

    # 基本信息字段
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    datatype: Mapped[Optional[str]] = mapped_column(String(10), default="0", comment="数据类型")
    created_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), nullable=True, comment='系统创建时间')
    updated_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True, comment='系统更新时间')

    # ---- 子类可声明以下类属性以自动注册到 pipeline 注册表 ----
    # 用 ClassVar 标注，避免被 SQLAlchemy 当作映射列。
    datatype_key: ClassVar[Optional[str]] = None
    unique_field: ClassVar[Optional[str]] = None
    update_fields: ClassVar[Optional[list[str]]] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 仅当子类自身（而非继承自父类）显式声明了 datatype_key 才注册，
        # 避免别名 / 中间基类重复注册。
        key = cls.__dict__.get("datatype_key")
        if not key:
            return
        DATATYPE_TO_MODEL[key] = cls
        uf = cls.__dict__.get("unique_field")
        if uf:
            UNIQUE_FIELD_MAPPING[key] = uf
        up = cls.__dict__.get("update_fields")
        if up:
            UPDATE_FIELD_MAPPING[key] = list(up)


# ============== Pydantic DTO 基类 ==============

class DataTypeEnum(str, Enum):
    """数据类型枚举（与 Content.data_type 的 String 列对齐）"""
    NEWS = "1"      # 新闻
    SOCIAL = "2"    # 社交
    VIDEO = "3"     # 视频
    ARTICLE = "4"   # 文章


class BaseSchema(BaseModel):
    """基础 Schema"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra='ignore',
        use_enum_values=True,
    )


class TimeMixin(BaseModel):
    """时间字段混入"""
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class IDMixin(BaseModel):
    """ID 字段混入"""
    id: int


# ============== 通用 API 响应 Schemas ==============

class ApiResponse(BaseSchema):
    """通用 API 响应"""
    success: bool = True
    message: str = ""
    data: Optional[dict] = None


class PageResponse(BaseSchema):
    """分页响应"""
    page: int
    page_size: int
    total: int
    items: List[dict]
