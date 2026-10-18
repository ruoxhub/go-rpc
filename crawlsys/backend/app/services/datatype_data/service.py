"""数据记录管理服务：对已注册 ORM 模型对应的物理表做受控 Core CRUD。

设计边界：

- 表名与列名只来自代码内省的 ORM 元数据（`model.__table__`），不接受客户端输入，
  因此不存在表名或列名注入面。
- 所有值都经过按列类型的强制转换后再以绑定参数写入，绝不拼接值到 SQL 文本。
- 只允许新增加拿大可空列之外的通用 CRUD，不提供任意 SQL、DDL 或跨表关联。
- 金额、日期等语义化格式化由前端负责，本层只保证类型正确与可读。
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import (
    JSON,
    Boolean,
    ColumnElement,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    Numeric,
    and_,
    func,
    or_,
    select,
)
from sqlalchemy import types as sa_types
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from common.logging import get_logger
from models.base import DATATYPE_TO_MODEL
from services.datatype_data.errors import DatatypeDataError
from storage import SQLAlchemyDB

logger = get_logger(__file__)

_FILTER_OPERATORS = (
    "eq",
    "ne",
    "contains",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
)
FilterOperator = Literal["eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_null"]

_ORDER_VALUES = ("asc", "desc")
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 20
KEYWORD_COLUMN_LIMIT = 8


@dataclass(frozen=True, slots=True)
class DatatypeColumnSpec:
    """单列的可编辑契约与展示元数据。"""

    name: str
    sql_type: str
    value_type: str
    nullable: bool
    primary_key: bool
    comment: str | None
    max_length: int | None
    has_default: bool
    autoincrement: bool

    @property
    def editable(self) -> bool:
        return not self.autoincrement

    @property
    def required(self) -> bool:
        """新建时是否必须显式提供：非空、非自增且没有默认值。"""
        return (not self.nullable) and (not self.autoincrement) and (not self.has_default)


@dataclass(frozen=True, slots=True)
class DatatypeContext:
    """某个数据类型的表级上下文。"""

    datatype_key: str
    table_name: str
    model_name: str
    description: str | None
    unique_field: str | None
    columns: tuple[DatatypeColumnSpec, ...]
    pk_columns: tuple[str, ...]

    def column(self, name: str) -> DatatypeColumnSpec | None:
        for column in self.columns:
            if column.name == name:
                return column
        return None

    @property
    def searchable_columns(self) -> tuple[str, ...]:
        return tuple(
            c.name for c in self.columns if c.value_type == "string"
        )[:KEYWORD_COLUMN_LIMIT]


@dataclass(frozen=True, slots=True)
class DatatypeRowPage:
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


def _value_type_of(column_type: sa_types.TypeEngine) -> str:
    if isinstance(column_type, Boolean):
        return "boolean"
    if isinstance(column_type, Integer):
        return "integer"
    if isinstance(column_type, (Numeric, Float)):
        return "number"
    if isinstance(column_type, DateTime):
        return "datetime"
    if isinstance(column_type, JSON):
        return "json"
    if isinstance(column_type, LargeBinary):
        return "binary"
    return "string"


def _is_autoincrement(column) -> bool:
    """判断列是否由数据库自动生成。

    注意：SQLAlchemy 的 ``Column.autoincrement`` 默认值是 ``"auto"``（而非 ``False``），
    表示「若该列是整型主键则自增」。直接 ``bool("auto")`` 会把所有列误判为自增，
    因此这里必须显式判断：整型主键且未被显式关闭 ``autoincrement``。
    """
    if not column.primary_key:
        return False
    if column.autoincrement is False:
        return False
    return isinstance(column.type, Integer)


def _build_context(datatype_key: str, model: type) -> DatatypeContext:
    table = model.__table__
    columns: list[DatatypeColumnSpec] = []
    for column in table.columns:
        column_type = column.type
        has_default = column.default is not None or column.server_default is not None
        columns.append(
            DatatypeColumnSpec(
                name=column.name,
                sql_type=str(column_type),
                value_type=_value_type_of(column_type),
                nullable=bool(column.nullable),
                primary_key=bool(column.primary_key),
                comment=column.comment or None,
                max_length=getattr(column_type, "length", None),
                has_default=has_default,
                autoincrement=_is_autoincrement(column),
            )
        )
    doc = (model.__doc__ or "").strip().split("\n")[0] or None
    return DatatypeContext(
        datatype_key=datatype_key,
        table_name=table.name,
        model_name=model.__name__,
        description=doc,
        unique_field=getattr(model, "unique_field", None),
        columns=tuple(columns),
        pk_columns=tuple(c.name for c in table.primary_key.columns),
    )


def _coerce_value(spec: DatatypeColumnSpec, raw: Any) -> Any:
    """把客户端 JSON 值转换为数据库可写入的 Python 值。"""
    if raw is None:
        return None

    value_type = spec.value_type
    try:
        if value_type == "boolean":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, int) and raw in (0, 1):
                return bool(raw)
            if isinstance(raw, str) and raw.strip().lower() in ("true", "false", "1", "0"):
                return raw.strip().lower() in ("true", "1")
            raise ValueError("布尔值只能是 true 或 false")

        if value_type == "integer":
            if isinstance(raw, bool):
                raise ValueError("整数不接受布尔值")
            if isinstance(raw, int):
                return raw
            if isinstance(raw, float) and raw.is_integer():
                return int(raw)
            if isinstance(raw, str) and raw.strip():
                return int(raw.strip())
            raise ValueError("需要整数")

        if value_type == "number":
            if isinstance(raw, bool):
                raise ValueError("数字不接受布尔值")
            if isinstance(raw, (int, float, Decimal)):
                number = float(raw)
            elif isinstance(raw, str) and raw.strip():
                number = float(raw.strip())
            else:
                raise ValueError("需要数字")
            if number != number or number in (float("inf"), float("-inf")):
                raise ValueError("数字必须是有限值")
            return number

        if value_type == "datetime":
            if isinstance(raw, datetime):
                moment = raw
            elif isinstance(raw, str) and raw.strip():
                moment = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            else:
                raise ValueError("需要 ISO 日期时间")
            if moment.tzinfo is not None:
                moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
            return moment

        if value_type == "json":
            if isinstance(raw, (dict, list)):
                return raw
            if isinstance(raw, str) and raw.strip():
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("JSON 无效") from exc
                if isinstance(parsed, (dict, list)):
                    return parsed
            raise ValueError("需要 JSON 对象或数组")

        if value_type == "binary":
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw)
            if isinstance(raw, str):
                return base64.b64decode(raw, validate=True)
            raise ValueError("需要 Base64 字符串")

        # string 及兜底
        if isinstance(raw, (dict, list)):
            raise ValueError("需要文本")
        text = raw if isinstance(raw, str) else str(raw)
        if spec.max_length is not None and len(text) > spec.max_length:
            raise ValueError(f"长度不能超过 {spec.max_length} 个字符")
        return text
    except (ValueError, TypeError, binascii.Error) as exc:
        raise DatatypeDataError(
            "invalid_field_value",
            f"字段 {spec.name} 的值无效：{exc}",
            status_code=422,
            details={"field": spec.name},
        ) from exc


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    mapping = row._mapping
    return {name: _serialize_value(mapping[name]) for name in columns}


def _map_db_error(exc: SQLAlchemyError, *, action: str) -> DatatypeDataError:
    """把 SQL 错误转换为不泄漏 SQL 细节的领域错误。"""
    logger.warning("Datatype data %s failed (%s)", action, type(exc).__name__)
    if isinstance(exc, IntegrityError):
        return DatatypeDataError(
            "constraint_violation",
            "写入违反数据库约束（唯一键或非空约束）",
            status_code=409,
        )
    return DatatypeDataError(
        "storage_error",
        "数据存储操作失败，请稍后重试",
        status_code=502,
    )


class DatatypeDataService:
    """对已注册 ORM 表做受控行级 CRUD 的服务。"""

    def __init__(self, db: SQLAlchemyDB) -> None:
        self.db = db

    def context(self, datatype_key: str) -> DatatypeContext:
        model = DATATYPE_TO_MODEL.get(datatype_key)
        if model is None:
            raise DatatypeDataError(
                "unknown_datatype",
                f"数据类型 '{datatype_key}' 不存在",
                status_code=404,
            )
        return _build_context(datatype_key, model)

    def _table(self, ctx: DatatypeContext):
        return DATATYPE_TO_MODEL[ctx.datatype_key].__table__

    # ------------------- 查询 -------------------

    def _condition_from_filter(
        self, table, ctx: DatatypeContext, field: str, operator: str, raw: Any
    ) -> ColumnElement:
        spec = ctx.column(field)
        if spec is None:
            raise DatatypeDataError(
                "unknown_field", f"字段 {field} 不存在", status_code=422, details={"field": field}
            )
        if operator not in _FILTER_OPERATORS:
            raise DatatypeDataError(
                "invalid_operator",
                f"不支持的过滤操作符 {operator}",
                status_code=422,
                details={"field": field},
            )
        column = table.c[spec.name]
        if operator == "is_null":
            if not isinstance(raw, bool):
                raise DatatypeDataError(
                    "invalid_field_value",
                    f"字段 {field} 的 is_null 需要布尔值",
                    status_code=422,
                    details={"field": field},
                )
            return column.is_(None) if raw else column.is_not(None)
        if operator == "contains":
            if spec.value_type != "string":
                raise DatatypeDataError(
                    "invalid_operator",
                    f"字段 {field} 不支持文本包含过滤",
                    status_code=422,
                    details={"field": field},
                )
            return column.ilike(f"%{_coerce_value(spec, raw)}%")
        value = _coerce_value(spec, raw)
        comparison = {
            "eq": lambda c, v: c == v,
            "ne": lambda c, v: c != v,
            "gt": lambda c, v: c > v,
            "gte": lambda c, v: c >= v,
            "lt": lambda c, v: c < v,
            "lte": lambda c, v: c <= v,
        }[operator]
        return comparison(column, value)

    def _conditions(
        self,
        table,
        ctx: DatatypeContext,
        filters: list[dict[str, Any]],
        keyword: str | None,
    ) -> list[ColumnElement]:
        conditions: list[ColumnElement] = []
        for item in filters:
            conditions.append(
                self._condition_from_filter(
                    table, ctx, item["field"], item["operator"], item.get("value")
                )
            )
        normalized = (keyword or "").strip()
        if normalized and ctx.searchable_columns:
            pattern = f"%{normalized}%"
            conditions.append(
                or_(*(table.c[name].ilike(pattern) for name in ctx.searchable_columns))
            )
        return conditions

    def _order_clause(self, table, ctx: DatatypeContext, sort: str | None, order: str | None):
        direction = (order or "desc").lower()
        if direction not in _ORDER_VALUES:
            direction = "desc"
        if sort:
            spec = ctx.column(sort)
            if spec is None:
                raise DatatypeDataError(
                    "unknown_field", f"排序字段 {sort} 不存在", status_code=422
                )
            column = table.c[spec.name]
            return column.desc() if direction == "desc" else column.asc()
        # 默认按主键降序，保证分页稳定
        pk = table.c[ctx.pk_columns[0]] if ctx.pk_columns else None
        if pk is None:
            return None
        return pk.desc() if direction == "desc" else pk.asc()

    async def list_rows(
        self,
        ctx: DatatypeContext,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        filters: list[dict[str, Any]] | None = None,
        keyword: str | None = None,
        sort: str | None = None,
        order: str | None = None,
    ) -> DatatypeRowPage:
        safe_page = max(1, page)
        safe_size = min(max(1, page_size), MAX_PAGE_SIZE)
        table = self._table(ctx)
        conditions = self._conditions(table, ctx, filters or [], keyword)
        names = tuple(c.name for c in ctx.columns)
        order_clause = self._order_clause(table, ctx, sort, order)

        stmt = select(table)
        count_stmt = select(func.count()).select_from(table)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        if order_clause is not None:
            stmt = stmt.order_by(order_clause)
        stmt = stmt.limit(safe_size).offset((safe_page - 1) * safe_size)

        try:
            async with self.db.asession_scope() as session:
                total = int((await session.execute(count_stmt)).scalar() or 0)
                rows = (await session.execute(stmt)).all()
        except SQLAlchemyError as exc:
            raise _map_db_error(exc, action="list") from exc

        return DatatypeRowPage(
            items=[_serialize_row(names, row) for row in rows],
            total=total,
            page=safe_page,
            page_size=safe_size,
        )

    async def get_row(self, ctx: DatatypeContext, pk: dict[str, Any]) -> dict[str, Any]:
        table = self._table(ctx)
        key_clause = self._pk_clause(table, ctx, pk)
        names = tuple(c.name for c in ctx.columns)
        try:
            async with self.db.asession_scope() as session:
                row = (await session.execute(select(table).where(key_clause))).first()
        except SQLAlchemyError as exc:
            raise _map_db_error(exc, action="get") from exc
        if row is None:
            raise DatatypeDataError("row_not_found", "数据记录不存在", status_code=404)
        return _serialize_row(names, row)

    def _pk_clause(self, table, ctx: DatatypeContext, pk: dict[str, Any]):
        if not ctx.pk_columns:
            raise DatatypeDataError(
                "no_primary_key", "该数据模型没有主键，无法定位记录", status_code=409
            )
        clauses = []
        for name in ctx.pk_columns:
            if name not in pk or pk[name] is None:
                raise DatatypeDataError(
                    "missing_primary_key",
                    f"缺少主键字段 {name}",
                    status_code=422,
                    details={"field": name},
                )
            spec = ctx.column(name)
            assert spec is not None
            clauses.append(table.c[name] == _coerce_value(spec, pk[name]))
        return and_(*clauses)

    # ------------------- 写入 -------------------

    def _editable_values(
        self,
        ctx: DatatypeContext,
        values: dict[str, Any],
        *,
        require_all: bool,
    ) -> dict[str, Any]:
        if not isinstance(values, dict):
            raise DatatypeDataError("invalid_payload", "请求体必须是字段对象", status_code=422)
        coerced: dict[str, Any] = {}
        for name, raw in values.items():
            spec = ctx.column(name)
            if spec is None:
                raise DatatypeDataError(
                    "unknown_field",
                    f"字段 {name} 不存在",
                    status_code=422,
                    details={"field": name},
                )
            if not spec.editable:
                raise DatatypeDataError(
                    "readonly_field",
                    f"字段 {name} 不可写入",
                    status_code=422,
                    details={"field": name},
                )
            coerced[name] = _coerce_value(spec, raw)

        if not coerced:
            raise DatatypeDataError(
                "empty_payload",
                "没有可写入的字段" if require_all else "没有可更新的字段",
                status_code=422,
            )

        if require_all:
            for spec in ctx.columns:
                if spec.required and coerced.get(spec.name) is None:
                    raise DatatypeDataError(
                        "missing_required_field",
                        f"缺少必填字段 {spec.name}",
                        status_code=422,
                        details={"field": spec.name},
                    )
        return coerced

    async def create_row(self, ctx: DatatypeContext, values: dict[str, Any]) -> dict[str, Any]:
        table = self._table(ctx)
        coerced = self._editable_values(ctx, values, require_all=True)
        names = tuple(c.name for c in ctx.columns)
        try:
            async with self.db.asession_scope() as session:
                result = await session.execute(
                    table.insert().values(**coerced).returning(*table.c)
                )
                row = result.first()
                if row is None:
                    inserted = result.inserted_primary_key
                    key_clause = self._pk_clause(
                        table,
                        ctx,
                        {name: inserted[index] for index, name in enumerate(ctx.pk_columns)},
                    )
                    row = (await session.execute(select(table).where(key_clause))).first()
        except SQLAlchemyError as exc:
            raise _map_db_error(exc, action="create") from exc
        if row is None:
            raise DatatypeDataError("storage_error", "创建后无法读取记录", status_code=502)
        return _serialize_row(names, row)

    async def update_row(
        self, ctx: DatatypeContext, pk: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        table = self._table(ctx)
        coerced = self._editable_values(ctx, values, require_all=False)
        key_clause = self._pk_clause(table, ctx, pk)
        names = tuple(c.name for c in ctx.columns)
        try:
            async with self.db.asession_scope() as session:
                result = await session.execute(
                    table.update()
                    .where(key_clause)
                    .values(**coerced)
                    .returning(*table.c)
                )
                row = result.first()
        except SQLAlchemyError as exc:
            raise _map_db_error(exc, action="update") from exc
        if row is None:
            raise DatatypeDataError("row_not_found", "数据记录不存在", status_code=404)
        return _serialize_row(names, row)

    async def delete_row(self, ctx: DatatypeContext, pk: dict[str, Any]) -> None:
        table = self._table(ctx)
        key_clause = self._pk_clause(table, ctx, pk)
        try:
            async with self.db.asession_scope() as session:
                result = await session.execute(table.delete().where(key_clause))
        except SQLAlchemyError as exc:
            raise _map_db_error(exc, action="delete") from exc
        if result.rowcount == 0:
            raise DatatypeDataError("row_not_found", "数据记录不存在", status_code=404)


def parse_filters(raw: str | None) -> list[dict[str, Any]]:
    """解析查询串中的 filters JSON，校验为受支持的过滤项列表。"""
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DatatypeDataError("invalid_filters", "filters 不是合法 JSON", status_code=422) from exc
    if not isinstance(parsed, list):
        raise DatatypeDataError("invalid_filters", "filters 必须是数组", status_code=422)
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise DatatypeDataError("invalid_filters", f"filters[{index}] 必须是对象", status_code=422)
        field = item.get("field")
        operator = item.get("operator")
        if not isinstance(field, str) or not field.strip():
            raise DatatypeDataError("invalid_filters", f"filters[{index}].field 无效", status_code=422)
        if operator not in _FILTER_OPERATORS:
            raise DatatypeDataError(
                "invalid_filters", f"filters[{index}].operator 无效", status_code=422
            )
        normalized.append({"field": field.strip(), "operator": operator, "value": item.get("value")})
    return normalized


def parse_primary_key(raw: str) -> dict[str, Any]:
    """解析查询串中的 pk JSON，校验为字段对象。"""
    if not raw or not raw.strip():
        raise DatatypeDataError("missing_primary_key", "缺少主键参数", status_code=422)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DatatypeDataError("invalid_primary_key", "pk 不是合法 JSON", status_code=422) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise DatatypeDataError("invalid_primary_key", "pk 必须是非空对象", status_code=422)
    return parsed


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "DatatypeColumnSpec",
    "DatatypeContext",
    "DatatypeDataService",
    "DatatypeRowPage",
    "FilterOperator",
    "MAX_PAGE_SIZE",
    "parse_filters",
    "parse_primary_key",
]
