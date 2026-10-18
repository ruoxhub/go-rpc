"""Video analysis result model."""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VideoAnalysisRunStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VideoAnalysisRunOrigin(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    MIGRATED = "migrated"


class VideoAnalysisRun(Base):
    __tablename__ = "t_video_analysis_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    content_id: Mapped[str] = mapped_column(String(64), nullable=False)
    minio_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_object_name: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_task_run_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_rule_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "public.t_agent_prompt_rule_version.id",
            name="fk_video_analysis_prompt_rule_version",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    observation_prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_prompt_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evaluation_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    analysis_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("public.t_llm_model.id", name="fk_video_analysis_llm_model"),
        nullable=True,
    )
    model: Mapped[str] = mapped_column(String(500), nullable=False)
    started_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed')",
            name="ck_video_analysis_status",
        ),
        CheckConstraint(
            "origin IN ('manual','scheduled','migrated')",
            name="ck_video_analysis_origin",
        ),
        CheckConstraint(
            "status <> 'pending' OR (next_retry_at IS NOT NULL AND lease_token IS NULL "
            "AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="ck_video_analysis_pending_state",
        ),
        CheckConstraint(
            "status <> 'processing' OR (next_retry_at IS NULL AND lease_token IS NOT NULL "
            "AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_video_analysis_processing_state",
        ),
        CheckConstraint(
            "status NOT IN ('succeeded','failed') OR (next_retry_at IS NULL AND "
            "lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="ck_video_analysis_terminal_state",
        ),
        CheckConstraint(
            "origin = 'migrated' OR (prompt_rule_version_id IS NOT NULL AND "
            "observation_prompt_snapshot IS NOT NULL AND evaluation_prompt_snapshot IS NOT NULL "
            "AND observation_prompt_hash IS NOT NULL AND evaluation_prompt_hash IS NOT NULL "
            "AND execution_config_snapshot IS NOT NULL AND llm_model_id IS NOT NULL "
            "AND idempotency_key IS NOT NULL)",
            name="ck_video_analysis_native_snapshot",
        ),
        CheckConstraint(
            "origin <> 'scheduled' OR (source_task_id IS NOT NULL AND source_task_run_seq IS NOT NULL)",
            name="ck_video_analysis_scheduled_source",
        ),
        CheckConstraint(
            "origin <> 'migrated' OR status IN ('succeeded','failed')",
            name="ck_video_analysis_migrated_terminal",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts",
            name="ck_video_analysis_attempt_bounds",
        ),
        UniqueConstraint(
            "platform",
            "content_id",
            name="uq_video_analysis_platform_content",
        ),
        Index("idx_video_analysis_status_updated", "status", "updated_time"),
        Index("idx_video_analysis_llm_model_id", "llm_model_id"),
        Index("idx_video_analysis_prompt_rule_version", "prompt_rule_version_id"),
        {"schema": "public"},
    )


VideoAnalysisResult = VideoAnalysisRun
VideoAnalysisStatus = VideoAnalysisRunStatus
