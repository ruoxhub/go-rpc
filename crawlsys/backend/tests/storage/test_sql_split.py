"""Tests for sql sub-package structure."""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from storage.sql import SQLAlchemyDB, Base
from storage.sql.sync import SyncSQLImpl
from storage.sql._async import (
    AsyncSQLImpl,
    _build_non_null_upsert_set,
    _resolve_upsert_index_elements,
)
from storage.sql._base import convert_sql_error, logger
from storage.exceptions import SQLOperationError
from models import Content, TkChallenge


def test_sql_imports():
    assert SQLAlchemyDB is not None
    assert Base is not None
    assert SyncSQLImpl is not None
    assert AsyncSQLImpl is not None


def test_convert_sql_error_generic():
    err = convert_sql_error(ValueError("test"))
    assert isinstance(err, SQLOperationError)


def test_convert_sql_error_no_result():
    try:
        from sqlalchemy.exc import NoResultFound
        from storage.exceptions import NotFoundError
        err = convert_sql_error(NoResultFound())
        assert isinstance(err, NotFoundError)
    except ImportError:
        import pytest
        pytest.skip("sqlalchemy not installed")


def test_convert_sql_error_integrity():
    try:
        from sqlalchemy.exc import IntegrityError
        from storage.exceptions import AlreadyExistsError
        err = convert_sql_error(IntegrityError("dup", None, None))
        assert isinstance(err, AlreadyExistsError)
    except ImportError:
        import pytest
        pytest.skip("sqlalchemy not installed")


def test_logger_exists():
    assert logger is not None


@pytest.mark.asyncio
async def test_asession_scope_reraises_domain_errors_unchanged():
    """业务异常（如 CatalogConflictError）不能被转成 SQL 错误，否则 404/409 会变 503。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    class DomainError(Exception):
        pass

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        with pytest.raises(DomainError):
            async with AsyncSQLImpl(engine).asession_scope():
                raise DomainError("still referenced")
    finally:
        await engine.dispose()


def test_resolve_upsert_index_elements_uses_composite_unique_key():
    assert _resolve_upsert_index_elements(Content, "content_id") == [
        "platform",
        "content_id",
    ]
    assert _resolve_upsert_index_elements(TkChallenge, "challenge_id") == ["challenge_id"]


def test_content_upsert_refreshes_detail_media_urls():
    assert "extend" in Content.update_fields


def test_build_non_null_upsert_set_uses_coalesce():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(TkChallenge)
    set_map = _build_non_null_upsert_set(TkChallenge, stmt, ["desc"])

    compiled = str(set_map["desc"].compile(dialect=postgresql.dialect())).lower()
    assert "coalesce" in compiled
    assert "excluded" in compiled
    assert "tk_challenge" in compiled
