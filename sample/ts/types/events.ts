/**
 * @license
 * Copyright 2026 JSReverser-MCP
 * SPDX-License-Identifier: Apache-2.0
 */

import {z} from 'zod';

export interface AppEventMap {
  'browser:launched': {url: string; mode: string};
  'browser:closed': {reason: string};
  'hook:injected': {hookId: string; target: string; url: string};
  'hook:triggered': {hookId: string; data: unknown};
  'network:captured': {requestId: string; url: string; method: string};
  'debugger:paused': {reason: string; scriptId: string};
  'debugger:resumed': Record<string, never>;
  'tool:called': {name: string; durationMs: number; success: boolean};
  'tool:error': {name: string; code: string; message: string};
}

export const appEventSchemas = {
  'browser:launched': z.object({
    url: z.string(),
    mode: z.string(),
  }),
  'browser:closed': z.object({
    reason: z.string(),
  }),
  'hook:injected': z.object({
    hookId: z.string(),
    target: z.string(),
    url: z.string(),
  }),
  'hook:triggered': z.object({
    hookId: z.string(),
    data: z.unknown(),
  }),
  'network:captured': z.object({
    requestId: z.string(),
    url: z.string(),
    method: z.string(),
  }),
  'debugger:paused': z.object({
    reason: z.string(),
    scriptId: z.string(),
  }),
  'debugger:resumed': z.record(z.never()),
  'tool:called': z.object({
    name: z.string(),
    durationMs: z.number().finite().nonnegative(),
    success: z.boolean(),
  }),
  'tool:error': z.object({
    name: z.string(),
    code: z.string(),
    message: z.string(),
  }),
} satisfies Record<keyof AppEventMap, z.ZodTypeAny>;

// 编译期静态校验：确保 appEventSchemas 推导出的 Output 类型与 AppEventMap 完全一致
type AssertEqual<T, U> = T extends U ? (U extends T ? true : never) : never;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
type VerifyEventSchemas = {
  [K in keyof AppEventMap]: AssertEqual<z.output<typeof appEventSchemas[K]>, AppEventMap[K]>;
};

export const appEventValidators = Object.fromEntries(
  Object.entries(appEventSchemas).map(([name, schema]) => [
    name,
    (payload: unknown) => schema.parse(payload),
  ]),
) as {
  [K in keyof AppEventMap]: (payload: unknown) => AppEventMap[K];
};

export function createAppEventBusOptions(): {
  validators: typeof appEventValidators;
} {
  return {validators: appEventValidators};
}
