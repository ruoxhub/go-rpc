# crawler 局部共享组件

本目录只承载 crawler 下平台、动作、任务与关键词模块共同使用的页面骨架和基础交互，不作为全局组件入口。

## 组件

- `PageHeader/`：页面标题、说明与操作区。
- `DataTable/`：轻量泛型数据表格与空状态。
- `FilterBar/`：筛选控件与操作区容器。
- `FormField/`：表单标签、提示和错误关联。
- `SubmitButton/`：提交及加载状态按钮；可通过 `loaderClassName` 为特定流程设置加载图标的动效降级。
- `Feedback/`：成功、错误、警告和信息反馈。

## 边界

组件仅沉淀四个 crawler 模块已经共享的结构。业务请求、业务状态和模块专属展示留在各自页面目录；跨页面基础控件位于 `app/_components`。
