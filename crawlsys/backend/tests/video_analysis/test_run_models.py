from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

import models
from models.analysis import (
    VideoAnalysisResult,
    VideoAnalysisRun,
    VideoAnalysisRunOrigin,
    VideoAnalysisRunStatus,
    VideoAnalysisStatus,
)
from models.prompt_rule import AgentPromptRule, AgentPromptRuleVersion


def _constraint_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_prompt_rule_tables_keep_versions_immutable_and_restricted():
    rule = AgentPromptRule.__table__
    version = AgentPromptRuleVersion.__table__

    assert (rule.schema, rule.name) == ("public", "t_agent_prompt_rule")
    assert (version.schema, version.name) == (
        "public",
        "t_agent_prompt_rule_version",
    )
    assert rule.c.active_published_version_id.nullable
    assert isinstance(version.c.observation_prompt.type, type(version.c.evaluation_prompt.type))
    assert version.c.published_time.nullable

    unique_names = {
        constraint.name
        for constraint in version.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_agent_prompt_rule_version" in unique_names

    foreign_keys = {
        constraint.name: constraint
        for table in (rule, version)
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert foreign_keys["fk_agent_prompt_rule_active_version"].ondelete == "RESTRICT"
    assert foreign_keys["fk_agent_prompt_version_rule"].ondelete == "RESTRICT"


def test_video_analysis_run_has_snapshot_queue_and_source_fields():
    table = VideoAnalysisRun.__table__
    expected = {
        "origin",
        "source_task_id",
        "source_task_run_seq",
        "prompt_rule_version_id",
        "observation_prompt_snapshot",
        "evaluation_prompt_snapshot",
        "observation_prompt_hash",
        "evaluation_prompt_hash",
        "execution_config_snapshot",
        "idempotency_key",
        "max_attempts",
        "next_retry_at",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "error_code",
    }

    assert expected.issubset(table.c.keys())
    assert isinstance(table.c.execution_config_snapshot.type, JSONB)
    assert table.c.started_time.nullable
    assert not table.c.origin.nullable
    assert not table.c.status.nullable
    assert not table.c.max_attempts.nullable
    assert table.c.next_retry_at.nullable
    assert table.c.prompt_rule_version_id.foreign_keys.pop().ondelete == "RESTRICT"


def test_video_analysis_run_names_all_state_and_snapshot_constraints():
    table = VideoAnalysisRun.__table__
    assert _constraint_names(table) == {
        "ck_video_analysis_status",
        "ck_video_analysis_origin",
        "ck_video_analysis_pending_state",
        "ck_video_analysis_processing_state",
        "ck_video_analysis_terminal_state",
        "ck_video_analysis_native_snapshot",
        "ck_video_analysis_scheduled_source",
        "ck_video_analysis_migrated_terminal",
        "ck_video_analysis_attempt_bounds",
    }
    unique_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_video_analysis_platform_content" in unique_names


def test_video_analysis_enums_and_compatibility_aliases():
    assert {item.value for item in VideoAnalysisRunStatus} == {
        "pending",
        "processing",
        "succeeded",
        "failed",
    }
    assert {item.value for item in VideoAnalysisRunOrigin} == {
        "manual",
        "scheduled",
        "migrated",
    }
    assert VideoAnalysisResult is VideoAnalysisRun
    assert VideoAnalysisStatus is VideoAnalysisRunStatus
    assert models.VideoAnalysisRun is VideoAnalysisRun
    assert models.VideoAnalysisRunOrigin is VideoAnalysisRunOrigin
    assert models.VideoAnalysisRunStatus is VideoAnalysisRunStatus
