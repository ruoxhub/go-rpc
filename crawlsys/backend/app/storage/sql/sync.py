# -*- coding: utf-8 -*-
"""Synchronous SQLAlchemy implementation."""
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
)
from contextlib import contextmanager

from sqlalchemy import (
    Engine,
    and_,
    delete,
    func,
    select,
    update,
    text,
    exists as sql_exists,
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ._base import (
    _BaseAlchemyHelper,
    Base,
    logger,
    convert_sql_error,
)

T = TypeVar("T")


class SyncSQLImpl:
    """Synchronous SQLAlchemy implementation."""

    def __init__(self, engine: Engine):
        self.engine = engine

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Synchronous session context manager."""
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Database transaction failed: {e}")
                raise

    # ------------------- Synchronous CRUD -------------------
    def add(self, obj: Any):
        """Add a single object synchronously."""
        with self.session_scope() as s:
            s.add(obj)

    def adds(self, objs: List[Any]):
        """Batch add objects synchronously."""
        with self.session_scope() as s:
            s.add_all(objs)

    def query(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Query multiple records synchronously."""
        with self.session_scope() as s:
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if order_by:
                stmt = stmt.order_by(
                    *_BaseAlchemyHelper.build_order(class_model, order_by)
                )
            if limit:
                stmt = stmt.limit(limit)
            if offset:
                stmt = stmt.offset(offset)
            return list(s.scalars(stmt).all())

    def query_one(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[T]:
        """Query a single record synchronously."""
        with self.session_scope() as s:
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            return s.scalars(stmt).first()

    def count(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count records synchronously."""
        with self.session_scope() as s:
            stmt = select(func.count()).select_from(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            return s.scalar(stmt) or 0

    def merge(self, obj: Any) -> None:
        """Merge an object (update or insert) synchronously."""
        with self.session_scope() as s:
            s.merge(obj)

    def execute_sql(
        self, sql: str, params: Optional[Dict[str, Any]] = None
    ) -> Union[List[Any], int]:
        """Execute raw SQL synchronously."""
        with self.session_scope() as s:
            result = s.execute(text(sql), params or {})
            if result.returns_rows:  # type: ignore[attr-defined]
                return list(result.fetchall())
            else:
                return result.rowcount  # type: ignore[attr-defined]

    def bulk_insert(self, objs: List[Any], batch_size: int = 1000) -> None:
        """Batch insert objects synchronously.

        Args:
            objs: List of objects to insert
            batch_size: Batch size, default 1000
        """
        if not objs:
            return
        with self.session_scope() as s:
            for i in range(0, len(objs), batch_size):
                batch = objs[i : i + batch_size]
                s.bulk_save_objects(batch, return_defaults=False, preserve_order=False)

    def paginate(
        self,
        class_model: Type[T],
        page: int = 1,
        page_size: int = 20,
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
    ) -> tuple[List[T], int]:
        """Paginated query synchronously.

        Returns:
            (items, total) tuple
        """
        with self.session_scope() as s:
            stmt_count = select(func.count()).select_from(class_model)
            stmt_count = _BaseAlchemyHelper.apply_filters(
                stmt_count, class_model, filter
            )
            total = s.scalar(stmt_count) or 0
            stmt = select(class_model)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if order_by:
                stmt = stmt.order_by(
                    *_BaseAlchemyHelper.build_order(class_model, order_by)
                )
            offset = (page - 1) * page_size
            stmt = stmt.limit(page_size).offset(offset)
            items = list(s.scalars(stmt).all())
            return items, total

    def exists(
        self, class_model: Type[Base], filter: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a record exists synchronously (optimized with EXISTS subquery)."""
        with self.session_scope() as s:
            subq = select(class_model)
            subq = _BaseAlchemyHelper.apply_filters(subq, class_model, filter)
            stmt = select(sql_exists(subq))
            return s.scalar(stmt) or False

    def bulk_update(
        self,
        class_model: Type[Base],
        data: List[Dict[str, Any]],
        key_fields: List[str],
        batch_size: int = 500,
    ) -> int:
        """Batch update based on business unique keys synchronously.

        Uses Core SQL to execute updates one by one, bypassing ORM primary key restrictions.
        """
        if not data:
            return 0

        total_updated = 0
        processed_count = 0
        pk_columns = list(class_model.__table__.primary_key.columns)
        primary_key = pk_columns[0].name if pk_columns else None

        with Session(self.engine, expire_on_commit=False) as s:
            try:
                for item in data:
                    where_params = {
                        k: item.get(k) for k in key_fields if item.get(k) is not None
                    }
                    if len(where_params) != len(key_fields):
                        continue

                    set_params = {
                        k: v
                        for k, v in item.items()
                        if k not in key_fields and k != primary_key
                    }
                    if not set_params:
                        continue

                    stmt = (
                        update(class_model)
                        .where(
                            and_(
                                *[
                                    getattr(class_model, k) == v
                                    for k, v in where_params.items()
                                ]
                            )
                        )
                        .values(**set_params)
                    )

                    result = s.execute(stmt)
                    total_updated += (
                        result.rowcount if hasattr(result, "rowcount") else 1
                    )
                    processed_count += 1

                    if processed_count % batch_size == 0:
                        s.commit()
                s.commit()
            except Exception as e:
                s.rollback()
                logger.error(f"Batch update failed: {e}")
                raise convert_sql_error(e)

        return total_updated

    def aggregate(
        self,
        class_model: Type[Base],
        aggregations: Dict[str, tuple],
        filter: Optional[Dict[str, Any]] = None,
        group_by: Optional[List[str]] = None,
    ) -> List[Any]:
        """Aggregate query synchronously.

        Args:
            aggregations: Aggregation config, format: {alias: (field, func)}
                         Supported functions: count, sum, avg, min, max
            filter: Filter conditions
            group_by: Group by fields
        """
        with self.session_scope() as s:
            agg_columns = []
            for alias, (field, agg_func) in aggregations.items():
                col = _BaseAlchemyHelper._build_aggregation_column(
                    class_model, field, agg_func, alias
                )
                if col is not None:
                    agg_columns.append(col)

            if group_by:
                for field in group_by:
                    if hasattr(class_model, field):
                        agg_columns.append(getattr(class_model, field))

            stmt = select(*agg_columns)
            stmt = _BaseAlchemyHelper.apply_filters(stmt, class_model, filter)
            if group_by:
                stmt = stmt.group_by(
                    *[
                        getattr(class_model, f)
                        for f in group_by
                        if hasattr(class_model, f)
                    ]
                )
            result = s.execute(stmt)
            return result.fetchall()

    @contextmanager
    def transaction(self, auto_commit: bool = False):
        """Synchronous manual transaction context manager."""
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                yield session
                if auto_commit:
                    session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"Manual transaction failed: {e}")
                raise convert_sql_error(e)

    def update(
        self,
        class_model: Type[Base],
        filter: Dict[str, Any],
        update_data: Dict[str, Any],
    ) -> int:
        """Update records synchronously.

        Returns:
            Number of updated rows
        """
        with self.session_scope() as s:
            stmt = (
                update(class_model)
                .where(and_(*_BaseAlchemyHelper.build_conditions(class_model, filter)))
                .values(**update_data)
            )
            result = s.execute(stmt)
            return result.rowcount if hasattr(result, "rowcount") else 0

    def delete(self, class_model: Type[Base], filter: Dict[str, Any]) -> int:
        """Delete records synchronously.

        Returns:
            Number of deleted rows
        """
        with self.session_scope() as s:
            stmt = delete(class_model).where(
                and_(*_BaseAlchemyHelper.build_conditions(class_model, filter))
            )
            result = s.execute(stmt)
            return result.rowcount if hasattr(result, "rowcount") else 0

    def get(self, class_model: Type[T], pk: Any) -> Optional[T]:
        """Get a record by primary key synchronously."""
        with self.session_scope() as s:
            return s.get(class_model, pk)

    def get_pool_status(self) -> Dict[str, Any]:
        return _BaseAlchemyHelper._get_pool_status(self.engine)

    def remove_duplicates(
        self,
        class_model: Type[Base],
        duplicate_fields: List[str],
        keep: Literal["first", "last"] = "first",
        order_by_field: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_window_function: bool = False,
    ) -> int:
        """Remove duplicate rows based on ``duplicate_fields``."""
        delete_sql = _BaseAlchemyHelper._build_remove_duplicates_sql(
            class_model, duplicate_fields, keep, order_by_field, use_window_function
        )
        with self.session_scope() as s:
            result = s.execute(text(delete_sql))
            return result.rowcount

    def init_db(self, drop_existing: bool = False):
        """Create all tables defined in ``Base`` metadata.
        If ``drop_existing`` is True, existing tables are dropped first.
        """
        try:
            if drop_existing:
                logger.warning("Dropping all existing tables...")
                Base.metadata.drop_all(self.engine)
            Base.metadata.create_all(self.engine)
            logger.info("Database tables initialized successfully.")
        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    def close(self):
        """Dispose the underlying engine."""
        self.engine.dispose()
