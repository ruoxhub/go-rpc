export const CURRENT_PROTOCOL_VERSION = 1;
export const INVOCATION_CONTEXT_CAPABILITY = "invocation_context.v1";
export const MAX_MESSAGE_BYTES = 10 * 1024 * 1024;

export interface InvocationContext {
  sequence: string;
  trace_id: string;
  group: string;
  action: string;
  client_id: string;
  deadline_unix_ms: number;
  idempotent: boolean;
  idempotency_key: string;
  attempt: number;
}

export type RpcHandler = (request: Record<string, unknown>) => unknown | Promise<unknown>;
export type ContextRpcHandler = (
  context: InvocationContext,
  request: Record<string, unknown>,
  signal: AbortSignal,
) => unknown | Promise<unknown>;

export interface WebSocketAuth {
  headers?: Record<string, string>;
  protocols?: string[];
}

export interface WebSocketLike {
  readonly readyState: number;
  onopen: ((event?: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event?: unknown) => void) | null;
  onerror: ((event?: unknown) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string, auth: WebSocketAuth) => WebSocketLike;
