from types import SimpleNamespace

import pytest

from core.task_model_validation import validate_explicit_task_model
from llm.model_factory import ModelUnavailableError
from models.task_config import TaskConfig, VideoAnalysisTaskConfig


class Catalog:
    def __init__(self, entry):
        self.entry = entry
        self.calls = []

    async def get_model(self, model_id):
        self.calls.append(model_id)
        return self.entry


def _entry(*, provider_enabled=True, model_enabled=True, remote_available=True):
    return (
        SimpleNamespace(enabled=model_enabled, remote_available=remote_available),
        SimpleNamespace(enabled=provider_enabled),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    [
        None,
        _entry(provider_enabled=False),
        _entry(model_enabled=False),
        _entry(remote_available=False),
    ],
)
async def test_rejects_missing_or_unusable_explicit_model(entry):
    catalog = Catalog(entry)
    config = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(llm_model_id=17),
    )

    with pytest.raises(ModelUnavailableError):
        await validate_explicit_task_model(catalog, config, explicit=True)

    assert catalog.calls == [17]


@pytest.mark.asyncio
async def test_accepts_usable_explicit_model():
    catalog = Catalog(_entry())
    config = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(llm_model_id=17),
    )

    await validate_explicit_task_model(catalog, config, explicit=True)

    assert catalog.calls == [17]


@pytest.mark.asyncio
async def test_does_not_revalidate_unchanged_historical_model():
    catalog = Catalog(None)
    config = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(llm_model_id=17),
    )

    await validate_explicit_task_model(catalog, config, explicit=False)

    assert catalog.calls == []


@pytest.mark.asyncio
async def test_explicit_clear_does_not_query_catalog():
    catalog = Catalog(None)
    config = TaskConfig(
        executor="video_analysis",
        analysis=VideoAnalysisTaskConfig(llm_model_id=None),
    )

    await validate_explicit_task_model(catalog, config, explicit=True)

    assert catalog.calls == []
