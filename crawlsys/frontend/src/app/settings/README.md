# 系统设置

服务端页面一次读取运行时配置与 Provider 模型目录，`SettingsClient` 按职责切换页签；每张配置卡独立维护草稿、保存和错误状态。AI 页签维护模型提供商与默认模型，媒体页签维护视频分析配置，两者互不耦合。`utils/` 封装本模块 API 与类型，`ProviderManager/` 维护 Provider、同步模型目录及启停状态，`PlatformPolicyEditor/` 按平台维护评级和类型化 AND 过滤条件，并保护未保存草稿。

Provider API Key 和代理 URL 不回显原值；编辑 Provider 时密钥输入留空表示保留当前值，切换请求格式或 Base URL authority（scheme、hostname、port）时必须重新输入密钥，只有路径变化时无需重输。前端只提交 Provider 名称、请求格式、Base URL 和密钥，LiteLLM 前缀由后端按请求格式派生并仅作为诊断字段返回。默认分析/转写模型保存数据库模型 ID；历史模型不可用时仍显示其名称和不可用状态，用户明确重选前不会静默覆盖。

Cleaner 的平台评级与过滤策略使用独立平台配置，不包含在 Cleaner 全局响应中。`poll_interval` 与 `watermark_key` 当前仅为初始化兼容字段，页面按后端 `inactive_fields` 禁用并标注“当前未接入”。
