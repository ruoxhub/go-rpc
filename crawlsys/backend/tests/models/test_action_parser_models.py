from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex

from models.action import Action
from models.action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from models.base import Base


def test_action_defaults_sampling_to_unsafe():
    assert Action(bs_id=1, ba_action="detail").ba_sample_safe is False


def test_parser_tables_are_registered_in_base_metadata():
    assert {
        "public.t_busi_action_parser_sample",
        "public.t_busi_action_parser_revision",
        "public.t_busi_action_parser_revision_sample",
    }.issubset(
        {f"{table.schema}.{table.name}" for table in Base.metadata.tables.values()}
    )


def test_sample_columns_and_action_reference_contract():
    table = ActionParserSample.__table__

    assert set(table.c.keys()) == {
        "sample_id",
        "ba_id",
        "request_params_redacted",
        "request_params_hmac_sha256",
        "request_hmac_key_version",
        "raw_object_key",
        "redacted_object_key",
        "response_sha256",
        "response_bytes",
        "sanitizer_version",
        "rpc_duration_ms",
        "created_at",
    }
    assert isinstance(
        table.c.request_params_redacted.type.dialect_impl(postgresql.dialect()),
        postgresql.JSONB,
    )
    assert isinstance(
        table.c.request_params_redacted.type.dialect_impl(sqlite.dialect()),
        sqlite.JSON,
    )
    assert {index.name for index in table.indexes} == {
        "idx_action_parser_sample_ba_id"
    }
    assert table.c.raw_object_key.unique is True
    assert table.c.redacted_object_key.unique is True
    ba_fk = next(iter(table.c.ba_id.foreign_keys))
    assert ba_fk.target_fullname == "public.t_busi_action.ba_id"
    assert ba_fk.ondelete == "RESTRICT"


def test_revision_columns_constraints_and_indexes():
    table = ActionParserRevision.__table__

    assert set(table.c.keys()) == {
        "revision_id",
        "ba_id",
        "revision_no",
        "status",
        "definition",
        "definition_sha256",
        "source",
        "source_sample_id",
        "restored_from_revision_id",
        "validation_report",
        "lock_version",
        "generation_metadata",
        "created_at",
        "updated_at",
        "published_at",
    }
    assert any(
        tuple(column.name for column in constraint.columns)
        == ("ba_id", "revision_no")
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert set(check_constraints) == {
        "ck_action_parser_revision_status",
        "ck_action_parser_revision_source",
    }
    assert check_constraints["ck_action_parser_revision_source"] == (
        "source IN ('manual', 'ai', 'restore')"
    )
    assert table.c.validation_report.nullable is True
    assert {index.name for index in table.indexes} == {
        "idx_action_parser_revision_ba_id",
        "idx_action_parser_revision_status",
        "uq_action_parser_revision_draft_per_action",
        "uq_action_parser_revision_published_per_action",
    }


def test_revision_has_partial_unique_draft_and_published_indexes():
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        sql = "\n".join(
            str(CreateIndex(index).compile(dialect=dialect))
            for index in ActionParserRevision.__table__.indexes
        )
        assert "WHERE status = 'draft'" in sql
        assert "WHERE status = 'published'" in sql


def test_sample_references_are_restrict_and_join_revision_is_cascade():
    source_fk = next(iter(ActionParserRevision.__table__.c.source_sample_id.foreign_keys))
    sample_fk = next(iter(ActionParserRevisionSample.__table__.c.sample_id.foreign_keys))
    revision_fk = next(
        iter(ActionParserRevisionSample.__table__.c.revision_id.foreign_keys)
    )
    assert source_fk.ondelete == "RESTRICT"
    assert sample_fk.ondelete == "RESTRICT"
    assert revision_fk.ondelete == "CASCADE"


def test_restored_revision_reference_is_nullable_and_set_null_on_delete():
    column = ActionParserRevision.__table__.c.restored_from_revision_id
    restored_from_fk = next(iter(column.foreign_keys))

    assert column.nullable is True
    assert restored_from_fk.ondelete == "SET NULL"


def test_revision_sample_has_composite_primary_key():
    table = ActionParserRevisionSample.__table__

    assert tuple(column.name for column in table.primary_key.columns) == (
        "revision_id",
        "sample_id",
    )
    assert set(table.c.keys()) == {
        "revision_id",
        "sample_id",
        "sample_sha256",
        "created_at",
    }
