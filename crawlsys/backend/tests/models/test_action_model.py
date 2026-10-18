from pathlib import Path

import pytest

from models.action import Action, ActionHttpMethod


def test_action_normalizes_business_fields():
    action = Action(bs_id=1, ba_action=" getUserInfo ", ba_api_method=" post ")

    assert action.ba_action == "getUserInfo"
    assert action.ba_api_method == ActionHttpMethod.POST.value


@pytest.mark.parametrize("name", ["", "   "])
def test_action_rejects_blank_name(name):
    with pytest.raises(ValueError, match="不能为空"):
        Action(bs_id=1, ba_action=name)


def test_action_rejects_unsupported_http_method():
    with pytest.raises(ValueError, match="不支持的 HTTP 方法"):
        Action(bs_id=1, ba_action="getUserInfo", ba_api_method="CONNECT")


def test_action_parses_params_schema():
    action = Action(
        bs_id=1,
        ba_action="getUserInfo",
        ba_params_schema='{"type": "object"}',
    )

    assert action.params_schema == {"type": "object"}


def test_action_invalid_params_schema_returns_none():
    action = Action(bs_id=1, ba_action="getUserInfo", ba_params_schema="not-json")

    assert action.params_schema is None


def test_existing_database_migration_covers_action_and_task_schema_changes():
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "sql"
        / "2026-08-05_add_action_task_constraints_and_indexes.sql"
    )
    sql = sql_path.read_text(encoding="utf-8").lower()

    for constraint in (
        "ck_action_name_not_blank",
        "ck_action_http_method",
        "ck_task_status",
        "ck_task_attempts_non_negative",
    ):
        assert f"conname = '{constraint}'" in sql
        assert f"add constraint {constraint}" in sql

    for index in (
        "idx_action_platform_enabled",
        "idx_task_ready",
        "idx_task_platform_status",
        "idx_task_action_id",
    ):
        assert f"create index concurrently if not exists {index}" in sql


def test_action_parser_migration_is_idempotent_and_matches_orm_contract():
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "sql"
        / "2026-08-10_create_action_parser_configuration.sql"
    )
    sql = sql_path.read_text(encoding="utf-8").lower()
    normalized_sql = " ".join(sql.split())
    executable_sql = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ).strip()

    assert executable_sql.startswith("begin;")
    assert executable_sql.endswith("commit;")
    assert (
        "alter table public.t_busi_action "
        "add column if not exists ba_sample_safe boolean not null default false"
    ) in normalized_sql
    for table in (
        "t_busi_action_parser_sample",
        "t_busi_action_parser_revision",
        "t_busi_action_parser_revision_sample",
    ):
        assert f"create table if not exists public.{table}" in sql
    for index in (
        "idx_action_parser_sample_ba_id",
        "idx_action_parser_revision_ba_id",
        "idx_action_parser_revision_status",
        "uq_action_parser_revision_draft_per_action",
        "uq_action_parser_revision_published_per_action",
    ):
        assert f"create index if not exists {index}" in sql or (
            f"create unique index if not exists {index}" in sql
        )
    assert "foreign key (source_sample_id)" in sql
    assert "check (source in ('manual', 'ai', 'restore'))" in normalized_sql
    assert "validation_report jsonb not null" not in normalized_sql
    assert "validation_report jsonb" in normalized_sql
    assert (
        "references public.t_busi_action_parser_sample(sample_id) on delete restrict"
        in normalized_sql
    )
    assert (
        "references public.t_busi_action_parser_revision(revision_id) on delete set null"
        in normalized_sql
    )
    assert "foreign key (revision_id)" in sql
    assert (
        "references public.t_busi_action_parser_revision(revision_id) on delete cascade"
        in normalized_sql
    )


def test_action_schema_source_migration_and_constraints():
    sql_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "sql"
        / "2026-09-17_add_action_schema_source.sql"
    )
    assert sql_path.exists(), "Migration SQL file must exist"
    sql = sql_path.read_text(encoding="utf-8").lower()

    assert "add column if not exists ba_schema_source varchar(16) default 'synced'" in sql
    assert "add column if not exists ba_synced_at timestamptz" in sql
    assert "ck_action_schema_source" in sql
    assert "ba_schema_source in ('synced', 'manual')" in sql

    # 验证 ORM 字段声明
    columns = Action.__table__.columns
    assert "ba_schema_source" in columns
    assert "ba_synced_at" in columns
    assert columns["ba_schema_source"].nullable is True
    assert columns["ba_synced_at"].nullable is True

