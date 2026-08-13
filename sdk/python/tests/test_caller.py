import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from go_rpc.caller import AsyncRpcHTTPClient, RpcAPIError, RpcHTTPClient, RpcTransportError

HTTP_SERVER = None
HTTP_THREAD = None
BASE_URL = None


def setUpModule():
    global HTTP_SERVER, HTTP_THREAD, BASE_URL
    HTTP_SERVER = ThreadingHTTPServer(("127.0.0.1", 0), InvokeHTTPHandler)
    HTTP_THREAD = threading.Thread(target=HTTP_SERVER.serve_forever, daemon=True)
    HTTP_THREAD.start()
    BASE_URL = f"http://127.0.0.1:{HTTP_SERVER.server_port}"


def tearDownModule():
    HTTP_SERVER.shutdown()
    HTTP_THREAD.join()

class InvokeHTTPHandler(BaseHTTPRequestHandler):
    requests = []
    status = 200
    body = {"code": 0, "data": {"ok": True}}
    lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        with self.lock:
            self.requests.append((self.path, self.headers.get("Authorization"), payload))
        encoded = json.dumps(self.body).encode()
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


class CallerTests(unittest.TestCase):
    def setUp(self):
        InvokeHTTPHandler.requests.clear()
        InvokeHTTPHandler.status = 200
        InvokeHTTPHandler.body = {"code": 0, "data": {"ok": True}}

    def test_sync_invoke_sends_one_bearer_request_and_returns_data(self):
        client = RpcHTTPClient(BASE_URL, token="token", timeout=4)
        self.assertEqual(client.invoke("g", "echo", {"value": 1}, timeout=2), {"ok": True})
        self.assertEqual(len(InvokeHTTPHandler.requests), 1)
        path, auth, payload = InvokeHTTPHandler.requests[0]
        self.assertEqual(path, "/business/invoke")
        self.assertEqual(auth, "Bearer token")
        self.assertEqual(payload, {"group": "g", "action": "echo", "params": {"value": 1}, "timeout": 2})
        client.close()

    def test_flattened_success_and_negative_business_code(self):
        InvokeHTTPHandler.body = {"code": 0, "message": "ok", "group": "g", "clientId": "c", "trace_id": "t", "value": 3}
        with RpcHTTPClient(BASE_URL) as client:
            self.assertEqual(client.invoke("g", "echo", {}), {"value": 3})
        InvokeHTTPHandler.body = {"code": -4, "message": "failed"}
        with self.assertRaises(RpcAPIError):
            with RpcHTTPClient(BASE_URL) as client:
                client.invoke("g", "echo", {})

    def test_transport_error_does_not_retry(self):
        InvokeHTTPHandler.status = 500
        with self.assertRaises(RpcTransportError):
            with RpcHTTPClient(BASE_URL) as client:
                client.invoke("g", "echo", {})
        self.assertEqual(len(InvokeHTTPHandler.requests), 1)


class AsyncCallerTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_invoke_sends_once(self):
        InvokeHTTPHandler.requests.clear()
        InvokeHTTPHandler.body = {"code": 0, "data": {"async": True}}
        client = AsyncRpcHTTPClient(BASE_URL, token="async-token", timeout=4)
        self.assertEqual(await client.invoke("g", "echo", {}), {"async": True})
        self.assertEqual(len(InvokeHTTPHandler.requests), 1)
        self.assertEqual(InvokeHTTPHandler.requests[0][1], "Bearer async-token")
        await client.close()

    async def test_async_context_manager_closes_client(self):
        InvokeHTTPHandler.requests.clear()
        InvokeHTTPHandler.body = {"code": 0, "data": {"async": True}}
        async with AsyncRpcHTTPClient(BASE_URL) as client:
            self.assertEqual(await client.invoke("g", "echo", {}), {"async": True})
