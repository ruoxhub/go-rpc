from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from llm.structured_output import StructuredOutputError, invoke_structured


class Output(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_structured_output_retries_once_after_validation_error():
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(side_effect=[{"value": "bad"}, Output(value=2)])
    model = MagicMock()
    model.with_structured_output.return_value = runnable

    result = await invoke_structured(model=model, schema=Output, messages=[])

    assert result.value == Output(value=2)
    assert result.attempts == 2
    repair_messages = runnable.ainvoke.await_args_list[1].args[0]
    assert "bad" not in str(repair_messages)


@pytest.mark.asyncio
async def test_structured_output_never_returns_provider_body_in_error():
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(side_effect=RuntimeError("Bearer provider-secret"))
    model = MagicMock()
    model.with_structured_output.return_value = runnable

    with pytest.raises(StructuredOutputError) as caught:
        await invoke_structured(model=model, schema=Output, messages=[])

    assert caught.value.code == "model_request_failed"
    assert "provider-secret" not in str(caught.value)
    assert "provider-secret" not in repr(caught.value)


@pytest.mark.asyncio
async def test_structured_output_prefers_function_calling_and_supports_legacy_model():
    runnable = MagicMock(ainvoke=AsyncMock(return_value={"value": 1}))
    model = MagicMock()
    model.with_structured_output.side_effect = [TypeError("legacy"), runnable]

    result = await invoke_structured(model=model, schema=Output, messages=[])

    assert result.value == Output(value=1)
    assert model.with_structured_output.call_args_list == [
        ((Output,), {"method": "function_calling"}),
        ((Output,), {}),
    ]


@pytest.mark.asyncio
async def test_structured_output_retries_only_one_retryable_request_failure():
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(
        side_effect=[TimeoutError("provider-secret"), {"value": 3}]
    )
    model = MagicMock()
    model.with_structured_output.return_value = runnable

    result = await invoke_structured(model=model, schema=Output, messages=[])

    assert result.value == Output(value=3)
    assert result.attempts == 2
