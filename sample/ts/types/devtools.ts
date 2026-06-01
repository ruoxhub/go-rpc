/**
 * @license
 * Copyright 2026 JSReverser-MCP
 * SPDX-License-Identifier: Apache-2.0
 */

// DevTools 类型定义 - 本地化避免路径问题
export interface Connection {
  connection: () => {
    send: (
      method: string,
      params?: Record<string, unknown>,
    ) => Promise<unknown>;
  };
}

export interface CDPSession {
  send: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  on: (event: string, callback: (...args: unknown[]) => void) => void;
}

export interface Page {
  on: (event: string, callback: (...args: unknown[]) => void) => void;
}

export type Browser = unknown;
export type ConsoleMessage = unknown;
export type Dialog = unknown;
export type Frame = unknown;
export type HTTPRequest = unknown;
export type Protocol = unknown;
export type Handler = unknown;

export interface AggregatedIssue {
  code: string;
  title: () => string;
  description: () => string | null;
}

export type Issue = unknown;
