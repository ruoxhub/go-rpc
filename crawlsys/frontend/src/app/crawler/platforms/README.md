# 平台管理

- `page.tsx`：服务端首屏获取平台列表，并通过 URL 控制是否包含已删除平台。
- `new/page.tsx`：新建平台入口。
- `[id]/edit/page.tsx`：服务端获取平台详情并渲染编辑入口。
- `_components/PlatformForm/`：创建与编辑共享的客户端表单。
- `_components/PlatformActions/`：删除、恢复及确认反馈交互。

平台请求与错误处理复用 `src/utils/crawler`；通用页面、表单和确认组件复用 crawler 局部共享组件。
