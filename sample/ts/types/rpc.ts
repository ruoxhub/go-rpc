/**
 * @license
 * Copyright 2026 JSReverser-MCP
 * SPDX-License-Identifier: Apache-2.0
 */

/**
 * Sekiro 协议类型定义
 */

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

export {
  type RpcRequest,
  type RpcResponse,
  type ActionHandler,
  type RpcConnectionState,
  type RpcClientOptions,
};
