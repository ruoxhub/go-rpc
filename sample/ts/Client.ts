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


/** RpcClient 状态快照 */
interface ClientStatus {
  isInitialized: boolean;
  isConnected: boolean;
  connectionState: RpcConnectionState;
  group: string;
  clientId: string;
  actionCount: number;
  rpcHost: string;
}
/** RpcClient 构造配置 */
interface RpcClientConfig {
  /** 分组名 */
  group: string;
  /** rpc Server 地址，如 ws://127.0.0.1:5612 */
  rpcHost: string;
  /** 客户端 ID（默认自动生成） */
  clientId?: string;
  /** 重连基础间隔 ms */
  reconnectBaseDelay?: number;
  /** 重连最大间隔 ms */
  reconnectMaxDelay?: number;
  /** 心跳间隔 ms */
  heartbeatInterval?: number;
}
/** Sekiro 请求（Server → Client） */
interface RpcRequest {
  __sekiro_seq__: string;
  action: string;
  params?: Record<string, unknown>;
}

/** Sekiro 响应（Client → Server） */
interface RpcResponse {
  code?: number;
  status?: number;
  message?: string;
  data?: unknown;
  __sekiro_seq__: string;
}

/** Action 处理函数签名 */
type ActionHandler = (
  request: RpcRequest,
  resolve: (response: unknown) => void,
  reject: (errorMessage: string) => void,
) => void;

/** SekiroClient 连接状态 */
type RpcConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting';

/** SekiroClient 配置选项 */
interface RpcClientOptions {
  /** WebSocket URL 前缀，如 ws://127.0.0.1:5612 */
  rpcHost: string;
  /** 分组名 */
  group: string;
  /** 客户端 ID（默认自动生成） */
  clientId?: string;
  /** 重连基础间隔 ms（默认 2000） */
  reconnectBaseDelay?: number;
  /** 重连最大间隔 ms（默认 30000） */
  reconnectMaxDelay?: number;
  /** 心跳间隔 ms（默认 30000，0 关闭） */
  heartbeatInterval?: number;
}


/** 默认配置 */
const DEFAULT_RECONNECT_BASE_DELAY = 2000;
const DEFAULT_RECONNECT_MAX_DELAY = 30000;
const DEFAULT_HEARTBEAT_INTERVAL = 30000;

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
  private reconnectAttempts = 0;

  // 可配置参数
  private readonly reconnectBaseDelay: number;
  private readonly reconnectMaxDelay: number;
  private readonly heartbeatInterval: number;

  // 连接状态
  private _connectionState: RpcConnectionState = 'disconnected';

  constructor(config: RpcClientConfig) {
    this.config = config;
    this.clientId = config.clientId || Math.random().toString(36).substring(2, 11);
    this.reconnectBaseDelay = config.reconnectBaseDelay ?? DEFAULT_RECONNECT_BASE_DELAY;
    this.reconnectMaxDelay = config.reconnectMaxDelay ?? DEFAULT_RECONNECT_MAX_DELAY;
    this.heartbeatInterval = config.heartbeatInterval ?? DEFAULT_HEARTBEAT_INTERVAL;

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
   * 启动客户端 — 连接到 Sekiro Server
   */
  async start(): Promise<void> {
    try {
      const wsURL = this.buildWebSocketURL();
      this.log(`连接 Sekiro: ${wsURL}`);
      this.wsURL = wsURL;
      this.connect();
      this.isInitialized = true;
      this.log('Sekiro 客户端初始化成功');
    } catch (error) {
      this.log(
        `Sekiro 客户端初始化失败：${error instanceof Error ? error.message : error}`,
        'error',
      );
      throw error;
    }
  }

  /**
   * 使用新地址重新连接
   */
  reconnect(newSekiroHost: string): void {
    this.log('正在重新连接...');
    this.config.rpcHost = newSekiroHost;
    const wsURL = this.buildWebSocketURL();
    this.log(`切换地址重连：${wsURL}`);
    this._internalDisconnect();
    this.wsURL = wsURL;
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
    this.log(`连接状态变更: ${state}`);
  }

  /**
   * 连接 WebSocket
   */
  private connect(): void {
    this.log(`正在连接 wsURL: ${this.wsURL}`);
    this.isManualDisconnect = false;
    this.setConnectionState('connecting');

    try {
      this.socket = new WebSocket(this.wsURL);

      this.socket.onopen = () => {
        this.log('成功建立连接');
        this.setConnectionState('connected');
        this.reconnectAttempts = 0;
        this.startHeartbeat();
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
          this.log('连接已手动断开');
          this.setConnectionState('disconnected');
          return;
        }
        this.log(`连接断开 (code=${event.code})，将自动重连`);
        this.scheduleReconnect();
      };

      this.socket.onerror = (event: WebSocket.ErrorEvent) => {
        this.log(`WebSocket 错误：${event.message || '未知错误'}`);
      };

      // ws 包支持 pong 事件
      this.socket.on('pong', () => {
        // 心跳 pong 收到，连接正常
      });
    } catch (e) {
      this.log(`创建连接失败，将自动重连：${e}`);
      this.scheduleReconnect();
    }
  }

  /**
   * 启动心跳
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    if (this.heartbeatInterval <= 0) return;

    this.heartbeatTimer = setInterval(() => {
      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        try {
          this.socket.ping();
        } catch {
          this.log('心跳 ping 发送失败');
        }
      }
    }, this.heartbeatInterval);
  }

  /**
   * 停止心跳
   */
  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
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

    this.log(`${delay}ms 后重连 (attempt=${this.reconnectAttempts})`);
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

    const seq = request.__sekiro_seq__ || '';

    if (!request.action) {
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
        responseJson = JSON.parse(response) as Record<string, unknown>;
      } catch {
        responseJson = {data: response};
      }
    } else if (typeof response === 'object' && response !== null) {
      responseJson = response as Record<string, unknown>;
    } else {
      responseJson = {data: response};
    }

    // 确保是数组或字符串时包装为对象
    if (Array.isArray(responseJson) || typeof responseJson === 'string') {
      responseJson = {data: responseJson, code: 0};
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
