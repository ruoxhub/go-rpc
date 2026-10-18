"""系统数据类型注册模型与内省逻辑。

将各业务 ORM 模型（Content, User, Comment 等）与 DTO 的元数据结构落库为持久化对象，
供管理前端、AI 辅助解析以及任务调度等动态查询。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import NoneType, UnionType
from typing import Any, ClassVar, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, DATATYPE_TO_MODEL, UNIQUE_FIELD_MAPPING, UPDATE_FIELD_MAPPING

JsonColumn = JSON().with_variant(JSONB, "postgresql")

FIELD_TYPES: tuple[str, ...] = (
    "string",
    "integer",
    "number",
    "boolean",
    "datetime",
    "object",
    "array",
)


# ============== SQLAlchemy ORM 模型 ==============

class SysDatatype(Base):
    """系统数据类型元数据持久化表。"""

    __tablename__ = "t_sys_datatype"
    __table_args__ = (
        UniqueConstraint("datatype_key", name="uq_sys_datatype_key"),
        Index("idx_sys_datatype_active", "is_active"),
    )

    datatype_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    datatype_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, comment="数据类型唯一标识"
    )
    table_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="对应的数据库物理表名"
    )
    model_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="ORM 类名"
    )
    description: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="模型中文说明"
    )
    unique_field: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="去重唯一标识字段"
    )
    update_fields: Mapped[list[str]] = mapped_column(
        JsonColumn, nullable=False, default=list, comment="冲突更新字段列表"
    )
    columns: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonColumn, nullable=False, default=list, comment="数据库物理列定义详情"
    )
    dto_fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonColumn, nullable=False, default=list, comment="解析器 DTO 字段规范"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ============== Pydantic Schemas / DTOs ==============

class ColumnMeta(BaseModel):
    """列定义元数据"""
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    comment: str | None = None


class DtoFieldMeta(BaseModel):
    """DTO 目标字段元数据"""
    name: str
    target: str
    required: bool = False
    value_types: list[str] = Field(default_factory=list)
    description: str | None = None


class SysDatatypeBase(BaseModel):
    """数据类型基础元数据"""
    datatype_key: str
    table_name: str
    model_name: str
    description: str | None = None
    unique_field: str | None = None
    update_fields: list[str] = Field(default_factory=list)
    columns: list[ColumnMeta] = Field(default_factory=list)
    dto_fields: list[DtoFieldMeta] = Field(default_factory=list)
    is_active: bool = True


class SysDatatypeRead(SysDatatypeBase):
    """数据类型查询响应"""
    model_config = ConfigDict(from_attributes=True)

    datatype_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SysDatatypeList(BaseModel):
    """数据类型列表响应"""
    items: list[SysDatatypeRead]
    total: int


class SysDatatypeSyncResponse(BaseModel):
    """数据类型同步响应"""
    success: bool = True
    synced_count: int
    datatypes: list[str]


class SysDatatypeStatusUpdate(BaseModel):
    """数据类型启用状态更新请求"""
    is_active: bool


# ============== 内省辅助函数 ==============

def parser_value_types(annotation: object) -> list[str]:
    """推导字段类型注解对应的 JSON/Parser 数据类型。"""
    if annotation is Any:
        return list(FIELD_TYPES)
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        inferred = {
            ft
            for member in get_args(annotation)
            if member is not NoneType
            for ft in parser_value_types(member)
        }
        return [ft for ft in FIELD_TYPES if ft in inferred] or list(FIELD_TYPES)
    scalar = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        datetime: "datetime",
    }.get(annotation)  # type: ignore[arg-type]
    if scalar:
        return [scalar]
    if annotation is dict or origin in (dict, Mapping):
        return ["object"]
    if annotation in (list, tuple, set, frozenset) or origin in (
        list,
        tuple,
        set,
        frozenset,
        Sequence,
    ):
        return ["array"]
    return list(FIELD_TYPES)


def introspect_datatype_models() -> list[dict[str, Any]]:
    """内省当前系统中所有由 GeneralBase 注册的业务模型及其关联 DTO。"""
    # 延迟导入，保证 parser.dto 初始化完毕
    from parser.dto import ParsedItem

    results: list[dict[str, Any]] = []
    for key, model_cls in DATATYPE_TO_MODEL.items():
        doc = (model_cls.__doc__ or "").strip().split("\n")[0]
        cols: list[dict[str, Any]] = []
        for col in model_cls.__table__.columns:
            cols.append({
                "name": col.name,
                "type": str(col.type),
                "nullable": bool(col.nullable),
                "primary_key": bool(col.primary_key),
                "comment": col.comment or None,
            })

        dto_cls = ParsedItem._DTO_BY_KIND.get(key)
        dto_fields: list[dict[str, Any]] = []
        if dto_cls:
            for fname, finfo in dto_cls.model_fields.items():
                if fname == "datatype":
                    continue
                dto_fields.append({
                    "name": fname,
                    "target": f"/{fname}",
                    "required": finfo.is_required(),
                    "value_types": parser_value_types(finfo.annotation),
                    "description": finfo.description or None,
                })

        results.append({
            "datatype_key": key,
            "table_name": getattr(model_cls, "__tablename__", ""),
            "model_name": model_cls.__name__,
            "description": doc,
            "unique_field": UNIQUE_FIELD_MAPPING.get(key),
            "update_fields": list(UPDATE_FIELD_MAPPING.get(key) or []),
            "columns": cols,
            "dto_fields": dto_fields,
            "is_active": True,
        })
    return results


__all__ = [
    "ColumnMeta",
    "DtoFieldMeta",
    "FIELD_TYPES",
    "SysDatatype",
    "SysDatatypeBase",
    "SysDatatypeList",
    "SysDatatypeRead",
    "SysDatatypeStatusUpdate",
    "SysDatatypeSyncResponse",
    "introspect_datatype_models",
    "parser_value_types",
]
