# Action Parser API

- `action-parser.types.ts`：动态 Parser 的页面模型与 wire 类型。
- `action-parser.api.ts`：Parser 领域请求函数，并在 API 边界完成 assist receipt 的字段映射。

页面不得手拼 Parser URL，也不得接触 receipt 的 wire 字段。
