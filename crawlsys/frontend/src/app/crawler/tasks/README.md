# 任务管理

- `page.tsx`：任务列表、优先级本地化 badge、URL 平台筛选和批量操作入口。
- `new/`、`[id]/edit/`：服务端首屏数据加载的独立复杂表单页面。
- `_components/TaskForm/`：表单状态、提交与元数据联动编排。
  - `index.tsx`：受控表单入口与平台、接口选择；视频分析任务可覆盖系统默认分析模型。
  - `components/SinkConfigFields/index.tsx`：结果写回模式与字段设置。
  - `hooks/useTaskMetadata.ts`：Schema、表字段加载及乱序响应隔离。
  - `utils/taskForm.ts`：表单初值、参数映射序列化和 DTO 组装。
- `_components/TaskActions/`：单项及批量状态操作与删除确认。
  - `index.tsx`：单项启动、暂停、删除和上下文反馈。
  - `BatchTaskActions.tsx`：按当前平台筛选批量启动或暂停。
- `_components/TaskPriorityControl/index.tsx`：原子 PATCH 调整优先级；运行中任务可调整，失败时回滚并显示后端错误。
- `_utils/taskPriority.ts`：优先级本地化标签与主题 badge 样式映射。
- `_components/SourceConfigFields/`：表字段和参数映射编辑。
  - `index.tsx`：受控数据源字段，不保留换表前的列选择。
- `_components/LoopSettings/`：循环执行设置。
  - `index.tsx`：循环开关和 NumberInput 间隔输入。

视频分析任务的模型选项来自任务元数据接口，仅展示当前可用模型；不选择时使用系统默认模型。编辑历史任务时若原模型不可用，表单会阻止误保存，直到用户明确选择可用模型或恢复系统默认。

组件仅服务任务模块；确认跨模块复用后再提升。
