import assert from "node:assert/strict";
import test from "node:test";
import { RpcClient } from "../src/client.js";
import type { InvocationContext, WebSocketFactory, WebSocketLike } from "../src/protocol.js";

class FakeWebSocket implements WebSocketLike {
  static instances: FakeWebSocket[] = [];
  readonly url: string;
  readonly auth: { headers?: Record<string, string>; protocols?: string[] };
  readyState = 0;
  sent: string[] = [];
  closeCode?: number;
  onopen: ((event?: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: ((event?: unknown) => void) | null = null;
  onerror: ((event?: unknown) => void) | null = null;

  constructor(url: string, auth: { headers?: Record<string, string>; protocols?: string[] }) {
    this.url = url;
    this.auth = auth;
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code?: number): void {
    this.closeCode = code;
    this.readyState = 3;
    this.onclose?.({ code });
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  message(value: unknown): void {
    this.onmessage?.({ data: typeof value === "string" ? value : JSON.stringify(value) });
  }
}

const factory: WebSocketFactory = (url, auth) => new FakeWebSocket(url, auth);

function latestSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1);
  assert.ok(socket);
  return socket;
}

test("start confirms before sorted bind and invokes context handler once", async () => {
  FakeWebSocket.instances.length = 0;
  const seen: { context?: InvocationContext; request?: Record<string, unknown>; signal?: AbortSignal } = {};
  const client = new RpcClient({ url: "wss://example.test/register", group: "g space", clientId: "c/client", token: "tok", websocketFactory: factory });
  client.registerAction("zeta", () => ({ z: 1 }));
  client.registerActionContext("echo", (context, request, signal) => {
    seen.context = context;
    seen.request = request;
    seen.signal = signal;
    return { echo: 1 };
  });
  const started = client.start();
  const socket = latestSocket();
  const query = new URL(socket.url).searchParams;
  assert.equal(query.get("protocol_version"), "1");
  assert.equal(query.get("capabilities"), "invocation_context.v1");
  assert.equal(query.get("group"), "g space");
  assert.equal(query.get("clientId"), "c/client");
  assert.equal(query.get("token"), null);
  assert.deepEqual(socket.auth.headers, { Authorization: "Bearer tok" });
  assert.deepEqual(socket.auth.protocols, ["sekiro-auth.tok"]);
  socket.open();
  assert.deepEqual(socket.sent, []);
  const registration = { type: "registered", protocol_version: 1, capabilities: ["invocation_context.v1"] };
  socket.message(registration);
  await started;
  assert.deepEqual(JSON.parse(socket.sent[0]!), { type: "bind", actions: ["echo", "zeta"] });

  socket.message({
    type: "invoke", action: "echo", __sekiro_seq__: "seq-1", group: "g space", clientId: "c/client", trace_id: "trace-1",
    params: { value: 1 },
    __rpc_context__: { sequence: "seq-1", trace_id: "trace-1", group: "g space", action: "echo", client_id: "c/client", deadline_unix_ms: Date.now() + 10000, idempotent: false, idempotency_key: "", attempt: 1 },
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(seen.context?.sequence, "seq-1");
  assert.equal(seen.context?.action, "echo");
  assert.equal(seen.request?.action, "echo");
  assert.equal(seen.signal?.aborted, false);
  assert.deepEqual(JSON.parse(socket.sent[1]!), { type: "invoke_response", __sekiro_seq__: "seq-1", group: "g space", clientId: "c/client", trace_id: "trace-1", status: 0, data: { echo: 1 } });
  client.destroy();
  assert.equal(socket.readyState, 3);
});

test("missing registered confirmation rejects using injectable timeout", async () => {
  FakeWebSocket.instances.length = 0;
  const client = new RpcClient({ url: "ws://example.test/register", group: "g", clientId: "c", websocketFactory: factory, confirmationTimeoutMs: 5 });
  const started = client.start();
  const socket = latestSocket();
  socket.open();
  await assert.rejects(started, /registered confirmation/);
  assert.equal(socket.readyState, 3);
});

test("destroy aborts an active context handler and does not reconnect", async () => {
  FakeWebSocket.instances.length = 0;
  let signal: AbortSignal | undefined;
  let aborted: (() => void) | undefined;
  const abortObserved = new Promise<void>((resolve) => { aborted = resolve; });
  const client = new RpcClient({ url: "ws://example.test/register", group: "g", clientId: "c", websocketFactory: factory });
  client.registerActionContext("wait", (_context, _request, handlerSignal) => {
    signal = handlerSignal;
    return new Promise((resolve) => {
      handlerSignal.addEventListener("abort", () => { aborted?.(); resolve({ done: true }); }, { once: true });
    });
  });
  const started = client.start();
  const socket = latestSocket();
  socket.open();
  socket.message({ type: "registered", protocol_version: 1, capabilities: ["invocation_context.v1"] });
  await started;
  socket.message({ type: "invoke", action: "wait", __sekiro_seq__: "seq-wait", group: "g", clientId: "c", __rpc_context__: { sequence: "seq-wait", action: "wait", group: "g", client_id: "c", deadline_unix_ms: 0, idempotent: false, idempotency_key: "", attempt: 1 } });
  for (let i = 0; i < 20 && !signal; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  client.destroy();
  await abortObserved;
  assert.equal(signal?.aborted, true);
  assert.equal(socket.closeCode, 1000);
  assert.equal(FakeWebSocket.instances.length, 1);
});

test("oversized UTF-8 text closes with 1009 before JSON parsing", async () => {
  FakeWebSocket.instances.length = 0;
  const client = new RpcClient({ url: "ws://example.test/register", group: "g", clientId: "c", websocketFactory: factory });
  const started = client.start();
  const socket = latestSocket();
  socket.open();
  socket.message({ type: "registered", protocol_version: 1, capabilities: ["invocation_context.v1"] });
  await started;
  socket.message("😀".repeat(Math.ceil((10 * 1024 * 1024) / 4) + 1));
  assert.equal(socket.closeCode, 1009);
  client.destroy();
});
