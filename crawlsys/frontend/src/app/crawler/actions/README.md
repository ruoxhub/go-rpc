# 接口管理

- `page.tsx`：RSC 并行加载平台选项和按 URL `platform_id` 筛选的接口列表。
- `new/page.tsx`：新建接口入口。
- `[id]/edit/page.tsx`：并行加载接口详情与包含已删除记录的平台选项，以识别历史归属。
- `[id]/parser/`：并行加载 Action、平台、参数 Schema、Parser 能力、样例、Revision 与模型，提供页面私有 ParserWorkspace 状态和响应式工作台骨架。
- `_components/ActionForm/`：创建与编辑共享表单；创建时选择可用平台，编辑时只读展示平台归属；参数 Schema 以 JSON 字符串编辑，并由 `utils/validateParamsSchema.ts` 按 2020-12 / draft-07 校验标准 JSON Schema 或 legacy 参数数组；`ba_sample_safe` 显式确认取样无副作用。
- `_components/ActionActions/`：编辑入口、独立的 Parser 配置路由入口及带对话框错误反馈的删除操作。
- `_components/ImportActionsDialog/`：限制 2 MiB / 1000 条后读取本地 JSON 数组，调用批量导入接口并保留失败上下文。

请求、字段错误映射及平台/接口类型复用 `src/utils/crawler`；通用表格、筛选栏、表单域和确认框复用 crawler 共享组件。
