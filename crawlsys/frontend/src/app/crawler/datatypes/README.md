# 数据模型管理

- `page.tsx`：服务端加载已同步的 ORM/DTO 数据类型元数据列表。
- `_components/SyncDatatypesButton/`：调用 `POST /datatypes/sync` 触发代码内省同步，带加载态与结果反馈。
- `_components/DatatypesTable/`：列表展示标识、模型类名、物理表名、描述、列数、DTO 字段数与启停开关，并提供「管理数据」入口与详情抽屉。
- `_components/DatatypeStatusSwitch/`：数据模型启用状态开关，PATCH 更新失败时回滚显示。
- `_components/DatatypeDetailDrawer/`：右侧抽屉，按页签展示数据库物理列、解析器 DTO 映射与冲突更新策略。
- `[key]/data/`：数据记录管理子页面。
  - `page.tsx`：服务端加载该数据类型的记录编辑器元数据（列契约、主键），404 时渲染 not-found。
  - `_components/DatatypeRowsBrowser/`：客户端分页查询、关键字与单字段过滤，`loading` 由「查询签名是否已结算」派生，避免 effect 内同步 setState。
  - `_components/DatatypeRowFormDialog/`：新增/编辑弹窗，按列契约渲染控件，编辑模式只提交改动字段。
  - `_components/DatatypeRowDeleteButton/`：二次确认删除，失败在弹窗内反馈。
  - `utils/rows.ts`：行记录与表单草稿的双向转换、类型校验与单元格格式化。
  - `data.test.tsx`：数据记录浏览、过滤与表单转换测试。

请求与类型复用 `src/api/datatype/`；通用表格、筛选栏、表单域与确认框复用 crawler 局部共享组件。组件仅服务数据模型模块；确认跨模块复用后再提升。
