# Frontend

Next.js 管理前端，默认连接本仓库 FastAPI JSON API。

## 联合启动

先启动后端（默认 `127.0.0.1:8081`）：

```bash
cd backend
python main.py
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

服务端渲染默认请求 `http://127.0.0.1:8081/api/crawler`。可用 `CRAWLER_API_BASE_URL` 覆盖完整 crawler API 基址，例如 `http://api.example.test/api/crawler`；浏览器始终请求同源 `/api/crawler`，开发环境由 Next.js 自动转发到 `http://127.0.0.1:8081`。

页面报 `采集服务返回了无法识别的响应（<状态码>）` 说明前端拿到的是非 JSON 响应，常见原因是后端端口被其他进程抢占（反向代理、抓包工具的透明代理等）。用 `netstat -ano -p tcp | findstr :8081` 确认监听进程：若 `127.0.0.1:8081` 与 `0.0.0.0:8081` 分属不同 PID，则环回地址已被抢占，应释放该端口、改用未被占用的端口，或临时用 `CRAWLER_API_BASE_URL` 指向可达地址。

生产环境必须由反向代理将前端同源 `/api/*` 转发到 FastAPI，并保留状态码、JSON `content-type` 和 `/api/crawler/*` 路径契约。不要把仅服务端可达的内部地址暴露给浏览器。

界面语言通过 `NEXT_PUBLIC_APP_LOCALE=zh-CN|en` 在构建或运行时选择，默认 `zh-CN`。

## 系统设置

桌面侧栏与移动端菜单均可进入 `/settings`。页面按“AI 与媒体、调度与调用、网络、清洗”分区，每张配置卡独立保存；平台清洗策略可按平台分别维护评级与 AND 过滤条件。

系统设置通过同源 `/api/settings` 读写后端运行时配置。LLM API Key 和代理 URL 不会回显原值：页面仅显示是否已配置及安全摘要，秘密字段留空保存会保留现值。
