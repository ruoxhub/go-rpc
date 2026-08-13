import asyncio
import json
from urllib.parse import parse_qs, urlparse
import unittest

import tornado.httpserver
import tornado.web
import tornado.websocket

from go_rpc.executor import ExecutorClient
from go_rpc.protocol import InvocationContext, MAX_MESSAGE_BYTES


class WebSocketState:
    def __init__(self, loop: asyncio.AbstractEventLoop, confirmation: bool = True):
        self.loop = loop
        self.confirmation = confirmation
        self.oversize = False
        self.action = "echo"
        self.query = {}
        self.authorization = None
        self.messages = []
        self.bind = loop.create_future()
        self.response = loop.create_future()
        self.closed = loop.create_future()
        self.invoke_started = loop.create_future()
        self.handler_calls = 0
        self.socket = None
        self.connections = 0
        self.handler_cancelled = loop.create_future()

    def finish(self, future, value=True):
        if not future.done():
            future.set_result(value)


class ContractSocket(tornado.websocket.WebSocketHandler):
    def initialize(self, state: WebSocketState):
        self.state = state

    def check_origin(self, origin):
        return True

    def open(self):
        self.state.socket = self
        self.state.connections += 1
        self.state.query = parse_qs(urlparse(self.request.uri).query)
        self.state.authorization = self.request.headers.get("Authorization")
        if self.state.confirmation == "legacy":
            self.write_message(json.dumps({"type": "registered"}))
        elif self.state.confirmation:
            self.write_message(json.dumps({
                "type": "registered",
                "protocol_version": 1,
                "capabilities": ["invocation_context.v1"],
            }))

    async def on_message(self, raw):
        message = json.loads(raw)
        self.state.messages.append(message)
        if message.get("type") == "bind":
            self.state.finish(self.state.bind, message)
            if self.state.oversize:
                try:
                    await self.write_message(b"{" + b"x" * MAX_MESSAGE_BYTES + b"}", binary=True)
                except tornado.websocket.WebSocketClosedError:
                    pass
                return
            if not self.state.response.done():
                self.state.finish(self.state.invoke_started)
                await self.write_message(json.dumps({
                    "type": "invoke",
                    "action": self.state.action,
                    "__sekiro_seq__": "seq-1",
                    "group": "group-a",
                    "clientId": "client-a",
                    "trace_id": "trace-1",
                    "value": 7,
                    "__rpc_context__": {
                        "sequence": "seq-1",
                        "trace_id": "trace-1",
                        "group": "group-a",
                        "action": self.state.action,
                        "client_id": "client-a",
                        "deadline_unix_ms": 4102444800000,
                        "idempotent": False,
                        "idempotency_key": "",
                        "attempt": 1,
                    },
                }))
        elif message.get("type") == "invoke_response":
            self.state.finish(self.state.response, message)
        elif message.get("type") == "heartbeat":
            self.state.messages.append(message)

    def on_close(self):
        self.state.finish(self.state.closed)


class ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = WebSocketState(asyncio.get_running_loop())
        self.application = tornado.web.Application([
            (r"/ws", ContractSocket, {"state": self.state}),
        ])
        self.server = tornado.httpserver.HTTPServer(self.application)
        self.server.listen(0, address="127.0.0.1")
        socket = next(iter(self.server._sockets.values()))
        self.url = f"ws://127.0.0.1:{socket.getsockname()[1]}/ws"

    async def asyncTearDown(self):
        self.server.stop()

    async def test_confirmed_start_binds_sorted_actions_and_dispatches_context(self):
        client = ExecutorClient(self.url, "group-a", "client-a", token="secret")
        seen = {}

        async def echo(context: InvocationContext, request: dict, cancel_event: asyncio.Event):
            seen["context"] = context
            seen["cancelled"] = cancel_event.is_set()
            return {"echo": request["value"]}

        client.register("zeta", lambda request: request)
        client.register_context("echo", echo)
        await client.start()
        bind = await asyncio.wait_for(self.state.bind, 1)
        response = await asyncio.wait_for(self.state.response, 1)

        self.assertEqual(self.state.query, {"protocol_version": ["1"], "capabilities": ["invocation_context.v1"], "group": ["group-a"], "clientId": ["client-a"]})
        self.assertEqual(self.state.authorization, "Bearer secret")
        self.assertEqual(bind, {"type": "bind", "actions": ["echo", "zeta"]})
        self.assertEqual(seen["context"].sequence, "seq-1")
        self.assertEqual(seen["context"].action, "echo")
        self.assertFalse(seen["cancelled"])
        self.assertEqual(response["status"], 0)
        self.assertEqual(response["__sekiro_seq__"], "seq-1")
        self.assertEqual(response["trace_id"], "trace-1")
        self.assertEqual(response["data"], {"echo": 7})
        await client.destroy()

    async def test_missing_confirmation_and_legacy_confirmation_are_rejected(self):
        for confirmation in (False, "legacy"):
            self.state.confirmation = confirmation
            client = ExecutorClient(self.url, "g", "c", confirmation_timeout=0.02)
            with self.assertRaisesRegex(RuntimeError, "registered confirmation"):
                await client.start()
            await client.destroy()

    async def test_invocation_context_rejects_missing_field(self):
        message = {
            "type": "invoke", "action": "echo", "__sekiro_seq__": "bad-seq",
            "group": "group-a", "clientId": "client-a", "trace_id": "bad-trace",
            "__rpc_context__": {
                "sequence": "bad-seq", "trace_id": "bad-trace", "group": "group-a",
                "action": "echo", "client_id": "client-a", "deadline_unix_ms": 0,
                "idempotent": False, "idempotency_key": "",
            },
        }
        self.state.response = self.state.loop.create_future()
        original = ContractSocket.on_message

        async def send_invalid(self, raw):
            parsed = json.loads(raw)
            if parsed.get("type") == "bind":
                self.state.finish(self.state.bind, parsed)
                await self.write_message(json.dumps(message))
            elif parsed.get("type") == "invoke_response":
                self.state.finish(self.state.response, parsed)

        ContractSocket.on_message = send_invalid
        try:
            calls = []
            client = ExecutorClient(self.url, "group-a", "client-a")
            client.register_context("echo", lambda *_: calls.append(True))
            await client.start()
            response = await asyncio.wait_for(self.state.response, 1)
            self.assertEqual(calls, [])
            self.assertEqual(response["status"], -1)
            self.assertEqual(response["__sekiro_seq__"], "bad-seq")
            self.assertEqual(response["trace_id"], "bad-trace")
            await client.destroy()
        finally:
            ContractSocket.on_message = original

    async def test_oversized_binary_frame_closes_with_1009(self):
        self.state.oversize = True
        client = ExecutorClient(self.url, "group-a", "client-a")
        await client.start()
        await asyncio.wait_for(self.state.closed, 2)
        await client.destroy()

    async def test_handler_exception_returns_one_error_response(self):
        self.state.action = "explode"
        client = ExecutorClient(self.url, "group-a", "client-a")
        client.register("explode", lambda _request: (_ for _ in ()).throw(RuntimeError("boom")))
        await client.start()
        response = await asyncio.wait_for(self.state.response, 1)
        self.assertEqual(response["status"], -1)
        self.assertEqual(len([m for m in self.state.messages if m.get("type") == "invoke_response"]), 1)
        await client.destroy()

    async def test_destroy_cancels_active_context_handler(self):
        self.state.action = "wait"
        started = asyncio.Event()
        cancelled = asyncio.Event()
        client = ExecutorClient(self.url, "group-a", "client-a")

        async def wait_handler(_context, _request, cancel_event):
            started.set()
            try:
                await cancel_event.wait()
            finally:
                if cancel_event.is_set():
                    cancelled.set()

        client.register_context("wait", wait_handler)
        await client.start()
        await asyncio.wait_for(started.wait(), 1)
        await client.destroy()
        await asyncio.wait_for(cancelled.wait(), 1)

    async def test_concurrent_start_dials_once_and_binds_once(self):
        client = ExecutorClient(self.url, "group-a", "client-a")
        await asyncio.gather(client.start(), client.start())
        await asyncio.wait_for(self.state.bind, 1)
        self.assertEqual(self.state.connections, 1)
        self.assertEqual(len([m for m in self.state.messages if m.get("type") == "bind"]), 1)
        await client.destroy()

    async def test_destroy_during_confirmation_cannot_make_start_succeed(self):
        self.state.confirmation = False
        client = ExecutorClient(self.url, "group-a", "client-a", confirmation_timeout=1)
        starting = asyncio.create_task(client.start())
        await asyncio.sleep(0.02)
        await client.destroy()
        with self.assertRaises(RuntimeError):
            await starting
        self.assertIsNone(client._socket)

    async def test_handler_can_await_destroy_without_self_wait(self):
        self.state.action = "self_destroy"
        client = ExecutorClient(self.url, "group-a", "client-a")
        done = asyncio.Event()

        async def self_destroy(_context, _request, _cancel_event):
            await client.destroy()
            done.set()
            return {"ok": True}

        client.register_context("self_destroy", self_destroy)
        await client.start()
        await asyncio.wait_for(done.wait(), 1)
        self.assertIsNone(client._socket)
        await client.destroy()

    async def test_remote_close_stops_heartbeat_cancels_handler_and_allows_restart(self):
        self.state.action = "wait"
        client = ExecutorClient(self.url, "group-a", "client-a")
        started = asyncio.Event()

        async def wait_handler(_context, _request, cancel_event):
            started.set()
            try:
                await cancel_event.wait()
            finally:
                if cancel_event.is_set():
                    self.state.finish(self.state.handler_cancelled)

        client.register_context("wait", wait_handler)
        await client.start()
        await asyncio.wait_for(started.wait(), 1)
        self.state.socket.close()
        await asyncio.wait_for(self.state.handler_cancelled, 1)
        for _ in range(20):
            if client._heartbeat is None and client._socket is None:
                break
            await asyncio.sleep(0)
        self.assertIsNone(client._heartbeat)
        self.assertIsNone(client._socket)
        await client.start()
        self.assertEqual(self.state.connections, 2)
        await client.destroy()

    def test_invocation_context_rejects_bool_and_string_integers(self):
        base = {
            "sequence": "seq", "trace_id": "trace", "group": "g", "action": "a",
            "client_id": "c", "deadline_unix_ms": 0, "idempotent": False,
            "idempotency_key": "", "attempt": 1,
        }
        for field, value in (("attempt", True), ("deadline_unix_ms", "0")):
            message = {"__rpc_context__": {**base, field: value}}
            with self.assertRaises(ValueError):
                InvocationContext.from_message(message)
