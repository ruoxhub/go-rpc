# ProviderManager

设置页私有的模型提供商管理区，负责 Provider 创建、编辑、启停、删除，以及远端模型同步和模型启停。

- `index.tsx`：Provider 列表、当前选择和异步操作状态边界。
- `components/ProviderForm/`：创建与编辑表单，通过五项下拉框选择请求格式；API Key 编辑时始终留空，请求格式或 Base URL authority 变化时要求重新输入。
- `components/ModelList/`：模型目录、远端可用状态和启停操作。

异步操作保持按钮文案不变，以 `Loader2`、禁用状态和 `aria-busy` 提供反馈；列表加载使用骨架屏。删除期间以请求发起时捕获的 Provider 作为确认上下文，并锁定新增、列表切换和相关操作，完成后再选择剩余 Provider。所有表单字段均有可关联的标签与错误信息，危险删除复用全局确认弹窗，移动端交互使用 `touch-target` 保证触控尺寸。

本目录仅服务系统设置页；确认跨页面复用后再提取到中立业务目录。

Provider 表单只提交名称、请求格式、Base URL 和密钥；LiteLLM 前缀由后端根据请求格式派生，前端不展示或提交该字段。

此区域没有套用 `ConfigCard`：它同时管理 Provider 列表、编辑表单、模型目录和多种独立操作，不符合 `ConfigCard` 的单表单单提交接口。实现仍复用设置页字段样式、`Loader2` 与全局 `ConfirmDialog`，保持控件和反馈方式一致。
