import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from go_rpc import (
    BlockedRpcError,
    InvalidRpcJsonError,
    PermanentRpcError,
    RateLimitedRpcError,
    RetryableRpcError,
    RpcClient,
    RpcResponseTooLargeError,
)
from runtime_config.models import RpcSettings


@pytest.fixture
def mock_response():
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"code": 0, "data": {"item": []}}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_invoke_sends_correct_payload(mock_response):
    client = RpcClient(base_url="http://rpc:5612", timeout=10)
    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        result = await client.invoke("bilibili", "getFeedRcmd", {"ps": 12})

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[1]["json"] == {
        "group": "bilibili",
        "action": "getFeedRcmd",
        "params": {"ps": 12},
    }
    assert result == {"code": 0, "data": {"item": []}}
    await client.close()


@pytest.mark.asyncio
async def test_invoke_includes_token_header():
    client = RpcClient(base_url="http://rpc:5612", token="my-token")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"code": 0}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_post:
        await client.invoke("bilibili", "getContent", {"content_id": "BV1"})

    headers = mock_post.call_args[1]["headers"]
    assert headers["sekiro-token"] == "my-token"
    await client.close()


@pytest.mark.asyncio
async def test_invoke_omits_token_when_empty():
    client = RpcClient(base_url="http://rpc:5612", token="")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.json.return_value = {"code": 0}
    mock_resp.raise_for_status = MagicMock()

    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=mock_resp
    ) as mock_post:
        await client.invoke("bilibili", "getContent", {})

    headers = mock_post.call_args[1]["headers"]
    assert "sekiro-token" not in headers
    await client.close()


@pytest.mark.parametrize(
    ("status_code", "error_type", "expected_calls"),
    [
        (400, PermanentRpcError, 1),
        (401, PermanentRpcError, 1),
        (403, BlockedRpcError, 1),
        (404, PermanentRpcError, 1),
        (410, PermanentRpcError, 1),
        (429, RateLimitedRpcError, 1),
        (500, RetryableRpcError, 3),
        (503, RetryableRpcError, 3),
    ],
)
@pytest.mark.asyncio
async def test_invoke_classifies_http_error(
    monkeypatch, status_code, error_type, expected_calls
):
    client = RpcClient(base_url="http://rpc:5612", max_retries=3)
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server Error",
        request=MagicMock(),
        response=mock_resp,
    )

    async def retry_sleep(_seconds):
        pass

    monkeypatch.setattr("go_rpc.caller.asyncio.sleep", retry_sleep)

    with (
        patch.object(
            client.client, "post", new_callable=AsyncMock, return_value=mock_resp
        ) as post,
        pytest.raises(error_type) as caught,
    ):
        await client.invoke("bilibili", "getContent", {})
    assert caught.value.status_code == status_code
    assert post.await_count == expected_calls
    await client.close()


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("connection failed"), asyncio.TimeoutError("timed out")],
)
@pytest.mark.asyncio
async def test_invoke_classifies_retryable_transport_errors(monkeypatch, failure):
    client = RpcClient(base_url="http://rpc:5612", max_retries=2)

    async def retry_sleep(_seconds):
        pass

    monkeypatch.setattr("go_rpc.caller.asyncio.sleep", retry_sleep)
    with patch.object(
        client.client, "post", new_callable=AsyncMock, side_effect=failure
    ) as post:
        with pytest.raises(RetryableRpcError) as caught:
            await client.invoke("bilibili", "getContent", {})

    assert caught.value.status_code is None
    assert post.await_count == 2
    await client.close()


@pytest.mark.asyncio
async def test_rate_limit_exposes_retry_after_without_retrying():
    client = RpcClient(base_url="http://rpc:5612", max_retries=3)
    response = MagicMock(spec=httpx.Response)
    response.status_code = 429
    response.headers = httpx.Headers({"Retry-After": "17"})
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limited", request=MagicMock(), response=response
    )

    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=response
    ) as post:
        with pytest.raises(RateLimitedRpcError) as caught:
            await client.invoke("bilibili", "getContent", {})

    assert caught.value.retry_after_seconds == 17
    assert post.await_count == 1
    await client.close()


@pytest.mark.asyncio
async def test_retry_budget_stops_retries_after_credits_are_exhausted(monkeypatch):
    client = RpcClient(base_url="http://rpc:5612", max_retries=3, retry_budget_ratio=0)
    failure = httpx.ConnectError("connection failed")

    async def retry_sleep(_seconds):
        pass

    monkeypatch.setattr("go_rpc.caller.asyncio.sleep", retry_sleep)
    with patch.object(
        client.client, "post", new_callable=AsyncMock, side_effect=failure
    ) as post:
        with pytest.raises(RetryableRpcError):
            await client.invoke("bilibili", "getContent", {})
        with pytest.raises(RetryableRpcError):
            await client.invoke("bilibili", "getContent", {})

    assert post.await_count == 4
    await client.close()


@pytest.mark.asyncio
async def test_retry_logs_use_redacted_structured_error(monkeypatch):
    client = RpcClient(base_url="http://rpc:5612", max_retries=2)
    fake_logger = MagicMock()

    async def retry_sleep(_seconds):
        pass

    monkeypatch.setattr("go_rpc.caller.asyncio.sleep", retry_sleep)
    monkeypatch.setattr("go_rpc.caller.logger", fake_logger)
    failure = httpx.ConnectError("token=secret password=pw network down")
    with patch.object(
        client.client, "post", new_callable=AsyncMock, side_effect=failure
    ):
        with pytest.raises(RetryableRpcError):
            await client.invoke("bilibili", "getContent", {})

    warning_text = " ".join(str(value) for value in fake_logger.warning.call_args.args)
    error_text = " ".join(str(value) for value in fake_logger.error.call_args.args)
    combined = warning_text + error_text
    assert "platform=%s" in combined
    assert "attempt=%d" in combined
    assert "outcome=%s" in combined
    assert "latency_ms=%d" in combined
    assert "network down" in combined
    assert "token=secret" not in combined
    assert "password=pw" not in combined
    await client.close()


@pytest.mark.asyncio
async def test_invoke_reads_dynamic_url_and_timeout_each_time(mock_response):
    store = MagicMock()
    store.get_rpc = AsyncMock(
        side_effect=[
            RpcSettings(base_url="https://one.test/prefix/", timeout_seconds=11),
            RpcSettings(base_url="https://two.test", timeout_seconds=22),
        ]
    )
    client = RpcClient(config_store=store)
    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=mock_response
    ) as post:
        await client.invoke("p", "a", {})
        await client.invoke("p", "a", {})

    assert [call.args[0] for call in post.await_args_list] == [
        "https://one.test/prefix/business/invoke",
        "https://two.test/business/invoke",
    ]
    assert [call.kwargs["timeout"].read for call in post.await_args_list] == [
        11.0,
        22.0,
    ]
    await client.close()


@pytest.mark.asyncio
async def test_in_flight_invoke_keeps_initial_settings(mock_response):
    store = MagicMock()
    store.get_rpc = AsyncMock(
        return_value=RpcSettings(base_url="https://initial.test", timeout_seconds=13)
    )
    client = RpcClient(config_store=store)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def post(url, **kwargs):
        calls.append((url, kwargs["timeout"].read))
        started.set()
        await release.wait()
        return mock_response

    with patch.object(client.client, "post", side_effect=post):
        invocation = asyncio.create_task(client.invoke("p", "a", {}))
        await started.wait()
        store.get_rpc.return_value = RpcSettings(
            base_url="https://updated.test", timeout_seconds=99
        )
        release.set()
        await invocation

    assert calls == [("https://initial.test/business/invoke", 13.0)]
    store.get_rpc.assert_awaited_once_with()
    await client.close()


@pytest.mark.asyncio
async def test_retry_chain_keeps_snapshot_and_next_invoke_refreshes(
    monkeypatch, mock_response
):
    initial = RpcSettings(base_url="https://initial.test/prefix", timeout_seconds=7)
    updated = RpcSettings(base_url="https://updated.test", timeout_seconds=17)
    store = MagicMock()
    store.get_rpc = AsyncMock(side_effect=[initial, updated])
    client = RpcClient(config_store=store, max_retries=2)
    failed_response = MagicMock(spec=httpx.Response)
    failed_response.status_code = 503
    failed_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unavailable", request=MagicMock(), response=failed_response
    )
    calls = []

    async def post(url, **kwargs):
        calls.append((url, kwargs["timeout"].read))
        return failed_response if len(calls) == 1 else mock_response

    async def retry_sleep(_seconds):
        pass

    monkeypatch.setattr("go_rpc.caller.asyncio.sleep", retry_sleep)
    with patch.object(client.client, "post", side_effect=post):
        await client.invoke("p", "a", {})
        await client.invoke("p", "a", {})

    assert calls == [
        ("https://initial.test/prefix/business/invoke", 7.0),
        ("https://initial.test/prefix/business/invoke", 7.0),
        ("https://updated.test/business/invoke", 17.0),
    ]
    assert store.get_rpc.await_count == 2
    await client.close()


class _ExplodingStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("response body must not be read")
        yield b""  # pragma: no cover


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


async def _invoke_bounded_json(payload, **limits):
    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    async def handler(request):
        return httpx.Response(200, content=content, request=request)

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        return await client.invoke(
            "demo",
            "detail",
            {},
            max_response_bytes=len(content),
            **limits,
        )
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_content_length_before_reading():
    async def handler(request):
        return httpx.Response(
            200,
            headers={"Content-Length": "1000"},
            stream=_ExplodingStream(),
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RpcResponseTooLargeError) as caught:
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    assert caught.value.category == "response_too_large"
    await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_stream_that_crosses_limit():
    async def handler(request):
        return httpx.Response(
            200,
            stream=_ChunkedStream(b'{"data":"', b"x" * 200, b'"}'),
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RpcResponseTooLargeError) as caught:
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    assert caught.value.category == "response_too_large"
    await client.close()


@pytest.mark.parametrize("payload", [{"data": [1]}, [1, {"ok": True}]])
@pytest.mark.asyncio
async def test_bounded_invoke_accepts_json_object_or_array(payload):
    content = httpx.Response(200, json=payload).content

    async def handler(request):
        return httpx.Response(200, content=content, request=request)

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert (
        await client.invoke("demo", "detail", {}, max_response_bytes=len(content))
        == payload
    )
    await client.close()


@pytest.mark.parametrize("content", [b"not-json", b"\xff"])
@pytest.mark.asyncio
async def test_bounded_invoke_rejects_invalid_json_without_retrying(content):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=content, request=request)

    client = RpcClient(base_url="http://rpc", max_retries=3)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(InvalidRpcJsonError) as caught:
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    assert caught.value.category == "invalid_json"
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_keeps_rate_limit_classification():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "17"},
            content=b"rate limited",
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=3)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimitedRpcError) as caught:
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    assert caught.value.retry_after_seconds == 17
    assert calls == 1
    await client.close()


@pytest.mark.asyncio
async def test_unbounded_invoke_keeps_post_json_path(mock_response):
    client = RpcClient(base_url="http://rpc", max_retries=1)
    with (
        patch.object(
            client.client,
            "post",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as post,
        patch.object(
            client.client,
            "stream",
            side_effect=AssertionError("unbounded invoke must not stream"),
        ),
    ):
        result = await client.invoke("demo", "detail", {})

    assert result == {"code": 0, "data": {"item": []}}
    assert post.await_count == 1
    await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_accepts_json_at_structure_limits():
    payload = {"items": ["éé", {"child": None}]}

    result = await _invoke_bounded_json(
        payload,
        json_max_depth=3,
        json_max_nodes=5,
        max_array_items=2,
        max_string_bytes=5,
    )

    assert result == payload


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_depth_max_plus_one():
    payload = {}
    current = payload
    for _ in range(65):
        child = {}
        current["child"] = child
        current = child

    with pytest.raises(InvalidRpcJsonError) as caught:
        await _invoke_bounded_json(payload)

    assert caught.value.category == "invalid_json"


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_node_max_plus_one():
    with pytest.raises(InvalidRpcJsonError):
        await _invoke_bounded_json(
            {"a": 1, "b": [2, 3]},
            json_max_nodes=4,
        )


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_array_items_max_plus_one():
    with pytest.raises(InvalidRpcJsonError):
        await _invoke_bounded_json(
            {"items": [1, 2, 3]},
            max_array_items=2,
        )


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_string_bytes_max_plus_one():
    with pytest.raises(InvalidRpcJsonError):
        await _invoke_bounded_json(
            {"text": "ééé"},
            max_string_bytes=5,
        )


@pytest.mark.parametrize("payload", [1, "value", True, None])
@pytest.mark.asyncio
async def test_bounded_invoke_rejects_scalar_top_level(payload):
    with pytest.raises(InvalidRpcJsonError):
        await _invoke_bounded_json(payload)


@pytest.mark.parametrize(
    "content_length",
    ["invalid", "-1"],
)
@pytest.mark.asyncio
async def test_bounded_invoke_rejects_invalid_content_length(content_length):
    async def handler(request):
        return httpx.Response(
            200,
            headers={"Content-Length": content_length},
            stream=_ExplodingStream(),
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RpcResponseTooLargeError):
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_rejects_conflicting_content_length():
    async def handler(request):
        return httpx.Response(
            200,
            headers=[("Content-Length", "2"), ("Content-Length", "3")],
            stream=_ExplodingStream(),
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(RpcResponseTooLargeError):
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    await client.close()


@pytest.mark.asyncio
async def test_bounded_invoke_requests_and_requires_identity_encoding():
    observed_accept_encoding = None

    async def identity_handler(request):
        nonlocal observed_accept_encoding
        observed_accept_encoding = request.headers.get("Accept-Encoding")
        return httpx.Response(200, content=b"{}", request=request)

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(identity_handler))
    assert await client.invoke("demo", "detail", {}, max_response_bytes=2) == {}
    await client.close()
    assert observed_accept_encoding == "identity"

    async def gzip_handler(request):
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            stream=_ExplodingStream(),
            request=request,
        )

    client = RpcClient(base_url="http://rpc", max_retries=1)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(gzip_handler))
    with pytest.raises(RpcResponseTooLargeError):
        await client.invoke("demo", "detail", {}, max_response_bytes=100)
    await client.close()
