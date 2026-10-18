"""数据记录管理路由：对已注册数据类型对应的物理表做行级 CRUD。

- 表名、列名与主键全部来自服务端内省，不接受客户端输入。
- 业务错误以 ``DatatypeDataError`` 抛出，由应用级处理器映射为稳定 JSON。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from api.crawler.schemas import (
    DatatypeRowColumnRead,
    DatatypeRowCreate,
    DatatypeRowDeleteResponse,
    DatatypeRowPageResponse,
    DatatypeRowResponse,
    DatatypeRowsMetaResponse,
    DatatypeRowUpdate,
)
from api.deps import get_db
from services.datatype_data import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DatatypeContext,
    DatatypeDataService,
    parse_filters,
    parse_primary_key,
)
from storage import SQLAlchemyDB

router = APIRouter(prefix="/api/crawler/datatypes", tags=["datatype-rows"])

_FILTERS_DESCRIPTION = (
    "JSON 数组，元素形如 {\"field\": \"platform\", \"operator\": \"eq\", \"value\": \"bilibili\"}"
)


def _meta_response(ctx: DatatypeContext) -> DatatypeRowsMetaResponse:
    return DatatypeRowsMetaResponse(
        datatype_key=ctx.datatype_key,
        table_name=ctx.table_name,
        model_name=ctx.model_name,
        description=ctx.description,
        unique_field=ctx.unique_field,
        pk_columns=list(ctx.pk_columns),
        columns=[
            DatatypeRowColumnRead(
                name=column.name,
                sql_type=column.sql_type,
                value_type=column.value_type,
                nullable=column.nullable,
                primary_key=column.primary_key,
                comment=column.comment,
                max_length=column.max_length,
                editable=column.editable,
                required=column.required,
            )
            for column in ctx.columns
        ],
    )


@router.get("/{datatype_key}/rows/meta", response_model=DatatypeRowsMetaResponse)
async def get_rows_meta(
    datatype_key: str,
    db: SQLAlchemyDB = Depends(get_db),
) -> DatatypeRowsMetaResponse:
    """返回该数据类型的数据记录编辑器元数据（列契约、主键、搜索列）。"""
    service = DatatypeDataService(db)
    return _meta_response(service.context(datatype_key))


@router.get("/{datatype_key}/rows", response_model=DatatypeRowPageResponse)
async def list_rows(
    datatype_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    keyword: str | None = Query(None, description="对所有文本列做不区分大小写的包含匹配"),
    sort: str | None = Query(None, description="排序字段名，缺省按主键降序"),
    order: str | None = Query(None, description="asc 或 desc"),
    filters: str | None = Query(None, description=_FILTERS_DESCRIPTION),
    db: SQLAlchemyDB = Depends(get_db),
) -> DatatypeRowPageResponse:
    """分页查询数据记录，支持关键字与字段过滤。"""
    service = DatatypeDataService(db)
    ctx = service.context(datatype_key)
    result = await service.list_rows(
        ctx,
        page=page,
        page_size=page_size,
        filters=parse_filters(filters),
        keyword=keyword,
        sort=sort,
        order=order,
    )
    return DatatypeRowPageResponse(
        items=result.items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post(
    "/{datatype_key}/rows",
    response_model=DatatypeRowResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_row(
    datatype_key: str,
    payload: DatatypeRowCreate,
    db: SQLAlchemyDB = Depends(get_db),
) -> DatatypeRowResponse:
    """新增一条数据记录；自增主键与带默认值的列可省略。"""
    service = DatatypeDataService(db)
    ctx = service.context(datatype_key)
    item = await service.create_row(ctx, payload.values)
    return DatatypeRowResponse(item=item)


@router.put("/{datatype_key}/rows", response_model=DatatypeRowResponse)
async def update_row(
    datatype_key: str,
    payload: DatatypeRowUpdate,
    pk: str = Query(..., description="主键键值对 JSON，形如 {\"id\": 1}"),
    db: SQLAlchemyDB = Depends(get_db),
) -> DatatypeRowResponse:
    """按主键更新一条数据记录；只更新提交中出现的字段。"""
    service = DatatypeDataService(db)
    ctx = service.context(datatype_key)
    item = await service.update_row(ctx, parse_primary_key(pk), payload.values)
    return DatatypeRowResponse(item=item)


@router.delete("/{datatype_key}/rows", response_model=DatatypeRowDeleteResponse)
async def delete_row(
    datatype_key: str,
    pk: str = Query(..., description="主键键值对 JSON，形如 {\"id\": 1}"),
    db: SQLAlchemyDB = Depends(get_db),
) -> DatatypeRowDeleteResponse:
    """按主键删除一条数据记录。"""
    service = DatatypeDataService(db)
    ctx = service.context(datatype_key)
    await service.delete_row(ctx, parse_primary_key(pk))
    return DatatypeRowDeleteResponse(deleted=True)


__all__ = ["router"]
