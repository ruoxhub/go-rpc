# Crawler 工具

本目录提供跨 Crawler 管理页面复用的低业务耦合能力。

- `crawler-api.ts`：统一浏览器与服务端请求基址、JSON 解码、Cron 预览、任务立即执行/启停操作及稳定错误映射；`CrawlerApiError` 可安全保留 Parser 的稳定错误码、白名单详情与限流重试秒数。非 JSON 或不可解析响应会带上 HTTP 状态码与截断到 200 字符的 `responseSnippet`，用于区分后端错误、反向代理错误页和被占用的端口。
- `crawler-types.ts`：API 客户端共享错误响应类型，以及平台、接口、关键词、结构化 `schedule` / `retry_policy` 与任务运行状态等 crawler 跨页面 API 数据模型；兼容期继续保留旧 `loop_*` 字段；`TASK_PRIORITIES`、`TaskPriority` 和 `isTaskPriority` 定义任务优先级 wire type 与守卫。Action schema 与 LLM metadata 类型已迁至 `src/api/task-metadata/`。
- `crawler-api.test.ts`：客户端请求与错误契约测试，包含任务优先级更新 PATCH 请求契约。

浏览器请求同源 `/api/crawler`；服务端渲染默认连接 `http://127.0.0.1:8081/api/crawler`，并允许用 `CRAWLER_API_BASE_URL` 覆盖。生产环境必须由反向代理保留同源 `/api/*` 契约，完整联调方式见 `frontend/README.md`。

服务端默认后端地址写死环回地址，若 `127.0.0.1:<后端端口>` 被其他进程（例如 mitmproxy 的透明代理）抢占，服务端请求会命中抢占者并收到非 JSON 响应，页面表现为 `invalid-response`。排查时用 `netstat -ano -p tcp | findstr :<端口>` 确认监听进程，必要时释放端口或改用未被占用的端口并设置 `CRAWLER_API_BASE_URL`。

新增规则：仅放多个 Crawler 页面共同使用的纯类型或请求基础设施；页面专属逻辑留在对应页面目录。
