from __future__ import annotations

import re
from typing import TYPE_CHECKING

# 业务模型映射表现在由 GeneralBase 子类自动注册（见 models/base.py）。
# 各模型在类体内声明 datatype_key / unique_field / update_fields 即可，
# 无需在此手动维护。这里直接复用注册表，保持对外的符号不变。
from models.base import (
    DATATYPE_TO_MODEL,
    UNIQUE_FIELD_MAPPING,
    UPDATE_FIELD_MAPPING,
)

if TYPE_CHECKING:
    from models import Base


# 平台字段名称
PLATFORM_FIELD_DEFAULT: str = "platform"
PLATFORM_FIELD_ARTICLE: str = "source_name"

# 数据类型到模型的映射（自动注册，见 models/base.py）
# DATATYPE_TO_MODEL / UNIQUE_FIELD_MAPPING / UPDATE_FIELD_MAPPING 已由上方导入。


_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*$")
# 注意：以下正则仅用于校验「受信任的管理员配置」(source/where)，并非安全边界；
# 若配置来源不可信，应改用 SQLAlchemy 表达式构造而非字符串拼接。
_EXPR_RE = re.compile(r"^[a-zA-Z0-9_.:'()\- >]+$")
_WHERE_RE = re.compile(
    r"^[a-zA-Z0-9_.\s,'\"=<>!()+*\/%-]+"
    r"(?:\s+(?:AND|OR|NOT|IN|IS|NULL|TRUE|FALSE|LIKE|BETWEEN)\s+"
    r"[a-zA-Z0-9_.\s,'\"=<>!()+*\/%-]+)*$",
    re.IGNORECASE,
)
_WHERE_DANGEROUS = re.compile(
    r";|--|/\*|\b(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|UNION|INTO)\b",
    re.IGNORECASE,
)

# order_by 单项：列名 + 可选 ASC/DESC。禁止函数/逗号/NULLS 子句（本版 YAGNI）。
_ORDER_BY_RE = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\s+(ASC|DESC))?$",
    re.IGNORECASE,
)


_COUNT_FIELDS = ("share_count", "repost_count", "comment_count", "like_count", "view_count", "favorites")
