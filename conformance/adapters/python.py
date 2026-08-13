import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python" / "src"))

from go_rpc import AsyncRpcHTTPClient, ExecutorClient


async def main() -> None:
    base_url = os.environ.get("RPC_TEST_BASE_URL")
    if not base_url:
        raise RuntimeError("RPC_TEST_BASE_URL is required")
    fixture = json.loads(Path("conformance/fixtures/invoke-context-v1.json").read_text())
    if len(fixture.get("rpc_context_required_fields", [])) != 9:
        raise RuntimeError("invalid invoke context fixture")
    group, client_id = "conformance-python", "python-client"
    executor = ExecutorClient(base_url.replace("http://", "ws://") + "/business/register", group, client_id)
    received = {}

    async def handler(context, request, cancel_event):
        received.update(context.__dict__)
        return {
            "echo": request["params"]["echo"],
            "context_group": context.group,
            "context_client_id": context.client_id,
            "context_trace_id": context.trace_id,
            "context_sequence": context.sequence,
        }

    executor.register_context("conformance.echo", handler)
    caller = AsyncRpcHTTPClient(base_url, timeout=10)
    try:
        await executor.start()
        result = await caller.invoke(group, "conformance.echo", {"echo": "python"})
        if not isinstance(result, dict) or result.get("echo") != "python" or result.get("context_group") != group or result.get("context_client_id") != client_id or not isinstance(result.get("context_trace_id"), str) or not result.get("context_trace_id"):
            raise RuntimeError(f"unexpected HTTP result: {result!r}")
        if (not isinstance(received.get("sequence"), str) or not received["sequence"] or not isinstance(received.get("trace_id"), str) or not received["trace_id"] or received.get("group") != group or received.get("action") != "conformance.echo" or received.get("client_id") != client_id or not isinstance(received.get("deadline_unix_ms"), int) or received["deadline_unix_ms"] <= 0 or not isinstance(received.get("idempotent"), bool) or not isinstance(received.get("idempotency_key"), str) or received.get("attempt") != 1):
            raise RuntimeError(f"unexpected invocation context: {received!r}")
    finally:
        await caller.close()
        await executor.destroy()


if __name__ == "__main__":
    asyncio.run(main())
