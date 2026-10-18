"""Immutable prompt-rule metadata and version models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentPromptRuleVersionStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AgentPromptRule(Base):
    __tablename__ = "t_agent_prompt_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_published_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "public.t_agent_prompt_rule_version.id",
            name="fk_agent_prompt_rule_active_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = ({"schema": "public"},)


class AgentPromptRuleVersion(Base):
    __tablename__ = "t_agent_prompt_rule_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "public.t_agent_prompt_rule.id",
            name="fk_agent_prompt_version_rule",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    observation_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    observation_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    published_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("rule_id", "version", name="uq_agent_prompt_rule_version"),
        CheckConstraint(
            "status IN ('draft','published','archived')",
            name="ck_agent_prompt_rule_version_status",
        ),
        Index("idx_agent_prompt_version_rule_status", "rule_id", "status"),
        {"schema": "public"},
    )
