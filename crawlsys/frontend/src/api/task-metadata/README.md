# Task Metadata API

- `task-metadata.types.ts`：跨 TaskForm 与 Parser 复用的 Action schema、LLM 模型 metadata wire 类型。
- `task-metadata.api.ts`：只读 metadata 请求函数。

本目录不承载页面状态或表字段 metadata；后者仍属于 TaskForm 私有逻辑。
