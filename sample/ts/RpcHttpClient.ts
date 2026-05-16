/**
 * Rpc HTTP API Client (TypeScript)
 *
 * 基于 fetch 的 Rpc 公开 HTTP API 客户端。
 * 支持自动重试、错误处理。
 *
 * 覆盖端点:
 *   - GET  /health
 *   - GET  /business/groupList
 *   - GET  /business/clientQueue
 *   - POST /business/invoke
 *   - POST /business/execjs
 *   - POST /business/cookie
 *   - POST /business/html
 *   - POST /v1/chat/completions
 *
 * Usage:
 *   const client = new RpcHttpClient({ baseUrl: "http://localhost:5612", apiToken: "your_token" });
 *   const groups = await client.groupList();
 *   const result = await client.invoke("test", "hello", { params: { name: "world" } });
 *   client.dispose();
 */

// ─── Types ───────────────────────────────────────────────────────────────────

/** 通用 API 响应格式 */
export interface RpcApiResponse<T = unknown> {
  status: number;
  message: string;
  data: T;
  [key: string]: unknown;
}

/** 客户端配置 */
export interface RpcHttpClientConfig {
  /** 服务器地址，默认 http://localhost:5612 */
  baseUrl?: string;
  /** API Token（可选） */
  apiToken?: string;
  /** 请求超时 ms，默认 30000 */
  timeout?: number;
  /** 最大重试次数，默认 3 */
  retryAttempts?: number;
}

/** invoke 可选参数 */
export interface InvokeOptions {
  clientId?: string;
  params?: Record<string, unknown> | unknown[];
  timeout?: number;
  constantInvoke?: string;
}

/** execjs / cookie / html 通用可选参数 */
export interface ClientTargetOptions {
  clientId?: string;
  constantInvoke?: string;
}

/** chat completions 可选参数 */
export interface ChatCompletionsOptions {
  stream?: boolean;
  group?: string;
  clientId?: string;
  constantInvoke?: string;
  extraBody?: Record<string, unknown>;
}

/** chat message */
export interface ChatMessage {
  role: string;
  content: string;
}

// ─── Errors ──────────────────────────────────────────────────────────────────

/** Rpc 客户端基础异常 */
export class RpcError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RpcError";
  }
}

/** Rpc API 返回的业务错误（HTTP 200 但 status != 0） */
export class RpcAPIError extends RpcError {
  public readonly status: number;
  public readonly rawResponse: RpcApiResponse | null;

  constructor(message: string, status: number = -1, rawResponse: RpcApiResponse | null = null) {
    super(message);
    this.name = "RpcAPIError";
    this.status = status;
    this.rawResponse = rawResponse;
  }
}

/** HTTP 层错误（网络、超时、4xx/5xx 等） */
export class RpcHTTPError extends RpcError {
  public readonly statusCode: number | null;

  constructor(message: string, statusCode: number | null = null) {
    super(message);
    this.name = "RpcHTTPError";
    this.statusCode = statusCode;
  }
}

// ─── Defaults ────────────────────────────────────────────────────────────────

const DEFAULT_BASE_URL = "http://localhost:5612";
const DEFAULT_TIMEOUT = 30_000; // ms
const DEFAULT_RETRY_ATTEMPTS = 3;

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 判断异常是否可重试（网络错误、超时、5xx） */
function isRetryable(err: unknown): boolean {
  if (err instanceof RpcHTTPError) {
    return err.statusCode !== null && err.statusCode >= 500;
  }
  // fetch 抛出的 TypeError / AbortError 等视为网络错误
  if (err instanceof TypeError) return true;
  if (err instanceof DOMException && err.name === "AbortError") return true;
  return false;
}

/** 过滤 null/undefined 的键 */
function stripNil(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v != null) result[k] = v;
  }
  return result;
}

/** 指数退避延迟 */
function backoffDelay(attempt: number, baseMs = 1000, maxMs = 10_000): number {
  return Math.min(baseMs * Math.pow(2, attempt), maxMs);
}

/** sleep */
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

// ─── Client ──────────────────────────────────────────────────────────────────

export class RpcHttpClient {
  private readonly baseUrl: string;
  private readonly apiToken: string | undefined;
  private readonly timeout: number;
  private readonly retryAttempts: number;
  private controller: AbortController | null = null;

  constructor(config: RpcHttpClientConfig = {}) {
    this.baseUrl = (config.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.apiToken = config.apiToken;
    this.timeout = config.timeout ?? DEFAULT_TIMEOUT;
    this.retryAttempts = config.retryAttempts ?? DEFAULT_RETRY_ATTEMPTS;
  }

  // ── 生命周期 ────────────────────────────────────────────────────────────

  /** 取消进行中的请求并清理资源 */
  dispose(): void {
    this.controller?.abort();
    this.controller = null;
  }

  // ── 底层请求 ────────────────────────────────────────────────────────────

  private async request<T = unknown>(
    method: string,
    path: string,
    opts?: {
      params?: Record<string, unknown>;
      jsonData?: Record<string, unknown>;
      overrideTimeout?: number;
    },
  ): Promise<T> {
    let lastError: unknown;

    for (let attempt = 0; attempt <= this.retryAttempts; attempt++) {
      try {
        return await this._doRequest<T>(method, path, opts);
      } catch (err) {
        lastError = err;
        if (attempt < this.retryAttempts && isRetryable(err)) {
          const delay = backoffDelay(attempt);
          console.warn(
            `[RpcHttpClient] 请求失败，${delay}ms 后重试 (attempt=${attempt + 1}/${this.retryAttempts}): ${err}`,
          );
          await sleep(delay);
          continue;
        }
        throw err;
      }
    }
    throw lastError;
  }

  private async _doRequest<T = unknown>(
    method: string,
    path: string,
    opts?: {
      params?: Record<string, unknown>;
      jsonData?: Record<string, unknown>;
      overrideTimeout?: number;
    },
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}${path}`);

    // query params
    if (opts?.params) {
      const clean = stripNil(opts.params);
      for (const [k, v] of Object.entries(clean)) {
        url.searchParams.set(k, String(v));
      }
    }

    // headers
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiToken) {
      headers["Authorization"] = `Bearer ${this.apiToken}`;
    }

    // timeout via AbortController
    this.controller?.abort();
    this.controller = new AbortController();
    const timeoutMs = opts?.overrideTimeout ?? this.timeout;
    const timer = setTimeout(() => this.controller!.abort(), timeoutMs);

    try {
      const response = await fetch(url.toString(), {
        method,
        headers,
        body: opts?.jsonData ? JSON.stringify(stripNil(opts.jsonData)) : undefined,
        signal: this.controller.signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new RpcHTTPError(
          `HTTP ${response.status}: ${text}`,
          response.status,
        );
      }

      const data: RpcApiResponse<T> = await response.json();

      // 统一响应格式处理
      if (typeof data === "object" && data !== null && "status" in data) {
        if (data.status !== 0) {
          throw new RpcAPIError(
            data.message || "Unknown error",
            data.status,
            data,
          );
        }
      }

      return data as unknown as T;
    } catch (err) {
      if (err instanceof RpcError) throw err;
      if (err instanceof TypeError) {
        throw new RpcHTTPError(`Request failed: ${(err as Error).message}`);
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new RpcHTTPError(`Request timeout after ${timeoutMs}ms`);
      }
      throw new RpcHTTPError(`Request failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }
  }

  // ── 公开 API ────────────────────────────────────────────────────────────

  /** GET /health — 健康检查 */
  async health(): Promise<RpcApiResponse> {
    return this.request("GET", "/health");
  }

  /** GET /business/groupList — 获取分组列表 */
  async groupList(): Promise<string[]> {
    const resp = await this.request<RpcApiResponse<string[]>>("GET", "/business/groupList");
    return resp.data ?? [];
  }

  /** GET /business/clientQueue — 获取某分组下的客户端队列 */
  async clientQueue(group: string): Promise<string[]> {
    if (!group) throw new Error("group is required");
    const resp = await this.request<RpcApiResponse<string[]>>("GET", "/business/clientQueue", {
      params: { group },
    });
    return resp.data ?? [];
  }

  /**
   * POST /business/invoke — RPC 调用
   *
   * @param group  分组名称（必填）
   * @param action 动作名称（必填）
   * @param opts   可选参数
   */
  async invoke(group: string, action: string, opts?: InvokeOptions): Promise<unknown> {
    if (!group || !action) throw new Error("group and action are required");

    const payload = {
      group,
      action,
      clientId: opts?.clientId,
      params: opts?.params,
      timeout: opts?.timeout,
      constantInvoke: opts?.constantInvoke,
    };

    const resp = await this.request<RpcApiResponse>("POST", "/business/invoke", {
      jsonData: payload,
    });
    return resp.data;
  }

  /** POST /business/execjs — 在目标客户端执行 JS 代码 */
  async execjs(group: string, code: string, opts?: ClientTargetOptions): Promise<unknown> {
    if (!group || !code) throw new Error("group and code are required");

    const payload = {
      group,
      code,
      clientId: opts?.clientId,
      constantInvoke: opts?.constantInvoke,
    };

    const resp = await this.request<RpcApiResponse>("POST", "/business/execjs", {
      jsonData: payload,
    });
    return resp.data;
  }

  /** POST /business/cookie — 获取目标客户端 Cookie */
  async getCookie(group: string, opts?: ClientTargetOptions): Promise<unknown> {
    if (!group) throw new Error("group is required");

    const payload = {
      group,
      clientId: opts?.clientId,
      constantInvoke: opts?.constantInvoke,
    };

    const resp = await this.request<RpcApiResponse>("POST", "/business/cookie", {
      jsonData: payload,
    });
    return resp.data;
  }

  /** POST /business/html — 获取目标客户端 HTML */
  async getHtml(group: string, opts?: ClientTargetOptions): Promise<unknown> {
    if (!group) throw new Error("group is required");

    const payload = {
      group,
      clientId: opts?.clientId,
      constantInvoke: opts?.constantInvoke,
    };

    const resp = await this.request<RpcApiResponse>("POST", "/business/html", {
      jsonData: payload,
    });
    return resp.data;
  }

  /**
   * POST /v1/chat/completions — OpenAI 兼容接口（非流式）
   *
   * @param model    模型名称（必填）
   * @param messages 消息列表
   * @param opts     可选参数
   */
  async chatCompletions(
    model: string,
    messages: ChatMessage[],
    opts?: ChatCompletionsOptions,
  ): Promise<Record<string, unknown>> {
    if (!model) throw new Error("model is required");
    if (opts?.stream) throw new Error("stream=true is not supported yet");

    const payload: Record<string, unknown> = {
      model,
      messages,
      stream: false,
    };
    if (opts?.group != null) payload["group"] = opts.group;
    if (opts?.clientId != null) payload["clientId"] = opts.clientId;
    if (opts?.constantInvoke != null) payload["constantInvoke"] = opts.constantInvoke;
    if (opts?.extraBody) Object.assign(payload, opts.extraBody);

    // chat completions 响应格式与标准 API 不同，直接透传 JSON
    const url = `${this.baseUrl}/v1/chat/completions`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (this.apiToken) {
      headers["Authorization"] = `Bearer ${this.apiToken}`;
    }

    this.controller?.abort();
    this.controller = new AbortController();
    const timer = setTimeout(() => this.controller!.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: this.controller.signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => "");
        throw new RpcHTTPError(`HTTP ${response.status}: ${text}`, response.status);
      }

      return response.json();
    } catch (err) {
      if (err instanceof RpcError) throw err;
      if (err instanceof TypeError) {
        throw new RpcHTTPError(`Request failed: ${(err as Error).message}`);
      }
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new RpcHTTPError(`Request timeout after ${this.timeout}ms`);
      }
      throw new RpcHTTPError(`Request failed: ${(err as Error).message}`);
    } finally {
      clearTimeout(timer);
    }
  }
}

export default RpcHttpClient;