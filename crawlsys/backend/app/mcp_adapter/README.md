# Crawler Content Analysis MCP

服务启动且 `mcp.enabled = true` 时，Streamable HTTP MCP 端点为 `http://<host>:<port>/mcp`。
本文示例统一使用 `http://mcp.example.test/mcp`；它不是可访问的生产地址，也不需要或包含密钥。

## 部署边界

- 此端点仅限可信内网/受控网络访问。它**没有应用层认证**，不得直接暴露到公网；请在网络层、反向代理或零信任网关实施访问控制。
- 在 `[mcp]` 中显式配置 `allowed_hosts`，禁止裸 `*` 主机通配；可填写具体主机名/IP，或明确的 `host:*` 端口通配。SDK 会拒绝不在该列表中的 Host。
- `allowed_origins` 默认为空，浏览器跨域请求默认不启用。确有浏览器客户端时，只加入具体受信 Origin；服务仅为这些 Origin 安装 CORS 中间件。
- 预签名 URL 由 MinIO 生成，含访问查询参数。不要把它写入日志、工单或文档；默认有效期为 15 分钟，可配置为 1–60 分钟。

```toml
[mcp]
enabled = true
allowed_hosts = ["mcp.example.test"]
allowed_origins = ["https://console.example.test"]
inline_object_limit_bytes = 10485760      # 10 MiB 默认内联读取/上传上限
inline_object_hard_limit_bytes = 52428800 # 50 MiB 服务硬上限
presigned_expiry_minutes = 15
```

`get_object_content` 和 `upload_base64_object` 的默认限制为 10 MiB，且无论配置如何都不能超过 50 MiB。Base64 会增加传输体积，客户端应优先对较大对象使用预签名 URL。

## 工具清单与写入边界

| 工具 | 作用 | 写入行为 |
| --- | --- | --- |
| `get_content` | 按平台和内容 ID 读取内容详情 | 只读 |
| `list_contents` | 游标分页查询内容摘要 | 只读 |
| `get_user` | 按平台和用户 ID 读取用户详情 | 只读 |
| `list_users` | 按平台/用户名过滤，游标分页查询用户摘要 | 只读 |
| `get_analysis_result` | 读取单条视频分析结果 | 只读 |
| `list_analysis_results` | 游标分页查询分析结果摘要 | 只读 |
| `list_buckets` | 列出存储桶 | 只读 |
| `create_bucket` | 幂等创建存储桶 | 创建 |
| `list_objects` | 游标分页列出对象 | 只读 |
| `stat_object` | 读取对象元数据 | 只读 |
| `get_object_download_url` | 为已存在对象创建临时下载 URL | 只读（生成临时凭据） |
| `get_object_content` | 以内联 Base64 读取小对象 | 只读 |
| `create_upload_url` | 为已存在存储桶创建临时上传 URL | 生成临时凭据 |
| `upload_base64_object` | 上传或覆盖一个受限大小的对象 | 写入/覆盖 |

适配层**不提供任何删除工具**：没有删除对象、删除存储桶或删除内容/分析结果的 MCP 操作。`upload_base64_object` 可以覆盖同名对象，调用前应自行确认对象名和保留策略。

## 客户端接入

先从可信网络验证端点可达，再按客户端连接。以下命令均不发送密钥。

### MCP Inspector

使用官方 Inspector 启动本地检查器：

```bash
npx @modelcontextprotocol/inspector
```

在 Inspector 界面选择 Streamable HTTP，并填写：

```text
http://mcp.example.test/mcp
```

### Codex CLI

本机 CLI 的 `codex mcp add --help` 显示 HTTP 服务使用 `--url`：

```bash
codex mcp add crawler-content-analysis --url http://mcp.example.test/mcp
```

### Claude Code

本机 CLI 的 `claude mcp add --help` 显示 HTTP transport 使用 `--transport http`：

```bash
claude mcp add --transport http crawler-content-analysis http://mcp.example.test/mcp
```

连接成功后先调用只读工具确认访问范围；上传、创建存储桶和预签名上传 URL 应仅授予确有需要的受控客户端。
