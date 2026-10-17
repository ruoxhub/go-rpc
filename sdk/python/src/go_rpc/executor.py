import asyncio
import inspect
import json
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tornado.httpclient import HTTPRequest
from tornado.ioloop import PeriodicCallback
from tornado.websocket import websocket_connect

from .protocol import INVOCATION_CONTEXT_CAPABILITY, MAX_MESSAGE_BYTES, PROTOCOL_VERSION, InvocationContext


PlainHandler = Callable[[dict], Any]
ContextHandler = Callable[[InvocationContext, dict, asyncio.Event], Any]


class ExecutorClient:
    def __init__(self, url: str, group: str, client_id: str, token: Optional[str] = None, confirmation_timeout: float = 5.0, executor_type: str = "python"):
        self.url = url
        self.group = group
        self.client_id = client_id
        self.token = token
        self.confirmation_timeout = confirmation_timeout
        self.executor_type = executor_type
        self._handlers: Dict[str, tuple[Callable[..., Any], bool]] = {}
        self._socket = None
        self._reader_task: Optional[asyncio.Task] = None
        self._active_tasks: set[asyncio.Task] = set()
        self._cancel_events: set[asyncio.Event] = set()
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._heartbeat: Optional[PeriodicCallback] = None
        self._started = False
        self._destroyed = False

    def register(self, action: str, handler: PlainHandler) -> None:
        if not action or not callable(handler):
            raise ValueError("action and handler are required")
        self._handlers[action] = (handler, False)

    def register_context(self, action: str, handler: ContextHandler) -> None:
        if not action or not callable(handler):
            raise ValueError("action and handler are required")
        self._handlers[action] = (handler, True)

    async def start(self) -> None:
        async with self._start_lock:
            if self._destroyed:
                raise RuntimeError("executor is destroyed")
            if self._started:
                return
            headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
            socket = None
            try:
                socket = await websocket_connect(HTTPRequest(self._registration_url(), headers=headers), max_message_size=MAX_MESSAGE_BYTES + 1)
                if self._destroyed:
                    raise RuntimeError("executor is destroyed")
                self._socket = socket
                try:
                    first = await asyncio.wait_for(socket.read_message(), self.confirmation_timeout)
                except asyncio.TimeoutError as exc:
                    raise RuntimeError("registered confirmation timeout") from exc
                if self._destroyed or self._socket is not socket:
                    raise RuntimeError("executor was closed during registration")
                if not isinstance(first, str):
                    raise RuntimeError("registered confirmation must be text")
                confirmation = json.loads(first)
                if not isinstance(confirmation, dict) or confirmation.get("type") != "registered":
                    raise RuntimeError("registered confirmation was not received")
                capabilities = confirmation.get("capabilities")
                if confirmation.get("protocol_version") != PROTOCOL_VERSION or not isinstance(capabilities, list) or INVOCATION_CONTEXT_CAPABILITY not in capabilities:
                    raise RuntimeError("registered confirmation is invalid")
                bind_msg = {"type": "bind", "actions": sorted(self._handlers)}
                if self.executor_type:
                    bind_msg["executor_type"] = self.executor_type
                await self._send(socket, bind_msg)
                if self._destroyed or self._socket is not socket:
                    raise RuntimeError("executor was closed during registration")
                self._started = True
                self._reader_task = asyncio.create_task(self._read_loop(socket))
                self._heartbeat = PeriodicCallback(self._heartbeat_once, 25_000)
                self._heartbeat.start()
            except BaseException:
                if socket is not None:
                    socket.close()
                if self._socket is socket:
                    self._socket = None
                self._started = False
                raise

    async def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._stop_heartbeat()
        for event in self._cancel_events:
            event.set()
        current = asyncio.current_task()
        tasks = [task for task in self._active_tasks if task is not current]
        for task in tasks:
            task.cancel()
        socket = self._socket
        self._socket = None
        if socket is not None:
            socket.close()
        reader = self._reader_task
        self._reader_task = None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._started = False

    def _stop_heartbeat(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.stop()
            self._heartbeat = None

    @property
    def connected(self) -> bool:
        """注册成功且连接仍存活。连接断开（含远端关闭）后转 False，可再次 start()。"""
        return self._started and self._socket is not None

    def _registration_url(self) -> str:
        parts = urlsplit(self.url)
        query = list(parse_qsl(parts.query, keep_blank_values=True))
        query.extend([
            ("protocol_version", str(PROTOCOL_VERSION)),
            ("capabilities", INVOCATION_CONTEXT_CAPABILITY),
            ("group", self.group),
            ("clientId", self.client_id),
            ("executor_type", self.executor_type),
        ])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    async def _heartbeat_once(self) -> None:
        socket = self._socket
        if socket is None or not self._started:
            return
        try:
            await self._send(socket, {"type": "heartbeat", "group": self.group, "clientId": self.client_id})
        except Exception:
            return

    async def _read_loop(self, socket) -> None:
        try:
            while not self._destroyed and self._socket is socket:
                raw = await socket.read_message()
                if raw is None:
                    return
                if isinstance(raw, bytes):
                    if len(raw) > MAX_MESSAGE_BYTES:
                        socket.close(code=1009, reason="message too large")
                        return
                elif isinstance(raw, str):
                    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                        socket.close(code=1009, reason="message too large")
                        return
                else:
                    continue
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(message, dict) or message.get("type") in ("heartbeat", "error"):
                    continue
                if message.get("type") == "invoke":
                    task = asyncio.create_task(self._dispatch(socket, message))
                    self._active_tasks.add(task)
                    task.add_done_callback(self._active_tasks.discard)
        finally:
            if self._socket is socket:
                self._stop_heartbeat()
                socket.close()
                self._socket = None
                self._started = False
                if self._reader_task is asyncio.current_task():
                    self._reader_task = None
                if not self._destroyed:
                    for event in self._cancel_events:
                        event.set()
                    current = asyncio.current_task()
                    for task in list(self._active_tasks):
                        if task is not current:
                            task.cancel()

    async def _dispatch(self, socket, message: dict) -> None:
        sequence = message.get("__sekiro_seq__") if isinstance(message.get("__sekiro_seq__"), str) else message.get("sequence", "")
        if not isinstance(sequence, str):
            sequence = ""
        trace_id = message.get("trace_id") if isinstance(message.get("trace_id"), str) else ""
        group = message.get("group") if isinstance(message.get("group"), str) else self.group
        client_id = message.get("clientId") if isinstance(message.get("clientId"), str) else self.client_id
        result = None
        error = None
        event = asyncio.Event()
        try:
            context = InvocationContext.from_message(message)
            entry = self._handlers.get(message.get("action"))
            if entry is None:
                raise RuntimeError(f"no handler registered for action {message.get('action')}")
            self._cancel_events.add(event)
            deadline = context.deadline_unix_ms
            if deadline > 0:
                import time
                delay = max(0.0, (deadline - int(time.time() * 1000)) / 1000)
                deadline_handle = asyncio.get_running_loop().call_later(delay, event.set)
            else:
                deadline_handle = None
            handler, is_context = entry
            try:
                value = handler(context, message, event) if is_context else handler(message)
                result = await value if inspect.isawaitable(value) else value
            finally:
                if deadline_handle is not None:
                    deadline_handle.cancel()
        except asyncio.CancelledError:
            return
        except Exception as caught:
            error = str(caught)
        finally:
            self._cancel_events.discard(event)
        response = {
            "type": "invoke_response",
            "__sekiro_seq__": sequence,
            "group": group,
            "clientId": client_id,
            "trace_id": trace_id,
            "status": -1 if error is not None else 0,
        }
        response["error" if error is not None else "data"] = error if error is not None else result
        try:
            await self._send(socket, response)
        except Exception:
            return

    async def _send(self, socket, message: dict) -> None:
        async with self._write_lock:
            if self._destroyed or self._socket is not socket:
                raise RuntimeError("socket is no longer active")
            socket.write_message(json.dumps(message))
