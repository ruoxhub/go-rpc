# 国际化

本目录提供服务端组件与客户端组件共用的静态国际化能力，不维护语言路由或客户端全局状态。

- `index.ts`：导出 typed `MessageKey`、`t()`、当前语言与支持语言。
- `messages/zh-CN.ts`：默认中文消息，也是消息键的类型来源。
- `messages/en.ts`：英文消息，使用 TypeScript 强制与中文键完整一致。

通过 `NEXT_PUBLIC_APP_LOCALE=zh-CN|en` 在构建或运行时选择语言，未配置或值不受支持时回退到 `zh-CN`。新增用户可见文案必须同步更新两个消息文件，并通过 `t(key)` 读取；不得手动拼接语言路由前缀。
