import { readFile } from "node:fs/promises";
import { RpcClient, nodeWebSocketFactory } from "../../sdk/typescript/dist/src/node.js";

const baseURL = process.env.RPC_TEST_BASE_URL;
if (!baseURL) fail("RPC_TEST_BASE_URL is required");
const fixture = JSON.parse(await readFile("conformance/fixtures/invoke-context-v1.json", "utf8"));
if (fixture.rpc_context_required_fields?.length !== 9) fail("invalid invoke context fixture");

const group = "conformance-typescript";
const clientId = "typescript-client";
const client = new RpcClient({
  url: `${baseURL.replace(/^http/, "ws")}/business/register`,
  group,
  clientId,
  websocketFactory: nodeWebSocketFactory,
});
let received;
client.registerActionContext("conformance.echo", async (context, request) => {
  received = context;
  return {
    echo: request.params.echo,
    group: context.group,
    clientId: context.client_id,
    trace_id: context.trace_id,
    sequence: context.sequence,
  };
});
try {
  await client.start();
  const response = await fetch(`${baseURL}/business/invoke`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ group, action: "conformance.echo", params: { echo: "typescript" } }),
  });
  if (!response.ok) fail(`HTTP status ${response.status}`);
  const payload = await response.json();
  const data = payload.data ?? payload;
  const validContext = received && typeof received.sequence === "string" && received.sequence.length > 0 && typeof received.trace_id === "string" && received.trace_id.length > 0 && received.group === group && received.action === "conformance.echo" && received.client_id === clientId && Number.isInteger(received.deadline_unix_ms) && received.deadline_unix_ms > 0 && typeof received.idempotent === "boolean" && typeof received.idempotency_key === "string" && Number.isInteger(received.attempt) && received.attempt === 1;
  if (payload.group !== group || payload.clientId !== clientId || typeof payload.trace_id !== "string" || payload.trace_id.length === 0 || data.echo !== "typescript" || data.group !== group || data.clientId !== clientId || !validContext || payload.trace_id !== received.trace_id || received.idempotent !== false || received.idempotency_key !== "") {
    fail(`conformance mismatch: ${JSON.stringify({ payload, received })}`);
  }
} finally {
  client.destroy();
}

function fail(message) {
  console.error(message);
  process.exitCode = 1;
  throw new Error(message);
}
