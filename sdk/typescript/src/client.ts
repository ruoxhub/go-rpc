import {
  CURRENT_PROTOCOL_VERSION,
  INVOCATION_CONTEXT_CAPABILITY,
  MAX_MESSAGE_BYTES,
} from "./protocol.js";
import type {
  ContextRpcHandler,
  InvocationContext,
  RpcHandler,
  WebSocketFactory,
  WebSocketLike,
} from "./protocol.js";

export type { ContextRpcHandler, InvocationContext, RpcHandler } from "./protocol.js";

export interface RpcClientOptions {
  url: string;
  group: string;
  clientId: string;
  token?: string;
  websocketFactory: WebSocketFactory;
  confirmationTimeoutMs?: number;
}

interface ActionEntry {
  plain?: RpcHandler;
  context?: ContextRpcHandler;
}

interface InvokeMessage extends Record<string, unknown> {
  type?: unknown;
  protocol_version?: unknown;
  capabilities?: unknown;
  action?: unknown;
  __sekiro_seq__?: unknown;
  sequence?: unknown;
  group?: unknown;
  clientId?: unknown;
  trace_id?: unknown;
  __rpc_context__?: unknown;
}

export class RpcClient {
  private readonly options: RpcClientOptions;
  private readonly actions = new Map<string, ActionEntry>();
  private readonly lifecycle = new AbortController();
  private readonly active = new Set<AbortController>();
  private socket?: WebSocketLike;
  private startPromise?: Promise<void>;
  private startReject?: (reason?: unknown) => void;
  private confirmationTimer?: ReturnType<typeof setTimeout>;
  private started = false;
  private destroyed = false;

  public constructor(options: RpcClientOptions) {
    this.options = options;
  }

  public registerAction(action: string, handler: RpcHandler): void {
    if (!action || !handler) throw new Error("action and handler are required");
    const entry = this.actions.get(action) ?? {};
    entry.plain = handler;
    this.actions.set(action, entry);
  }

  public registerActionContext(action: string, handler: ContextRpcHandler): void {
    if (!action || !handler) throw new Error("action and handler are required");
    const entry = this.actions.get(action) ?? {};
    entry.context = handler;
    this.actions.set(action, entry);
  }

  public async start(): Promise<void> {
    if (this.destroyed) throw new Error("client is destroyed");
    if (this.started) return;
    if (this.startPromise) return this.startPromise;

    this.startPromise = new Promise<void>((resolve, reject) => {
      this.startResolver = resolve;
      this.startReject = reject;
      let socket: WebSocketLike;
      try {
        socket = this.options.websocketFactory(this.registrationUrl(), this.auth());
      } catch (error) {
        this.failStart(error);
        return;
      }
      this.socket = socket;
      socket.onopen = () => undefined;
      socket.onmessage = (event) => {
        if (this.socket === socket) this.receive(socket, event.data);
      };
      socket.onerror = (event) => {
        if (this.socket === socket && !this.started) this.failStart(new Error(`WebSocket error: ${String(event ?? "unknown")}`), socket);
      };
      socket.onclose = () => {
        if (this.socket === socket && !this.started) this.failStart(new Error("registered confirmation was not received"), socket);
      };
      this.confirmationTimer = setTimeout(() => {
        if (this.socket === socket) this.failStart(new Error("registered confirmation timeout"), socket);
      }, this.options.confirmationTimeoutMs ?? 5000);
    });
    return this.startPromise;
  }

  public destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    this.clearConfirmationTimer();
    this.lifecycle.abort();
    this.startReject?.(new Error("client destroyed"));
    this.startReject = undefined;
    const socket = this.socket;
    this.socket = undefined;
    if (socket && socket.readyState !== 3) socket.close(1000, "client destroyed");
  }

  private registrationUrl(): string {
    const url = new URL(this.options.url);
    url.searchParams.set("protocol_version", String(CURRENT_PROTOCOL_VERSION));
    url.searchParams.set("capabilities", INVOCATION_CONTEXT_CAPABILITY);
    url.searchParams.set("group", this.options.group);
    url.searchParams.set("clientId", this.options.clientId);
    return url.toString();
  }

  private auth(): { headers: Record<string, string>; protocols: string[] } {
    if (!this.options.token) return { headers: {}, protocols: [] };
    return {
      headers: { Authorization: `Bearer ${this.options.token}` },
      protocols: [`sekiro-auth.${this.options.token}`],
    };
  }

  private receive(socket: WebSocketLike, data: unknown): void {
    if (this.socket !== socket) return;
    if (typeof data !== "string") {
      socket.close(1003, "unsupported data");
      return;
    }
    const text = data;
    if (new TextEncoder().encode(text).byteLength > MAX_MESSAGE_BYTES) {
      socket.close(1009, "message too large");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      return;
    }
    if (!isPlainRecord(parsed)) return;
    const message = parsed as InvokeMessage;
    if (message.type === "registered") {
      this.confirm(socket, message);
      return;
    }
    if (!this.started || message.type === "heartbeat" || message.type === "error") return;
    if (message.type === "invoke") void this.dispatch(socket, message);
  }

  private confirm(socket: WebSocketLike, message: InvokeMessage): void {
    if (this.socket !== socket || this.started) return;
    if (message.protocol_version !== CURRENT_PROTOCOL_VERSION || !Array.isArray(message.capabilities) || !message.capabilities.includes(INVOCATION_CONTEXT_CAPABILITY)) {
      this.failStart(new Error("registered confirmation is missing protocol capability"), socket);
      return;
    }
    this.clearConfirmationTimer();
    try {
      const actions = [...this.actions.keys()].sort();
      this.send(socket, { type: "bind", actions });
      this.started = true;
      this.startReject = undefined;
      this.resolveStart();
    } catch (error) {
      this.failStart(error, socket);
    }
  }

  private resolveStart(): void {
    const resolve = this.startResolver;
    this.startResolver = undefined;
    this.startPromise = undefined;
    resolve?.();
  }

  private startResolver?: () => void;

  private failStart(error: unknown, expectedSocket?: WebSocketLike): void {
    if (expectedSocket !== undefined && this.socket !== expectedSocket) return;
    this.clearConfirmationTimer();
    const socket = this.socket;
    this.socket = undefined;
    if (socket && socket.readyState !== 3) socket.close(1000, "registration failed");
    const reject = this.startReject;
    this.startReject = undefined;
    this.startResolver = undefined;
    this.startPromise = undefined;
    reject?.(error);
  }

  private clearConfirmationTimer(): void {
    if (this.confirmationTimer !== undefined) {
      clearTimeout(this.confirmationTimer);
      this.confirmationTimer = undefined;
    }
  }

  private async dispatch(socket: WebSocketLike, message: InvokeMessage): Promise<void> {
    const sequence = typeof message.__sekiro_seq__ === "string" ? message.__sekiro_seq__ : typeof message.sequence === "string" ? message.sequence : "";
    const action = typeof message.action === "string" ? message.action : "";
    const group = typeof message.group === "string" ? message.group : this.options.group;
    const clientId = typeof message.clientId === "string" ? message.clientId : this.options.clientId;
    const traceId = typeof message.trace_id === "string" ? message.trace_id : "";
    let result: unknown;
    let error: unknown;
    if (!sequence || !action || !isInvocationContext(message.__rpc_context__)) {
      error = new Error("invoke requires action, sequence, and context");
    } else {
      const context = message.__rpc_context__ as InvocationContext;
      const entry = this.actions.get(action);
      const controller = new AbortController();
      const abort = () => controller.abort();
      this.active.add(controller);
      this.lifecycle.signal.addEventListener("abort", abort, { once: true });
      let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
      if (context.deadline_unix_ms > 0) {
        deadlineTimer = setTimeout(() => controller.abort(), Math.max(0, context.deadline_unix_ms - Date.now()));
      }
      try {
        if (entry?.context) result = await entry.context(context, message, controller.signal);
        else if (entry?.plain) result = await entry.plain(message);
        else error = new Error(`no handler registered for action ${action}`);
      } catch (caught) {
        error = caught;
      } finally {
        if (deadlineTimer !== undefined) clearTimeout(deadlineTimer);
        this.lifecycle.signal.removeEventListener("abort", abort);
        this.active.delete(controller);
      }
    }
    try {
      this.send(socket, {
        type: "invoke_response",
        __sekiro_seq__: sequence,
        group,
        clientId,
        trace_id: traceId,
        status: error === undefined ? 0 : -1,
        ...(error === undefined ? { data: result } : { error: String(error) }),
      });
    } catch {
      // Destroy may close the socket while an active handler is unwinding.
    }
  }

  private send(socket: WebSocketLike, value: Record<string, unknown>): void {
    socket.send(JSON.stringify(value));
  }
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.getPrototypeOf(value) === Object.prototype;
}

function isInvocationContext(value: unknown): value is InvocationContext {
  if (!isPlainRecord(value) || Object.keys(value).length !== 9) return false;
  for (const key of ["sequence", "trace_id", "group", "action", "client_id", "idempotency_key"]) {
    if (typeof value[key] !== "string") return false;
  }
  for (const key of ["deadline_unix_ms", "attempt"]) {
    if (typeof value[key] !== "number" || !Number.isFinite(value[key]) || !Number.isInteger(value[key])) return false;
  }
  return typeof value.idempotent === "boolean";
}
