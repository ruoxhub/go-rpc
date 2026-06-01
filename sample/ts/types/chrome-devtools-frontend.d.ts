/**
 * @license
 * Copyright 2026 Google LLC
 * SPDX-License-Identifier: Apache-2.0
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

// 空类型声明用于绕过 chrome-devtools-frontend 类型检查
declare module 'chrome-devtools-frontend/**/*' {
  const _default: any;
  export default _default;
}
