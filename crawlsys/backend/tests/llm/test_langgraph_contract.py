"""LangChain LiteLLM 与 LangGraph 的最小运行时契约。"""

from __future__ import annotations

import socket
from typing import TypedDict
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import requests
from langgraph.graph import END, START, StateGraph

from models.results import AnalysisResult

with patch("tiktoken.get_encoding", return_value=object()):
    from langchain_litellm import ChatLiteLLM


class GraphState(TypedDict):
    visited: bool


@pytest.fixture(autouse=True)
def reject_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("contract tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(httpx.AsyncClient, "send", fail)
    monkeypatch.setattr(requests.Session, "send", fail)


@pytest.mark.asyncio
async def test_chat_litellm_supports_async_and_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ChatLiteLLM(
        model="openai/test-model",
        api_key="test-key",
        max_retries=0,
    )
    completion = AsyncMock(
        side_effect=[
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "plain response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"content_classification":'
                                '{"primary_type":"FUNCTIONAL_PROOF","topology":"ONE_TAKE"},'
                                '"decision":{"gate_status":"INSUFFICIENT_EVIDENCE",'
                                '"scoring_status":"UNAVAILABLE",'
                                '"system_disposition":"OWNER_REVIEW_REQUIRED"}}'
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        ]
    )
    monkeypatch.setattr(model.client, "acompletion", completion)

    message = await model.ainvoke("Return a plain response")
    result = await model.with_structured_output(AnalysisResult).ainvoke(
        "Return structured analysis"
    )

    assert message.content == "plain response"
    assert isinstance(result, AnalysisResult)
    assert result.content_classification.primary_type.value == "FUNCTIONAL_PROOF"
    assert completion.await_count == 2
    assert (
        completion.await_args_list[1].kwargs["response_format"]["type"]
        == "json_schema"
    )


@pytest.mark.asyncio
async def test_state_graph_compiles_without_checkpointer() -> None:
    async def visit(state: GraphState) -> GraphState:
        return {**state, "visited": True}

    graph = StateGraph(GraphState)
    graph.add_node("visit", visit)
    graph.add_edge(START, "visit")
    graph.add_edge("visit", END)

    compiled = graph.compile()

    assert callable(compiled.ainvoke)
    assert await compiled.ainvoke({"visited": False}) == {"visited": True}
