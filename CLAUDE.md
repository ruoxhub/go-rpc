# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Rpc RPC - Go 语言实现，是一个多语言、分布式、网络拓扑无关的服务发布平台。这是 Java 版本 Rpc 的 Go 语言实现。

**核心特性：**
- 多语言支持（Go、Java 客户端）
- 分布式架构，支持多节点部署
- 网络拓扑无关，支持内网穿透
- WebSocket 长连接通信
- 分组管理和负载均衡
- QPS 流量控制
- 实时监控指标

## 常用命令

```bash
# 安装依赖
go mod tidy

# 构建所有
go build ./...

# 构建服务器
go build -o sekiro-server ./cmd/server

# 构建客户端
go build -o sekiro-client ./cmd/client

# 构建调用端
go build -o sekiro-invoker ./cmd/invoker

# 运行服务器 (默认端口 5612)
go run cmd/server/main.go -port 5612

# 运行客户端
go run cmd/client/main.go -server localhost:5612 -group test-group -client-id test-1

# 运行调用端
go run cmd/invoker/main.go -server localhost:5612 -group test-group -api test

# 运行所有测试
go test ./...

# 运行单个包的测试
go test ./pkg/protocol/...
go test ./pkg/server/api/...

# 运行单个测试
go test -run TestRpcPacket ./pkg/protocol/...
```

### Web 前端命令

```bash
cd web

# 安装依赖
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 代码检查
npm run lint
```

## 项目架构

```
sekiro-go/
├── cmd/
│   ├── server/           # 服务器端启动程序
│   ├── client/           # 客户端示例
│   └── invoker/          # 调用端示例
├── internal/
│   ├── config/           # YAML 配置管理
│   └── utils/
│       └── logger/       # zap 日志工具
├── pkg/
│   ├── client/           # 客户端 SDK (RpcClient, RpcInvoker)
│   ├── compress/         # 压缩算法 (Gzip, Snappy, None)
│   ├── database/         # 数据库连接管理 (GORM + PostgreSQL)
│   ├── eventbus/         # 事件总线
│   ├── model/            # 数据模型定义
│   ├── protocol/         # 通信协议层 (数据包编解码)
│   └── server/           # 服务器端核心
│       ├── api/          # HTTP API 处理器 (Gin 框架)
│       ├── client/       # 客户端管理 (分组、轮询、健康检查)
│       ├── detector/     # 协议检测器
│       ├── flow/         # 流量控制 (延迟退避)
│       ├── forwarder/    # 请求转发和超时管理
│       ├── handlers/     # Web 管理界面 handlers
│       ├── middleware/   # Gin 中间件
│       ├── router/       # 路由策略 (轮询、一致性 Hash)
│       └── websocket/    # WebSocket 消息处理
├── deploy/
│   └── postgres/         # 数据库部署脚本
├── web/                  # React 前端 (Vite + Ant Design)
└── sample/               # 示例代码
```

## 核心模块

### 服务器端 (pkg/server)

| 文件 | 说明 |
|------|------|
| **bootstrap.go** | 服务器启动入口，加载配置、初始化数据库、启动 HTTP/WebSocket |
| **api/handlers.go** | HTTP API 处理器 (`/business/invoke`, `/business/groupList`, `/business/clientQueue`, `/business/execjs`, `/business/cookie`, `/business/html`) |
| **api/http_server.go** | Gin HTTP 服务器封装 |
| **api/websocket.go** | WebSocket 升级配置 |
| **client/manager.go** | 客户端分组管理，支持轮询和指定客户端路由 |
| **client/client.go** | RpcClient 定义，包含健康检查机制 |
| **client/group.go** | 分组管理逻辑 |
| **router/strategy.go** | 三种路由策略（轮询、指定客户端、一致性 Hash） |
| **forwarder/timeout.go** | 请求超时管理和追踪 |
| **flow/backoff.go** | 空队列延迟退避机制 |
| **websocket/handler.go** | WebSocket 消息处理和客户端注册 |
| **detector/** | HTTP 协议检测器 |
| **alert/** | **告警评估引擎** |
| **handlers/** | Web 管理界面处理器 (user.go, group.go, metric.go, sysconfig.go, anonymous.go, **trace.go**, **alert.go**) |
| **middleware/cors.go** | CORS 中间件 |
| **middleware/auth.go** | Token 认证中间件，从 Authorization header 解析用户信息 |
| **handlers/login.go** | 登录 API 处理器 (`/rpc-api/user-info/login`) |

### 客户端 SDK (pkg/client)

| 文件 | 说明 |
|------|------|
| **client.go** | RpcClient - WebSocket 客户端，支持注册和请求处理 |
| **invoker.go** | RpcInvoker - 调用端，支持向服务器发送 RPC 调用 |

### 协议层 (pkg/protocol)

数据包格式：
```
[Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
```

包类型：
| 类型 | 值 | 说明 |
|------|-----|------|
| HEARTBEAT | 0 | 心跳包 |
| C_REGISTER | 16 | 客户端注册 |
| C_INVOKE_RESPONSE | 17 | 调用响应 |
| C_OFFLINE | 18 | 客户端下线 |
| S_INVOKE | 32 | 服务器调用 |
| I_INVOKE | 49 | 调用端请求 |

### 数据模型 (pkg/model)

| 模型 | 表名 | 说明 |
|------|------|------|
| UserInfo | user_info | 用户信息 |
| SysConfig | sys_config | 系统配置 |
| SysLog | sys_log | 系统日志 |
| ServerNode | server_node | 服务器节点 |
| GroupConfig | group_config | 分组配置 |
| GroupAction | group_actions | 分组 Action |
| GroupDevice | group_device | 分组设备 |
| MetricTag | metric_tag | 指标标签 |
| MetricMinute | metric_minute | 分钟级指标 |
| MetricHour | metric_hour | 小时级指标 |
| MetricDay | metric_day | 天级指标 |
| **AlertRule** | **alert_rule** | **告警规则** |
| **AlertHistory** | **alert_history** | **告警历史记录** |
| **TraceRecord** | **trace_record** | **调用链路追踪** |

### 新增数据模型说明 (监控和可观测性)

**告警规则 (AlertRule)**
```go
type AlertRule struct {
    ID          int64     // 主键 ID
    Name        string    // 规则名称（唯一）
    Description string    // 规则描述
    Group       string    // 分组名称，空表示全局规则
    API         string    // API 名称，空表示所有 API
    MetricName  string    // 指标名称，如 invoke.total, invoke.latency
    Operator    string    // 操作符：>, <, >=, <=, ==, !=
    Threshold   float64   // 阈值
    Window      int       // 时间窗口（分钟）
    WebhookURL  string    // Webhook URL
    Email       string    // 通知邮箱
    Enabled     bool      // 是否启用
    CreatedAt   time.Time // 创建时间
    UpdatedAt   time.Time // 更新时间
}
```

**告警历史 (AlertHistory)**
```go
type AlertHistory struct {
    ID           int64     // 主键 ID
    RuleID       int64     // 规则 ID
    RuleName     string    // 规则名称
    Group        string    // 分组名称
    API          string    // API 名称
    MetricName   string    // 指标名称
    CurrentValue float64   // 触发时的值
    Threshold    float64   // 阈值
    Operator     string    // 操作符
    Level        string    // 告警级别：INFO, WARNING, CRITICAL
    Notified     bool      // 是否已通知
    NotifyError  string    // 通知错误信息
    TriggeredAt  time.Time // 触发时间
    Message      string    // 告警消息
}
```

**调用链路追踪 (TraceRecord)**
```go
type TraceRecord struct {
    ID           int64     // 主键 ID
    TraceID      string    // 追踪 ID
    SpanID       string    // Span ID
    ParentSpanID string    // 父 Span ID
    Group        string    // 分组名称
    DeviceID     string    // 设备 ID
    API          string    // API 名称
    Caller       string    // 调用者
    StartTime    time.Time // 开始时间
    EndTime      time.Time // 结束时间
    DurationMs   int64     // 耗时（毫秒）
    Status       string    // 状态：SUCCESS, FAILURE
    ErrorMessage string    // 错误消息
    ExtraData    string    // 额外数据（JSON 格式）
}
```

## API 端点

### 核心 API

| 路径 | 方法 | 说明 |
|------|------|------|
| `/business/invoke` | POST/GET | RPC 调用 |
| `/business/groupList` | GET | 获取分组列表 |
| `/business/clientQueue` | GET | 获取客户端队列 |
| `/business/register` | WebSocket | 客户端注册 |
| `/business/execjs` | POST/GET | 执行 JS 代码 |
| `/business/cookie` | POST/GET | 获取 Cookie |
| `/business/html` | GET | 获取 HTML |

### Web 管理 API

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/users` | GET/POST/DELETE | 用户管理 |
| `/api/users/qps` | PUT | 更新用户 QPS |
| `/api/current` | GET | 获取当前用户 |
| `/api/current/password` | POST | 修改密码 |
| `/api/current/token/refresh` | POST | 刷新 Token |
| `/api/groups` | GET/POST/DELETE | 分组管理 |
| `/api/groups/:groupName` | GET | 获取分组详情 |
| `/api/groups/qps` | PUT | 更新分组 QPS |
| `/api/groups/:groupName/devices` | GET/DELETE | 设备管理 |
| `/api/groups/:groupName/actions` | GET | 获取分组 Actions |
| `/api/anonymous-groups` | GET | 匿名分组列表 |
| `/api/sysconfig` | GET/PUT | 系统配置 |
| `/api/sysconfig/nodes` | GET | 服务器节点 |
| `/api/sysconfig/logs` | GET | 系统日志 |
| `/api/metrics` | GET | 监控指标 |
| `/api/metrics/list` | GET | 指标列表 |
| `/api/metrics/dashboard` | GET | 仪表盘数据 |
| `/api/traces` | GET | 追踪列表 |
| `/api/traces/stats` | GET | 追踪统计 |
| `/api/traces/timeline` | GET | 追踪时间线 |
| `/api/traces/:traceId` | GET | 追踪详情 |
| `/api/traces/:traceId/extra` | GET | 追踪额外数据 |
| `/api/alerts/rules` | GET/POST/DELETE | 告警规则管理 |
| `/api/alerts/rules/:id` | GET/PUT/DELETE | 告警规则详情 |
| `/api/alerts/history` | GET | 告警历史 |

### 前端兼容 API (`/rpc-api` 前缀)

| 路径 | 方法 | 说明 |
|------|------|------|
| `/rpc-api/user-info/login` | POST | 用户登录 |
| `/rpc-api/user-info/userInfo` | GET | 获取当前用户信息 |
| `/rpc-api/user-info/changePassword` | POST | 修改密码 |
| `/rpc-api/user-info/refreshToken` | POST | 刷新 Token |
| `/rpc-api/user-info/logout` | POST | 用户登出 |
| `/rpc-api/frontend/listGroup` | GET | 分组列表 |
| `/rpc-api/system/systemNotice` | GET | 系统通知 |
| `/rpc-api/system/systemInfo` | GET | 系统信息 |
| `/rpc-api/groupConfig/create` | POST | 创建分组 |
| `/rpc-api/groupConfig/delete` | POST | 删除分组 |
| `/rpc-api/groupConfig/updateQps` | POST | 更新分组 QPS |
| `/rpc-api/groupClient/list` | GET | 设备列表 |
| `/rpc-api/groupClient/remove` | POST | 删除设备 |
| `/rpc-api/groupClient/forbidden` | POST | 禁用设备 |
| `/rpc-api/groupActions/list` | GET | Action 列表 |
| `/rpc-api/groupActions/create` | POST | 创建 Action |
| `/rpc-api/groupActions/delete` | POST | 删除 Action |
| `/rpc-api/traces/list` | GET | 追踪列表 |
| `/rpc-api/traces/detail` | GET | 追踪详情 |
| `/rpc-api/alert/rules` | GET/POST/DELETE | 告警规则 |
| `/rpc-api/alert/history` | GET | 告警历史 |

## 配置

### YAML 配置文件 (`config.yaml`)

```yaml
# 基础监听配置
BasicListen: ":5612"
Host: "0.0.0.0"
Port: 5612

# 默认超时 (秒)
DefaultTimeOut: 30

# 日志配置
CloseLog: false
CloseWebLog: false

# 运行模式 (debug/release)
Mode: release

# CORS 配置
Cors: true

# HTTPS 配置
HttpsServices:
  IsEnable: false
  HttpsListen: ":5643"
  PemPath: "certs/server.pem"
  KeyPath: "certs/server.key"

# 路由前缀替换 (反向代理用)
RouterReplace:
  IsEnable: false
  ReplaceRoute: "/sekiro"

# 数据库配置
Database:
  Host: "localhost"
  Port: 5432
  User: "postgres"
  Password: "postgres"
  DBName: "sekiro"
  SSLMode: "disable"
```

### 配置结构 (internal/config/config.go)

```go
type Config struct {
    BasicListen    string         // 监听地址
    Host           string         // 监听主机
    Port           int            // 监听端口
    HttpsServices  HttpsConfig    // HTTPS 配置
    DefaultTimeOut int            // 默认超时
    CloseLog       bool           // 关闭日志
    CloseWebLog    bool           // 关闭 Web 日志
    Mode           string         // 运行模式
    Cors           bool           // CORS 开关
    RouterReplace  RouterReplace  // 路由替换
    Database       DatabaseConfig // 数据库配置
}
```

### 启动参数

```bash
# 服务器启动参数
-port int        # 服务器端口 (默认 5612)
-host string     # 服务器主机 (默认 "0.0.0.0")
-debug           # 启用调试日志
-local-debug     # 启用本地调试模式
-c string        # 指定配置文件路径 (默认 "config.yaml")
```

## 数据库

### PostgreSQL 表结构

数据库迁移脚本位于 `deploy/postgres/migration.sql`

**主要表：**
- `user_info` - 用户信息
- `sys_config` - 系统配置
- `sys_log` - 系统日志
- `server_node` - 服务器节点
- `group_config` - 分组配置
- `group_actions` - 分组动作
- `group_device` - 分组设备
- `metric_minute/hour/day` - 监控指标
- `metric_tag` - 指标标签

### 数据库初始化

```go
// 从配置初始化数据库
database.InitFromConfig(
    config.Database.Host,
    config.Database.Port,
    config.Database.User,
    config.Database.Password,
    config.Database.DBName,
    config.Database.SSLMode,
)
```

## Web 前端

### 技术栈

- **框架**: React 18
- **构建工具**: Vite 5
- **UI 库**: Ant Design 5
- **路由**: React Router 6
- **HTTP 客户端**: Axios
- **工具库**: ahooks

### 前端页面

| 页面 | 路径 | 说明 |
|------|------|------|
| Login | `/login` | 登录页面 |
| Dashboard | `/` | 仪表盘（用户概览） |
| UserList | `/users` | 用户列表 |
| GroupList | `/groups` | 分组列表 |
| GroupDetail | `/groups/:name` | 分组详情（含设备、Action、监控标签页） |
| AnonymousGroup | `/anonymous` | 匿名分组 |
| Monitor | `/monitor` | 监控页面 |
| SystemPanel | `/system` | 系统面板 |
| **MonitorDashboard** | `/monitor/dashboard` | **监控仪表盘（调用趋势、延迟分析）** |
| **TraceList** | `/traces` | **追踪列表页面** |
| **TraceDetail** | `/traces/:traceId` | **追踪详情页面** |
| **AlertRules** | `/alerts/rules` | **告警规则管理页面** |
| **AlertHistory** | `/alerts/history` | **告警历史记录页面** |

### 前端核心组件

| 组件 | 路径 | 说明 |
|------|------|------|
| AuthGuard | `web/src/components/AuthGuard.jsx` | 路由守卫，检查 token 并重定向到登录页 |
| GroupMonitor | `web/src/components/GroupMonitor.jsx` | 监控图表组件（ECharts），展示调用趋势、QPS、设备状态 |
| GroupAction | `web/src/components/GroupAction.jsx` | Action 管理组件 |
| GroupDeviceList | `web/src/components/GroupDeviceList.jsx` | 设备列表组件 |
| **TraceTimeline** | `web/src/components/TraceTimeline.jsx` | **追踪时间线图组件** |
| **AlertRuleForm** | `web/src/components/AlertRuleForm.jsx` | **告警规则表单组件** |
| **AlertHistoryTable** | `web/src/components/AlertHistoryTable.jsx` | **告警历史表格组件** |

## 开发注意事项

### 技术栈

- **Web 框架**: Gin (HTTP + WebSocket)
- **WebSocket**: gorilla/websocket
- **ORM**: GORM v2
- **数据库**: PostgreSQL
- **日志**: uber-go/zap
- **配置**: gopkg.in/yaml.v3
- **压缩**: Gzip, Snappy

### 代码规范

- 使用 `github.com/mrh30000/go-rpc` 作为模块路径
- 错误处理使用 `fmt.Errorf` 和 `errors.Wrap`
- 日志使用 `logger.Infof/Errorf/Warningf`
- JSON 标签使用 `json:"field_name"`
- GORM 标签使用 `gorm:"column_name"`

### 健康检查机制

客户端 (RpcClient) 实现了健康检查：
- `MarkSuccess()` - 标记成功，重置失败计数
- `MarkFailure()` - 标记失败，累加计数
- 连续 3 次失败标记为不健康
- 路由时优先选择健康客户端

### 超时管理

- 默认超时 30 秒
- 使用 `forwarder.TimeoutManager` 管理请求追踪
- 支持自定义超时时间
- 超时后自动清理记录

### 中间件

- **CORS 中间件**: `pkg/server/middleware/cors.go`
- **路由替换中间件**: 支持反向代理前缀
- **认证中间件**: `pkg/server/middleware/auth.go` - 从 `Authorization: Bearer <token>` 解析用户信息到 context

### 认证流程

1. 用户登录 (`POST /rpc-api/user-info/login`) 验证用户名密码
2. 成功后返回 `apiToken` 和 `loginToken` 保存到 localStorage
3. 后续请求通过 `Authorization: Bearer <apiToken>` header 传递 token
4. 认证中间件解析 token 获取用户信息，存入 `c.Set("currentUserName", ...)` 和 `c.Set("userId", ...)`
5. Handlers 通过 `c.GetString("currentUserName")` 和 `c.GetInt("userId")` 获取当前用户

### 前端依赖

- **echarts-for-react**: React 图表库，用于 GroupMonitor 监控组件

## 部署

### 服务器部署

```bash
# 1. 编译
go build -o sekiro-server ./cmd/server

# 2. 配置 config.yaml
cp config.yaml.example config.yaml
# 编辑配置文件

# 3. 初始化数据库
psql -h localhost -U postgres -d sekiro < deploy/postgres/migration.sql

# 4. 创建初始用户（可选，使用默认密码）
# 用户名：ruoxing, 密码：mrx123456
# 可通过数据库直接插入或使用 GORM 脚本

# 5. 启动服务
./sekiro-server -c config.yaml
```

### 前端构建

```bash
cd web
npm install
npm run build
# 将 dist/ 目录部署到静态服务器或直接由 Gin 服务
```

### 静态文件服务

服务器启动时会自动从 `web/dist` 目录提供静态文件服务：
- 前端构建产物需放置在 `web/dist` 目录
- 支持 SPA 路由（NoRoute 重定向到 index.html）
- 生产环境可直接运行 `./sekiro-server` 访问 Web 界面

## 相关资源

- [Rpc Java 原版](https://github.com/yint-tech/sekiro)
- [Gin 框架文档](https://gin-gonic.com/)
- [GORM 文档](https://gorm.io/)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **go-rpc** (8671 symbols, 21866 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/go-rpc/context` | Codebase overview, check index freshness |
| `gitnexus://repo/go-rpc/clusters` | All functional areas |
| `gitnexus://repo/go-rpc/processes` | All execution flows |
| `gitnexus://repo/go-rpc/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
