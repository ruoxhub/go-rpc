from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Generic, TypeVar

import httpx
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ValidationError

OutputT = TypeVar("OutputT", bound=BaseModel)


class StructuredOutputError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class StructuredOutputResult(Generic[OutputT]):
    value: OutputT
    attempts: int
    duration_ms: int


def _retryable(error: Exception) -> bool:
    return isinstance(
        error,
        (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError),
    ) or (
        isinstance(error, httpx.HTTPStatusError)
        and isinstance(getattr(error, "response", None), httpx.Response)
        and error.response.status_code == 429
    )


async def invoke_structured(
    *,
    model: Any,
    schema: type[OutputT],
    messages: Sequence[Any],
    on_attempt: Callable[[int], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
    max_validation_attempts: int = 2,
) -> StructuredOutputResult[OutputT]:
    started = perf_counter()
    try:
        try:
            runnable = model.with_structured_output(schema, method="function_calling")
        except TypeError:
            runnable = model.with_structured_output(schema)
    except asyncio.CancelledError:
        raise
    except Exception:
        raise StructuredOutputError(
            "structured_output_binding_failed",
            "model structured output binding failed",
        ) from None

    repair = HumanMessage(
        content=(
            "The previous response did not satisfy the required schema. Return one "
            "complete object matching the schema without quoting input sample values."
        )
    )
    for attempt in (1, 2):
        if check_cancelled is not None:
            check_cancelled()
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            response = await runnable.ainvoke(
                messages if attempt == 1 else [*messages, repair]
            )
            value = response if isinstance(response, schema) else schema.model_validate(response)
            return StructuredOutputResult(
                value=value,
                attempts=attempt,
                duration_ms=max(0, round((perf_counter() - started) * 1000)),
            )
        except asyncio.CancelledError:
            raise
        except ValidationError:
            if attempt < max_validation_attempts:
                continue
            exc = StructuredOutputError(
                "structured_output_invalid",
                "model structured output validation failed",
            )
            exc.__cause__ = None
            exc.__context__ = None
            raise exc from None
        except Exception as error:
            if attempt == 1 and _retryable(error):
                await asyncio.sleep(0.05)
                continue
            exc = StructuredOutputError(
                "model_request_failed", "model request failed"
            )
            exc.__cause__ = None
            exc.__context__ = None
            raise exc from None
    raise AssertionError("unreachable")


__all__ = ["StructuredOutputError", "StructuredOutputResult", "invoke_structured"]
