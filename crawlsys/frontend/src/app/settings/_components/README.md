# 系统设置局部组件

- `SettingsClient/`：五个职责页签、配置卡与 Provider 模型目录状态编排。
- `ConfigCard/`：单张卡片独立提交、字段错误和反馈状态。
- `forms/`：默认分析/转写模型、生成参数、视频分析、调度、RPC、代理与 Cleaner 表单，仅供系统设置页使用。
- `PlatformPolicyEditor/`：按平台维护评级与类型化过滤规则，并保护未保存草稿。
- `ProviderManager/`：维护模型提供商、同步模型目录并控制 Provider 与模型启停。

跨页面复用明确前不得提升到全局组件目录。
