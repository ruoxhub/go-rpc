/**
 * @license
 * Copyright 2026 JSReverser-MCP
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * RpcClient — Node.js 端 Sekiro 客户端
 *
 * 替代浏览器端 BaseClient，删除所有浏览器绑定：
 * - 无 Chrome Storage 配置加载
 * - 无 window 域名检测
 * - 无 window.postMessage 桥接
 *
 * 职责：管理 Action 注册、WebSocket 生命周期、连接/重连、消息处理
 */

import WebSocket from 'ws';

import type {RpcClientConfig, ClientStatus} from '../types/platform.js';
import type {
  RpcRequest,
  RpcResponse,
  ActionHandler,
  RpcConnectionState,
} from '../types/rpc.js';

/** 默认配置 */
const DEFAULT_RECONNECT_BASE_DELAY = 2000;
const DEFAULT_RECONNECT_MAX_DELAY = 30000;
// 服务端 SetReadDeadline = HeartbeatTimeout/2 = 30s，必须 < 30s 才能避开服务端读超时关连接。
// 选 15s（≈ 30s/2）留出充足余量，避免 Node 事件循环抖动/GC 导致心跳错过窗口。
const DEFAULT_HEARTBEAT_INTERVAL = 15000;
// pong 超时必须 ≥ 心跳间隔，否则一次 ack 慢就会触发本地重连，制造不必要抖动。
const DEFAULT_PONG_TIMEOUT = 20000;

export class RpcClient {
  private readonly config: RpcClientConfig;
  private readonly clientId: string;
  private isInitialized = false;

  // WebSocket & 重连
  private wsURL = '';
  private socket: WebSocket | null = null;
  private handlers = new Map<string, ActionHandler>();
  private isManualDisconnect = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private pongTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;

  // 可配置参数
  private readonly reconnectBaseDelay: number;
  private readonly reconnectMaxDelay: number;
  private readonly heartbeatInterval: number;
  private readonly pongTimeout: number;

  // 连接状态
  private _connectionState: RpcConnectionState = 'disconnected';

  constructor(config: RpcClientConfig) {
    this.config = config;
    this.clientId = config.clientId || Math.random().toString(36).substring(2, 11);
    this.reconnectBaseDelay = config.reconnectBaseDelay ?? DEFAULT_RECONNECT_BASE_DELAY;
    this.reconnectMaxDelay = config.reconnectMaxDelay ?? DEFAULT_RECONNECT_MAX_DELAY;
    this.heartbeatInterval = config.heartbeatInterval ?? DEFAULT_HEARTBEAT_INTERVAL;
    this.pongTimeout = config.pongTimeout ?? DEFAULT_PONG_TIMEOUT;

    // 注册默认的 _execjs handler
    this.handlers.set('_execjs', this._execjsHandler.bind(this));
  }

  /**
   * 统一日志
   */
  private log(message: string, level: 'log' | 'warn' | 'error' = 'log'): void {
    const prefix = `[RpcClient][${this.config.group}]`;
    const timestamp = new Date().toISOString();
    const fullMessage = `${timestamp} ${prefix} ${message}`;
    console[level](fullMessage);
  }

  /**
   * 构建 WebSocket 注册 URL
   */
  private buildWebSocketURL(): string {
    const host = this.config.rpcHost || 'ws://127.0.0.1:5612';
    return `${host}/business/register?group=${this.config.group}&clientId=${this.clientId}`;
  }

  /**
   * 注册 Action
   */
  registerAction(name: string, handler: ActionHandler): void {
    if (this.handlers.has(name)) {
      this.log(`Action "${name}" 已注册，将覆盖`, 'warn');
    }
    this.handlers.set(name, handler);
    this.log(`注册 Action: ${name}`);
  }

  /**
   * 移除 Action
   */
  unregisterAction(name: string): boolean {
    return this.handlers.delete(name);
  }

  /**
   * 启动客户端 — 等待首次连接建立后返回
   */
  async start(): Promise<void> {
    const wsURL = this.buildWebSocketURL();
    this.log(`连接 Sekiro: ${wsURL}`);
    this.wsURL = wsURL;

    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = (event: WebSocket.ErrorEvent) => {
        cleanup();
        reject(new Error(event.message || 'WebSocket 连接失败'));
      };

      const cleanup = () => {
        if (this.socket) {
          this.socket.removeEventListener('open', onOpen);
          this.socket.removeEventListener('error', onError);
        }
      };

      this.connect();

      if (this.socket) {
        this.socket.addEventListener('open', onOpen);
        this.socket.addEventListener('error', onError);
      } else {
        reject(new Error('创建 WebSocket 失败'));
      }
    });

    this.isInitialized = true;
    this.log('Sekiro 客户端初始化成功');
  }

  /**
   * 使用新地址重新连接
   */
  reconnect(newSekiroHost: string): void {
    this.log('正在重新连接...');
    this.config.rpcHost = newSekiroHost;
    const wsURL = this.buildWebSocketURL();
    this.log(`切换地址重连：${wsURL}`);
    // 先断开，_internalDisconnect 会把 isManualDisconnect 置为 true 防止旧 onclose 触发重连
    this._internalDisconnect();
    this.wsURL = wsURL;
    // 显式复位手动断开标记，防止后续 connect() 与旧 onclose 之间出现竞态
    this.isManualDisconnect = false;
    this.connect();
    this.log(`连接新地址：${wsURL}`);
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.log('正在断开连接...');
    this._internalDisconnect();
    this.isInitialized = false;
    this.log('已断开连接');
  }

  /**
   * 获取客户端状态
   */
  getStatus(): ClientStatus {
    return {
      isInitialized: this.isInitialized,
      isConnected: this.isConnected(),
      connectionState: this._connectionState,
      group: this.config.group,
      clientId: this.clientId,
      actionCount: this.getActionNames().length,
      rpcHost: this.config.rpcHost,
    };
  }

  /**
   * 获取所有已注册的 Action 名称（不含内部 _execjs）
   */
  getActionNames(): string[] {
    return Array.from(this.handlers.keys()).filter(name => name !== '_execjs');
  }

  // ==================== WebSocket 核心（原 SekiroClient）====================

  /**
   * 默认 _execjs handler — 执行 JavaScript 代码
   */
  private _execjsHandler(
    request: RpcRequest,
    resolve: (response: unknown) => void,
    reject: (error: string) => void,
  ): void {
    const extraFields = request as unknown as Record<string, unknown>;
    const param =
      extraFields.param || request.params || extraFields.code || '';
    if (!param) {
      reject('缺少执行参数 param');
      return;
    }

    try {
      const fn = new Function(
        'return (async () => { return ' + param + ' })()',
      );
      const result = fn();

      if (result && typeof result.then === 'function') {
        (result as Promise<unknown>)
          .then(res =>
            resolve(res !== undefined ? res : '执行成功 (无返回值)'),
          )
          .catch((err: unknown) =>
            reject('执行错误：' + ((err as Error).message || err)),
          );
      } else {
        resolve(result !== undefined ? result : '执行成功 (无返回值)');
      }
    } catch (err: unknown) {
      reject('语法错误：' + ((err as Error).message || err));
    }
  }

  /**
   * 更新连接状态
   */
  private setConnectionState(state: RpcConnectionState): void {
    this._connectionState = state;
    // this.log(`连接状态变更: ${state}`);
  }

  /**
   * 连接 WebSocket
   */
  private connect(): void {
    // this.log(`正在连接 wsURL: ${this.wsURL}`);
    this.isManualDisconnect = false;
    this.setConnectionState('connecting');

    try {
      this.socket = new WebSocket(this.wsURL);

      this.socket.onopen = () => {
        // this.log('成功建立连接');
        this.setConnectionState('connected');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
        // 建连立刻发一发心跳，避免在首个 interval（默认 15s）到来前被服务端读超时关连接
        this.sendHeartbeatNow();
      };

      this.socket.onmessage = (event: WebSocket.MessageEvent) => {
        try {
          const data =
            typeof event.data === 'string'
              ? event.data
              : Buffer.from(event.data as ArrayBuffer).toString('utf-8');
          this.handleRpcRequest(data);
        } catch (ex) {
          this.log(`处理消息异常：${ex}`);
        }
      };

      this.socket.onclose = (event: WebSocket.CloseEvent) => {
        this.stopHeartbeat();

        if (this.isManualDisconnect) {
          // this.log('连接已手动断开');
          this.setConnectionState('disconnected');
          return;
        }
        // this.log(`连接断开 (code=${event.code})，将自动重连`);
        this.scheduleReconnect();
      };

      this.socket.onerror = (event: WebSocket.ErrorEvent) => {
        this.log(`WebSocket 错误：${event.message || '未知错误'}`);
      };
    } catch (e) {
      this.log(`创建连接失败，将自动重连：${e}`);
      this.scheduleReconnect();
    }
  }

  /**
   * 启动心跳：发送应用层 JSON heartbeat 消息。
   *
   * 服务端 SetReadDeadline = HeartbeatTimeout/2 = 30s 内必须收到任意消息，
   * 且只识别 {type:"heartbeat",...} 这种 JSON 心跳后才会 UpdateActive()。
   * WebSocket 协议层 ping/pong 不会触发服务端 ReadMessage 返回，无法续命。
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    if (this.heartbeatInterval <= 0) return;

    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeatNow();
    }, this.heartbeatInterval);
  }

  /**
   * 立刻发送一次心跳，并启动 pong 超时检测。
   * 用于 onopen 后立即续命，避免在第一个 interval 到来前被服务端读超时关连接。
   */
  private sendHeartbeatNow(): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      this.socket.send(
        JSON.stringify({
          type: 'heartbeat',
          group: this.config.group,
          clientId: this.clientId,
          timestamp: Date.now(),
        }),
      );
      // pong 超时检测：若在 pongTimeout 内未收到任何消息（含心跳响应），主动断开重连
      if (this.pongTimeoutTimer) clearTimeout(this.pongTimeoutTimer);
      this.pongTimeoutTimer = setTimeout(() => {
        this.log('心跳响应超时，主动断开重连', 'warn');
        this._internalDisconnect();
        this.isManualDisconnect = false;
        this.scheduleReconnect();
      }, this.pongTimeout);
    } catch (e) {
      this.log(`心跳发送失败：${e}`, 'warn');
    }
  }

  /**
   * 停止心跳并清除 pong 超时计时器
   */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.pongTimeoutTimer) {
      clearTimeout(this.pongTimeoutTimer);
      this.pongTimeoutTimer = null;
    }
  }

  /**
   * 调度重连 — 指数退避
   */
  private scheduleReconnect(): void {
    if (this.isManualDisconnect) return;

    this.setConnectionState('reconnecting');

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    // 指数退避: base * 2^attempts，封顶 maxDelay
    const delay = Math.min(
      this.reconnectBaseDelay * Math.pow(2, this.reconnectAttempts),
      this.reconnectMaxDelay,
    );
    this.reconnectAttempts++;

    // this.log(`${delay}ms 后重连 (attempt=${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => {
      if (!this.isManualDisconnect) {
        this.connect();
      }
    }, delay);
  }

  /**
   * 内部断开（不重置 isInitialized）
   */
  private _internalDisconnect(): void {
    this.isManualDisconnect = true;
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.socket) {
      try {
        this.socket.close();
      } catch (e) {
        this.log(`断开连接异常：${e}`);
      }
      this.socket = null;
    }

    this.setConnectionState('disconnected');
  }

  /**
   * 处理 Sekiro 请求
   */
  private handleRpcRequest(requestJson: string): void {
    let request: RpcRequest;
    try {
      request = JSON.parse(requestJson);
    } catch (e) {
      this.log(`JSON 解析失败：${e}`);
      return;
    }

    // 服务端会主动下发的非业务控制消息：heartbeat 响应、error 通知、invoke_response。
    // 这些消息没有 action，但同样没有 __sekiro_seq__；不能当 RPC 请求回失败响应，
    // 否则会触发服务端 unknown-type 兜底再次回包，形成"缺少 action ↔ unknown type"无限回环。
    const msgType = (request as unknown as {type?: string}).type;
    if (msgType === 'heartbeat' || msgType === 'error' || msgType === 'invoke_response') {
      // 任意来自服务端的消息都视为"还活着"，清掉 pong 超时计时器
      if (this.pongTimeoutTimer) {
        clearTimeout(this.pongTimeoutTimer);
        this.pongTimeoutTimer = null;
      }
      return;
    }

    const seq = request.__sekiro_seq__ || '';

    if (!request.action) {
      // 没有 action 也没有 seq 的消息一定不是合法 RPC 请求，静默丢弃避免回环
      if (!seq) {
        this.log(`忽略无 action 且无 seq 的消息：${requestJson}`, 'warn');
        return;
      }
      this.sendFailed(seq, '缺少 request 参数 {action}');
      return;
    }

    const action = request.action;
    const handler = this.handlers.get(action);

    if (!handler) {
      this.sendFailed(seq, `未定义 action 处理函数：${action}`);
      return;
    }

    try {
      handler(
        request,
        response => {
          try {
            this.sendSuccess(seq, response);
          } catch (e) {
            this.sendFailed(seq, `响应异常：${e}`);
          }
        },
        errorMessage => {
          this.sendFailed(seq, errorMessage);
        },
      );
    } catch (e) {
      this.log(`执行 action 处理函数异常：${e}`);
      this.sendFailed(seq, String(e));
    }
  }

  /**
   * 发送成功响应
   */
  private sendSuccess(seq: string, response: unknown): void {
    let responseJson: Record<string, unknown>;

    if (typeof response === 'string') {
      try {
        const parsed = JSON.parse(response);
        if (Array.isArray(parsed)) {
          responseJson = {data: parsed};
        } else if (typeof parsed === 'object' && parsed !== null) {
          responseJson = parsed as Record<string, unknown>;
        } else {
          responseJson = {data: parsed};
        }
      } catch {
        responseJson = {data: response};
      }
    } else if (Array.isArray(response)) {
      responseJson = {data: response};
    } else if (typeof response === 'object' && response !== null) {
      responseJson = response as Record<string, unknown>;
    } else {
      responseJson = {data: response};
    }

    responseJson.code = 0;
    responseJson.status = 0;
    responseJson.__sekiro_seq__ = seq;

    const responseText = JSON.stringify(responseJson);
    this.send(responseText);
  }

  /**
   * 发送失败响应
   */
  private sendFailed(seq: string, errorMessage: string): void {
    const responseJson: RpcResponse = {
      message: errorMessage,
      status: -1,
      __sekiro_seq__: seq,
    };

    const responseText = JSON.stringify(responseJson);
    this.log(`返回失败信息：${responseText}`);
    this.send(responseText);
  }

  /**
   * 发送 WebSocket 消息
   */
  private send(message: string): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(message);
      } catch (e) {
        this.log(`发送消息异常：${e}`);
      }
    } else {
      this.log('WebSocket 未连接，无法发送消息');
    }
  }

  /**
   * 检查连接状态
   */
  private isConnected(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
}
