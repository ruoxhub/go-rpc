"""BusiSearchKeyword ORM model — column + table shape tests."""
from pathlib import Path

from models.keyword import BusiSearchKeyword


def test_table_name():
    assert BusiSearchKeyword.__tablename__ == "t_busi_search_keyword"


def test_schema_is_public():
    args = BusiSearchKeyword.__table_args__
    assert isinstance(args, tuple)
    assert {"schema": "public"} in args


def test_columns_present():
    col_names = {c.name for c in BusiSearchKeyword.__table__.columns}
    assert {"id", "platform", "keyword", "is_crawled", "created_at"} <= col_names


def test_platform_foreign_key():
    fk_targets = {fk.target_fullname for fk in BusiSearchKeyword.__table__.columns["platform"].foreign_keys}
    assert "public.t_busi_platform.bs_platform_code" in fk_targets


def test_index_on_platform():
    idx_names = {idx.name for idx in BusiSearchKeyword.__table__.indexes}
    assert "idx_bsk_platform" in idx_names


def test_create_sql_includes_is_crawled_column_and_migration():
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "sql"
        / "2026-06-30_create_t_busi_search_keyword.sql"
    )
    sql = sql_path.read_text(encoding="utf-8").lower()

    assert "is_crawled" in sql
    assert "add column if not exists is_crawled" in sql
