"""Action 动态解析器的采样与版本化定义模型。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


JsonColumn = JSON().with_variant(JSONB, "postgresql")


class ActionParserSample(Base):
    """经脱敏后可用于解析器生成和验证的长期采样元数据。"""

    __tablename__ = "t_busi_action_parser_sample"
    __table_args__ = (
        Index("idx_action_parser_sample_ba_id", "ba_id"),
        {"schema": "public"},
    )

    sample_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    ba_id: Mapped[int] = mapped_column(
        ForeignKey("public.t_busi_action.ba_id", ondelete="RESTRICT"), nullable=False
    )
    request_params_redacted: Mapped[dict] = mapped_column(JsonColumn, nullable=False)
    request_params_hmac_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hmac_key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_object_key: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True
    )
    redacted_object_key: Mapped[str] = mapped_column(
        String(512), nullable=False, unique=True
    )
    response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sanitizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rpc_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ActionParserRevision(Base):
    """Action 解析定义的不可变编号版本及其发布状态。"""

    __tablename__ = "t_busi_action_parser_revision"
    __table_args__ = (
        UniqueConstraint(
            "ba_id", "revision_no", name="uq_action_parser_revision_number"
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_action_parser_revision_status",
        ),
        CheckConstraint(
            "source IN ('manual', 'ai', 'restore')",
            name="ck_action_parser_revision_source",
        ),
        Index("idx_action_parser_revision_ba_id", "ba_id"),
        Index("idx_action_parser_revision_status", "status"),
        Index(
            "uq_action_parser_revision_draft_per_action",
            "ba_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
            sqlite_where=text("status = 'draft'"),
        ),
        Index(
            "uq_action_parser_revision_published_per_action",
            "ba_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
        {"schema": "public"},
    )

    revision_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    ba_id: Mapped[int] = mapped_column(
        ForeignKey("public.t_busi_action.ba_id", ondelete="RESTRICT"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    definition: Mapped[dict] = mapped_column(JsonColumn, nullable=False)
    definition_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sample_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "public.t_busi_action_parser_sample.sample_id", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    restored_from_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "public.t_busi_action_parser_revision.revision_id", ondelete="SET NULL"
        ),
        nullable=True,
    )
    validation_report: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    lock_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    generation_metadata: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ActionParserRevisionSample(Base):
    """一个 Revision 最近用于预览或验证的 Sample 集合。"""

    __tablename__ = "t_busi_action_parser_revision_sample"
    __table_args__ = ({"schema": "public"},)

    revision_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.t_busi_action_parser_revision.revision_id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    sample_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.t_busi_action_parser_sample.sample_id", ondelete="RESTRICT"
        ),
        primary_key=True,
    )
    sample_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
