"""Validation for explicit task-level LLM model overrides."""
from __future__ import annotations

from typing import Protocol

from llm.model_factory import validate_catalog_entry
from models.llm_provider import LlmModel, LlmProvider
from models.task_config import TaskConfig


class ModelCatalog(Protocol):
    async def get_model(
        self,
        model_id: int,
    ) -> tuple[LlmModel, LlmProvider] | None: ...


async def validate_explicit_task_model(
    catalog: ModelCatalog,
    config: TaskConfig,
    *,
    explicit: bool,
) -> None:
    """Validate only a newly supplied non-null video-analysis override."""
    if not explicit or config.executor != "video_analysis":
        return
    model_id = config.analysis.llm_model_id if config.analysis else None
    if model_id is None:
        return
    validate_catalog_entry(await catalog.get_model(model_id))
