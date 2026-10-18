# -*- coding: utf-8 -*-
"""Shared imports, driver maps, URL helpers, logger, and error conversion
for the SQL storage sub-package.
"""
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

from sqlalchemy import (
    Engine,
    create_engine,
    URL,
    and_,
    or_,
    asc,
    desc,
    delete,
    func,
    select,
    update,
    text,
    exists as sql_exists,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import Session, DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession

from utils.log import get_logger
from storage.exceptions import (
    ConnectionError as StoreConnectionError,
    OperationError,
    NotFoundError,
    AlreadyExistsError,
    SQLOperationError,
)

logger = get_logger("storage.sql")

T = TypeVar("T")


try:
    from models.base import Base
except ImportError:
    class Base(DeclarativeBase):
        pass


# ---------------------------------------------------------------------------
# Driver mapping: backend -> (sync_driver, async_driver)
# ---------------------------------------------------------------------------
DRIVER_MAPPING = {
    # MySQL
    "mysql": ("mysql+pymysql", "mysql+aiomysql"),
    "mysql+pymysql": ("mysql+pymysql", "mysql+aiomysql"),
    "mysql+mysqldb": ("mysql+mysqldb", "mysql+aiomysql"),
    "mysql+aiomysql": ("mysql+pymysql", "mysql+aiomysql"),
    "mysql+asyncmy": ("mysql+pymysql", "mysql+asyncmy"),
    # PostgreSQL
    "postgresql": ("postgresql+psycopg2", "postgresql+asyncpg"),
    "postgres": ("postgresql+psycopg2", "postgresql+asyncpg"),
    "postgresql+psycopg2": ("postgresql+psycopg2", "postgresql+asyncpg"),
    "postgresql+asyncpg": ("postgresql+psycopg2", "postgresql+asyncpg"),
    "postgresql+psycopg": (
        "postgresql+psycopg",
        "postgresql+psycopg",
    ),  # psycopg3 supports sync/async
    # SQLite
    "sqlite": ("sqlite", "sqlite+aiosqlite"),
    "sqlite+aiosqlite": ("sqlite", "sqlite+aiosqlite"),
    # SQL Server
    "mssql": ("mssql+pyodbc", "mssql+aioodbc"),
    "mssql+pyodbc": ("mssql+pyodbc", "mssql+aioodbc"),
    "mssql+aioodbc": ("mssql+pyodbc", "mssql+aioodbc"),
    # Oracle (async support is limited)
    "oracle": ("oracle+cx_oracle", "oracle+cx_oracle"),
    "oracle+cx_oracle": ("oracle+cx_oracle", "oracle+cx_oracle"),
}


OPERATOR_MAPPING: Dict[str, Callable] = {
    "eq": lambda col, val: col == val,
    "ne": lambda col, val: col != val,
    "gt": lambda col, val: col > val,
    "lt": lambda col, val: col < val,
    "ge": lambda col, val: col >= val,
    "le": lambda col, val: col <= val,
    "like": lambda col, val: col.like(val),
    "ilike": lambda col, val: col.ilike(val),
    "in": lambda col, val: col.in_(val) if isinstance(val, list) else None,
    "between": lambda col, val: col.between(val[0], val[1])
    if isinstance(val, (list, tuple)) and len(val) == 2
    else None,
    "is_null": lambda col, val: col.is_(None),
    "is_not_null": lambda col, val: col.is_not(None),
    "startswith": lambda col, val: col.startswith(val),
    "endswith": lambda col, val: col.endswith(val),
    "contains": lambda col, val: col.contains(val),
    "not_in": lambda col, val: col.notin_(val) if isinstance(val, list) else None,
    "not_like": lambda col, val: col.notlike(val),
    "not_ilike": lambda col, val: col.notilike(val),
    "not_between": lambda col, val: ~col.between(val[0], val[1])
    if isinstance(val, (list, tuple)) and len(val) == 2
    else None,
}


# ---------------------------------------------------------------------------
# Error conversion
# ---------------------------------------------------------------------------
def convert_sql_error(exc: Exception) -> OperationError:
    """Convert SQLAlchemy exceptions to StoreError subclasses."""
    try:
        from sqlalchemy.exc import NoResultFound, IntegrityError, OperationalError, SQLAlchemyError
        if isinstance(exc, NoResultFound):
            return NotFoundError(str(exc), original_error=exc)
        if isinstance(exc, IntegrityError):
            return AlreadyExistsError(str(exc), original_error=exc)
        if isinstance(exc, OperationalError):
            return StoreConnectionError(str(exc), original_error=exc)
        if isinstance(exc, SQLAlchemyError):
            return SQLOperationError(str(exc), cause=exc)
    except ImportError:
        pass
    return SQLOperationError(str(exc), cause=exc)


# ---------------------------------------------------------------------------
# Shared helper class
# ---------------------------------------------------------------------------
class _BaseAlchemyHelper:
    """Shared static helper methods for sync and async implementations."""

    @staticmethod
    def _apply_operator(column: Any, op: str, value: Any) -> Optional[Any]:
        """Apply an operator to a column, returning a condition expression or None."""
        op_func = OPERATOR_MAPPING.get(op)
        return op_func(column, value) if op_func else None

    @staticmethod
    def _build_single_condition(class_model, key: str, value: Any) -> Optional[Any]:
        """Build a single condition expression from a ``field__op`` key."""
        field_name, _, op = key.partition("__")
        op = op or "eq"
        if not hasattr(class_model, field_name):
            return None
        column = getattr(class_model, field_name)
        return _BaseAlchemyHelper._apply_operator(column, op, value)

    @staticmethod
    def build_conditions(
        class_model, filters: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Dynamically build filter conditions.
        Supports AND logic by default and OR logic when keys start with ``or__``.
        """
        if not filters:
            return []

        conditions: List[Any] = []
        build = _BaseAlchemyHelper._build_single_condition

        for key, value in filters.items():
            if key.startswith("or__"):
                or_conditions = [
                    cond
                    for or_key, or_value in value.items()
                    if (cond := build(class_model, or_key, or_value)) is not None
                ]
                if or_conditions:
                    conditions.append(or_(*or_conditions))
            else:
                cond = build(class_model, key, value)
                if cond is not None:
                    conditions.append(cond)

        return conditions

    @staticmethod
    def build_order(
        class_model, order_by: Optional[Dict[str, str]] = None
    ) -> List[Any]:
        """Build ordering expressions from a dict ``{field: direction}``."""
        if not order_by:
            return []
        order_exprs: List[Any] = []
        for field, direction in order_by.items():
            if hasattr(class_model, field):
                column = getattr(class_model, field)
                order_exprs.append(
                    desc(column) if direction.lower() == "desc" else asc(column)
                )
        return order_exprs

    @staticmethod
    def apply_filters(stmt, class_model, filters: Optional[Dict[str, Any]] = None):
        """Apply built conditions to a SQLAlchemy statement."""
        if not filters:
            return stmt
        conditions = _BaseAlchemyHelper.build_conditions(class_model, filters)
        if not conditions:
            return stmt
        and_conditions: List[Any] = []
        or_conditions: List[Any] = []
        for cond in conditions:
            if hasattr(cond, "clauses") and str(cond.operator) == "operator.or_":
                or_conditions.append(cond)
            else:
                and_conditions.append(cond)
        if and_conditions and or_conditions:
            stmt = stmt.where(and_(*and_conditions), *or_conditions)
        elif or_conditions:
            stmt = stmt.where(*or_conditions)
        else:
            stmt = stmt.where(and_(*conditions))
        return stmt

    @staticmethod
    def _parse_database_url(
        driver: str,
        username: Optional[str],
        password: Optional[str],
        host: Optional[str],
        port: Optional[int],
        database: str,
        amode: bool,
    ) -> URL:
        """Build a database URL from separated parameters, auto-mapping to sync/async driver."""
        target_driver = None
        if driver in DRIVER_MAPPING:
            sync_driver, adriver = DRIVER_MAPPING[driver]
            target_driver = adriver if amode else sync_driver
        else:
            backend = driver.split("+")[0]
            if backend in DRIVER_MAPPING:
                sync_driver, adriver = DRIVER_MAPPING[backend]
                target_driver = adriver if amode else sync_driver
                logger.warning(f"Unknown driver '{driver}', using backend '{backend}' default mapping: {target_driver}")
            else:
                target_driver = driver
                logger.warning(f"Unrecognized driver '{driver}', using as-is. Ensure the database driver package is installed.")

        is_sqlite = driver.startswith("sqlite")
        return URL.create(
            drivername=target_driver,
            username=username if not is_sqlite else None,
            password=password if not is_sqlite else None,
            host=host if not is_sqlite else None,
            port=port if not is_sqlite else None,
            database=database,
        )

    @staticmethod
    def _build_aggregation_column(
        class_model, field: str, agg_func: str, alias: str
    ) -> Any:
        """Build an aggregation function column."""
        column = getattr(class_model, field) if field != "*" else text("*")
        agg_mapping = {
            "count": func.count,
            "sum": func.sum,
            "avg": func.avg,
            "min": func.min,
            "max": func.max,
        }
        agg_fn = agg_mapping.get(agg_func.lower())
        if agg_fn:
            return agg_fn(column).label(alias)
        return None

    @staticmethod
    def _build_remove_duplicates_sql(
        class_model,
        duplicate_fields: List[str],
        keep: Literal["first", "last"] = "first",
        order_by_field: Optional[str] = None,
        use_window_function: bool = False,
    ) -> str:
        """Build a deduplication DELETE SQL statement for sync/async use."""
        if not duplicate_fields:
            raise ValueError("duplicate_fields must be provided")

        table_name = class_model.__tablename__
        valid_columns = {col.name for col in class_model.__table__.columns}
        for field in duplicate_fields:
            if field not in valid_columns:
                raise ValueError(f"Field '{field}' is not a valid column in the model")
        if order_by_field and order_by_field not in valid_columns:
            raise ValueError(f"Order field '{order_by_field}' is not a valid column in the model")

        partition_by = ", ".join(duplicate_fields)
        pk_columns = list(class_model.__table__.primary_key.columns)
        primary_key_name = pk_columns[0].name if pk_columns else "id"
        order_direction = "ASC" if keep == "first" else "DESC"
        order_clause = f"{order_by_field or primary_key_name} {order_direction}"

        if use_window_function:
            subquery = f"""SELECT {primary_key_name} FROM (
                SELECT {primary_key_name}, ROW_NUMBER() OVER (PARTITION BY {partition_by} ORDER BY {order_clause}) AS rn
                FROM {table_name}
            ) AS sub WHERE rn > 1"""
            return f"DELETE FROM {table_name} WHERE {primary_key_name} IN ({subquery})"

        agg_func = "MIN" if keep == "first" else "MAX"
        keep_ids_sql = f"SELECT {agg_func}({primary_key_name}) FROM {table_name} GROUP BY {partition_by}"
        return f"DELETE FROM {table_name} WHERE {primary_key_name} NOT IN ({keep_ids_sql})"

    @staticmethod
    def _get_pool_status(engine) -> Dict[str, Any]:
        """Get connection pool status, shared by sync/async."""
        try:
            pool = engine.pool
            return {
                "size": pool.size() if hasattr(pool, 'size') else -1,
                "checkedin": pool.checkedin() if hasattr(pool, 'checkedin') else -1,
                "checkedout": pool.checkedout() if hasattr(pool, 'checkedout') else -1,
                "overflow": pool.overflow() if hasattr(pool, 'overflow') else -1,
            }
        except (AttributeError, NotImplementedError) as e:
            logger.warning(f"Unable to get connection pool status: {e}")
            return {
                "size": -1, "checkedin": -1, "checkedout": -1,
                "overflow": -1, "error": str(e),
            }


@runtime_checkable
class StoreProtocol(Protocol):
    """Storage implementation protocol defining the common interface for SyncSQLImpl and AsyncSQLImpl."""

    engine: Any

    def session_scope(self) -> Generator[Session, None, None]:
        """Synchronous session context manager."""
        ...

    def asession_scope(self) -> AsyncGenerator[AsyncSession, None]:
        """Asynchronous session context manager."""
        ...

    def add(self, obj: Any) -> None:
        """Add a single object."""
        ...

    def adds(self, objs: List[Any]) -> None:
        """Batch add objects."""
        ...

    def query(
        self,
        class_model: Type[T],
        filter: Optional[Dict[str, Any]] = None,
        order_by: Optional[Dict[str, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """Query multiple records."""
        ...

    def get_pool_status(self) -> Dict[str, Any]:
        """Get connection pool status."""
        ...

    def close(self) -> None:
        """Close the connection."""
        ...
