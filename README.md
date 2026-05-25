# Rpc RPC - Go 语言实现

[![Go Version](https://img.shields.io/badge/go-1.25-blue.svg)](https://golang.org)
[![License](https://img.shields.io/badge/license-Apache2.0-green.svg)](LICENSE)

SEKIRO 是一个多语言、分布式、网络拓扑无关的服务发布平台。本仓库是 Go 语言实现，相比 Java 版本额外内置了监控指标、告警规则、调用链路追踪和 Web 管理后台。

## 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [核心功能](#核心功能)
- [SDK 使用](#sdk-使用)
- [API 接口](#api-接口)
- [前端管理界面](#前端管理界面)
- [协议说明](#协议说明)
- [路由策略](#路由策略)
- [测试](#测试)
- [开发指南](#开发指南)
- [与 Java 版本对比](#与-java-版本对比)
- [常见问题](#常见问题)

## 快速开始

### 路径 A：Docker Compose（推荐）

适合快速验证或部署。

```bash
# 1. 准备 PostgreSQL（仓库中的 docker-compose.yaml 默认未启用内置 postgres，
#    取消注释或自行准备 PostgreSQL 实例后填写连接信息到 config.yaml）

# 2. 准备配置文件
cp config.yaml.example config.yaml
# 编辑 Database 段指向可用的 PostgreSQL

# 3. 启动
docker compose up -d

# 4. 访问 Web 管理后台
# http://localhost:5612  默认账号：admin / admin123
```

### 路径 B：源码运行

适合本地开发。

```bash
# 1. 安装依赖
go mod tidy

# 2. 准备数据库
psql -U postgres -f deploy/postgres/migration.sql

# 3. 构建前端（go build 需要 web/dist 存在）
cd web && npm install && npm run build && cd ..

# 4. 配置文件
cp config.yaml.example config.yaml   # 修改 Database 段

# 5. 启动服务器（默认端口 5612）
go run main.go
# 或
go build -o rpcserver . && ./rpcserver

# 6. 访问 http://localhost:5612  账号 admin / admin123
```

### 启动参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-port` | 服务器端口（覆盖 config.yaml） | 0（用配置文件） |
| `-host` | 服务器主机 | 空（用配置文件） |
| `-debug` | 启用调试日志 | false |
| `-local-debug` | 启用本地调试模式 | false |
| `-c` | 配置文件路径 | `config.yaml` |

### 验证服务

```bash
# 健康检查
curl http://localhost:5612/health

# 获取分组列表
curl http://localhost:5612/business/groupList

# 发起一次 RPC 调用
curl -X POST http://localhost:5612/business/invoke \
  -H "Content-Type: application/json" \
  -d '{"group":"test-group","action":"test","params":{"key":"value"}}'
```

> 默认管理员密码 `admin123` 仅用于开发环境，生产环境请第一时间通过 `/api/current/password` 修改。

## 配置说明

完整示例见 `config.yaml.example`，关键字段如下：

```yaml
# 监听
BasicListen: ":5612"        # 监听地址（与 Host/Port 二选一）
Host: "0.0.0.0"
Port: 5612
DefaultTimeOut: 30          # RPC 默认超时（秒）

# 运行模式
Mode: release               # debug | release
Cors: true                  # 启用 CORS
CloseLog: false
CloseWebLog: false

# 模块开关（DB-less 部署时实用）
DisableWebAdmin: false      # 关闭 /api 路由和 Web 后台
DisableMetrics:  false      # 关闭指标采集
DisableAlert:    false      # 关闭告警引擎
DisableDatabase: false      # 跳过 DB 初始化（同时关闭依赖 DB 的路由）

# HTTPS（可选）
HttpsServices:
  IsEnable: false
  HttpsListen: ":5643"
  PemPath: "certs/server.pem"
  KeyPath: "certs/server.key"

# 反向代理前缀剥离
RouterReplace:
  IsEnable: false
  ReplaceRoute: "/sekiro"

# 数据库（DisableDatabase=false 时必填）
Database:
  Host: "localhost"
  Port: 5432
  User: "postgres"
  Password: "postgres"
  DBName: "sekiro"
  SSLMode: "disable"

# 告警 SMTP（DisableAlert=false 时生效）
Alert:
  SMTP:
    Host: "smtp.example.com"
    Port: 587
    Username: "alert@example.com"
    Password: "password"
    From:     "alert@example.com"
    UseTLS:   true
```

字段定义见 `internal/config/config.go`。

## 项目结构

```
go-rpc/
├── main.go                     # 服务器入口
├── config.yaml.example         # 配置模板
├── docker-compose.yaml         # Docker 编排
├── Dockerfile
├── deploy/postgres/migration.sql
├── docs/                       # 设计文档（PRD、改进计划等）
├── internal/
│   ├── config/                 # YAML 配置加载
│   └── utils/logger/           # zap 日志封装
├── pkg/
│   ├── client/                 # 客户端 SDK（RpcClient + RpcInvoker）
│   ├── compress/               # Gzip / Snappy / None
│   ├── database/               # GORM 连接、迁移、repository
│   ├── eventbus/               # 进程内事件总线
│   ├── model/                  # GORM 数据模型
│   ├── protocol/               # 二进制包编解码
│   ├── server/
│   │   ├── bootstrap.go        # 启动入口、路由注册
│   │   ├── alert/              # 告警评估引擎
│   │   ├── api/                # /business、/v1 处理器
│   │   ├── client/             # 客户端管理、健康检查
│   │   ├── config/             # 运行时配置服务
│   │   ├── detector/           # 协议自动识别
│   │   ├── flow/               # 流量控制、限流退避
│   │   ├── forwarder/          # 调用超时管理
│   │   ├── handlers/           # /api、/rpc-api 处理器
│   │   ├── metrics/            # 指标采集
│   │   ├── middleware/         # 认证、CORS、限流、追踪
│   │   ├── router/             # 路由策略
│   │   ├── transport/          # 传输层抽象
│   │   └── websocket/          # WebSocket 消息处理
│   └── utils/
├── web/                        # React 管理后台（//go:embed dist）
└── sample/                     # 多语言示例（go、java、python、frida、xposed 等）
```

## 核心功能

| 类别 | 功能 |
|------|------|
| 通信 | 二进制协议 + WebSocket 双协议；自动识别；Gzip/Snappy 压缩 |
| 客户端 | 注册、注销、心跳保活、连续 3 次失败标记不健康 |
| 路由 | 轮询、指定客户端、一致性 Hash 三种策略 |
| 安全 | Bearer Token 认证；管理员/普通用户分级；分组绑定用户 |
| 限流 | 用户与 IP 维度的 QPS 限流（运行时可调） |
| 监控 | 分钟/小时/天三档指标聚合（可选关闭） |
| 追踪 | 完整的调用链路记录与详情查询 |
| 告警 | 规则评估引擎，支持 SMTP/Webhook 通知 |
| 部署 | 支持反向代理前缀剥离、HTTPS、DB-less 模式 |
| 管理 | React + Ant Design 后台，`//go:embed` 进二进制 |

## SDK 使用

> 本仓库只发布 server 可执行文件。客户端/调用端以 SDK 形式提供（`pkg/client`），完整示例见 `sample/go/sekio/`。

### 客户端：注册并处理请求

```go
package main

import (
    "log"
    "github.com/mrh30000/go-rpc/pkg/client"
)

func main() {
    c := client.NewRpcClient("my-group", "my-client-id", "localhost", 5612)
    if err := c.Start(); err != nil {
        log.Fatal(err)
    }

    c.Register(func(request []byte) ([]byte, error) {
        return []byte(`{"result":"success"}`), nil
    })

    select {}
}
```

### 调用端：发起 RPC 调用

```go
package main

import (
    "fmt"
    "log"
    "github.com/mrh30000/go-rpc/pkg/client"
)

func main() {
    invoker := client.NewRpcInvoker([]string{"localhost:5612"})
    defer invoker.Destroy()

    resp, err := invoker.Invoke(&client.InvokeRequest{
        Group:   "my-group",
        Api:     "my-api",
        Params:  map[string]interface{}{"key": "value"},
        Timeout: 30,
    })
    if err != nil {
        log.Fatal(err)
    }

    fmt.Printf("code=%d message=%s data=%v\n", resp.Code, resp.Message, resp.Data)
}
```

### 主要 API

**RpcClient**

| 方法 | 说明 |
|------|------|
| `NewRpcClient(group, clientID, host, port)` | 创建客户端 |
| `Start() error` | 连接并启动消息循环 |
| `Register(handler)` | 注册请求处理器 |
| `Destroy(waitSeconds)` | 优雅关闭 |

**RpcInvoker**

| 方法 | 说明 |
|------|------|
| `NewRpcInvoker(serverList)` | 创建调用端 |
| `NewRpcInvokerWithToken(token, serverList)` | 带 API Token 的调用端 |
| `Invoke(req) (*InvokeResponse, error)` | 发起调用 |
| `Destroy()` | 释放连接 |

## API 接口

### 公开接口

| 路径 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/business/groupList` | GET | 分组列表 |
| `/business/clientQueue` | GET | 分组下客户端队列 |
| `/business/invoke` | GET/POST/Any | RPC 调用 |
| `/business/register` | GET → WebSocket | 客户端注册并升级到 WebSocket |
| `/business/execjs` | GET/POST | 执行 JS 代码 |
| `/business/cookie` | GET/POST | 获取 Cookie |
| `/business/html` | GET | 获取 HTML |
| `/v1/chat/completions` | POST | OpenAI 兼容接口 |

### 用户与前端兼容接口（`/rpc-api`）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/rpc-api/user-info/login` | POST | 用户登录 |
| `/rpc-api/user-info/register` | POST | 用户注册 |
| `/rpc-api/user-info/userInfo` | GET | 当前用户信息 |
| `/rpc-api/system/systemNotice` | GET | 系统公告 |
| `/rpc-api/system/systemInfo` | GET | 系统信息 |
| `/rpc-api/frontend/listGroup` | GET | 前端分组列表 |
| `/rpc-api/frontend/anonymousGroupList` | GET | 匿名分组列表 |
| `/rpc-api/frontend/groupDetail` | GET | 分组详情 |

### 管理后台接口（`/api`，需认证）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/users` | GET/POST/DELETE | 用户管理（仅管理员） |
| `/api/users/qps` | PUT | 调整用户 QPS |
| `/api/current` | GET | 当前用户 |
| `/api/current/password` | POST | 修改密码 |
| `/api/current/token/refresh` | POST | 刷新 Token |
| `/api/groups` | GET/POST/DELETE | 分组管理 |
| `/api/groups/qps` | PUT | 调整分组 QPS |
| `/api/groups/:groupName` | GET | 分组详情 |
| `/api/groups/:groupName/devices` | GET | 设备列表 |
| `/api/groups/devices` | DELETE | 删除设备 |
| `/api/groups/devices/disable` | PUT | 禁用设备 |
| `/api/groups/:groupName/actions` | GET | 动作列表 |
| `/api/groups/actions` | POST/DELETE | 添加/删除动作 |
| `/api/anonymous-groups` | GET/DELETE | 匿名分组 |
| `/api/anonymous-groups/convert` | POST | 转为正式分组 |
| `/api/sysconfig` | GET/PUT | 系统配置（仅管理员） |
| `/api/sysconfig/nodes` | GET | 服务节点 |
| `/api/sysconfig/logs` | GET | 系统日志 |
| `/api/sysconfig/app-logs` | GET | 应用日志 |
| `/api/metrics` | GET | 监控指标 |
| `/api/metrics/list` | GET | 指标列表 |
| `/api/metrics/dashboard` | GET | 仪表盘 |
| `/api/metrics/latency/percentiles` | GET | 延迟分位 |
| `/api/traces` | GET | 追踪列表 |
| `/api/traces/stats` | GET | 追踪统计 |
| `/api/traces/timeline` | GET | 追踪时间线 |
| `/api/traces/:traceId` | GET | 追踪详情 |
| `/api/traces/:traceId/extra` | GET | 追踪额外数据 |
| `/api/alerts/rules` | GET/POST | 告警规则（仅管理员） |
| `/api/alerts/rules/:id` | GET/PUT/DELETE | 规则详情 |
| `/api/alerts/history` | GET | 告警历史 |

### 响应格式

```json
// 成功
{ "status": 0, "message": "success", "data": { ... } }

// 失败
{ "status": -1, "message": "error message" }
```

## 前端管理界面

基于 React 18 + Vite 5 + Ant Design 5，构建产物 `web/dist/` 通过 `//go:embed dist` 嵌入二进制。

### 功能模块

| 模块 | 说明 |
|------|------|
| 我的 | API Token、修改密码 |
| 分组列表 | 创建/删除分组、配置 QPS |
| 匿名分组 | 查看与管理匿名分组 |
| 监控指标 | 业务大盘、调用趋势、延迟分位、MQL 编辑器 |
| 调用追踪 | 链路列表、时间线、单次详情 |
| 告警管理 | 规则配置与告警历史 |
| 账号列表 | 用户管理、QPS 配额（仅管理员） |
| 系统面板 | 系统配置、节点、日志（仅管理员） |

### 前端开发

```bash
cd web
npm install
npm run dev    # 端口 3000
```

> Vite 代理目标为 `localhost:5613`（见 `web/vite.config.js`），但服务器默认监听 `5612`。开发时启动服务器加 `-port 5613`，或修改代理配置。

### 前端构建

```bash
cd web && npm run build      # 输出到 web/dist/
```

构建完成后，下次执行 `go build` 会自动嵌入。

## 协议说明

### 数据包格式

```
[Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
```

| 字段 | 大小 | 说明 |
|------|------|------|
| Magic | 8B | 魔数 |
| Length | 4B | 包体长度 |
| Type | 1B | 包类型 |
| SerialNumber | 4B | 序列号 |
| Headers | 可变 | 头部键值对 |
| Data | 可变 | 数据载荷 |

### 包类型（`pkg/protocol/packet_type.go`）

| 类型 | 值 | 方向 | 说明 |
|------|----|------|------|
| HEARTBEAT | 0 | 双向 | 心跳 |
| C_REGISTER | 16 | C→S | 客户端注册 |
| C_INVOKE_RESPONSE | 17 | C→S | 调用响应 |
| C_OFFLINE | 18 | C→S | 客户端下线 |
| C_CMD_RESPONSE | 19 | C→S | 命令响应 |
| C_INVOKE_STREAM_CLOSE | 20 | C→S | 流式调用关闭 |
| S_INVOKE | 32 | S→C | 服务端调用 |
| S_CMD | 33 | S→C | 服务端命令 |
| S_OFFLINE_RESPONSE | 34 | S→C | 下线响应 |
| S_INVOKE_RESPONSE | 35 | S→C | 调用应答 |
| S_INVOKE_CONNECTED | 36 | S→C | 调用建立 |
| I_CONNECT | 48 | I→S | 调用端接入 |
| I_INVOKE | 49 | I→S | 调用端请求 |

### WebSocket 消息

```jsonc
// 请求
{ "type":"invoke","group":"my-group","clientId":"client-1",
  "action":"my-api","params":{"key":"value"},"__sekiro_seq__":"seq-id" }

// 响应
{ "type":"invoke_response","status":0,
  "data":{"result":"success"},"__sekiro_seq__":"seq-id" }

// 心跳
{ "type":"heartbeat","timestamp":1234567890 }
```

## 路由策略

服务器对同一分组下的多个客户端支持三种路由策略：

```go
// 1. 轮询（默认）：不指定 ClientID
invoker.Invoke(&client.InvokeRequest{Group: "g", Api: "a"})

// 2. 指定客户端
invoker.Invoke(&client.InvokeRequest{Group: "g", ClientID: "node-1", Api: "a"})

// 3. 一致性 Hash：URL 加 constantInvoke=true
// curl "http://localhost:5612/business/invoke?group=g&action=a&constantInvoke=true"
```

健康检查会优先把请求路由到健康客户端（连续 3 次失败标记不健康）。

## 测试

```bash
# 全量测试
go test ./...

# 带竞态检测
go test -race ./...

# 单包测试
go test ./pkg/protocol/...
go test ./pkg/server/...

# 单测试
go test -run TestRpcPacket ./pkg/protocol/...
```

## 开发指南

### 添加新的 `/api` 处理器

1. 在 `pkg/server/handlers/` 新建处理器文件
2. 在 `pkg/server/handlers/routes.go` 的 `SetupWebRoutes` 内注册路由
3. 如需新仓储，扩展 `Deps` 与 `bootstrap.go` 的注入

### 添加 `/business` 端点

直接在 `pkg/server/bootstrap.go::registerRoutes` 的 `business` 分组中追加，并在 `pkg/server/api/` 实现 handler。

### 添加新前端页面

1. `web/src/pages/` 添加页面组件
2. `web/src/App.jsx` 注册路由
3. `web/src/layouts/Layout.jsx` 添加菜单项

### 编码约定

- 模块路径：`github.com/mrh30000/go-rpc`
- 错误处理：`fmt.Errorf("...: %w", err)`
- 日志：`logger.Infof / Errorf / Warningf`
- GORM 标签：`gorm:"column:xxx"`，JSON 标签 `json:"field"`

## 与 Java 版本对比

| 维度 | Java 版本 | Go 版本 |
|------|-----------|---------|
| 网络 | Netty | gorilla/websocket + Gin |
| JSON | FastJSON | encoding/json |
| 压缩 | Java Gzip/Snappy | compress/gzip + golang/snappy |
| 日志 | Logback | uber-go/zap |
| 并发 | 线程池 | goroutine + channel |
| 配置 | properties | yaml.v3 |
| 数据库 | MySQL/自建 | PostgreSQL + GORM |
| 后台 | JSP/Vue | React + Ant Design（嵌入二进制） |
| 监控告警 | 无 | 内置指标 + 告警规则 |
| 调用追踪 | 无 | 内置链路追踪 |

## 常见问题

**Q：`go build` 报 `pattern dist: no matching files found`？**
先构建前端：`cd web && npm install && npm run build`。`web/embed.go` 通过 `//go:embed dist` 嵌入构建产物。

**Q：能否不依赖 PostgreSQL 运行？**
可以。`config.yaml` 设 `DisableDatabase: true`，依赖数据库的路由（用户/分组/告警/追踪等）会自动关闭，仅保留 `/business/*` 等核心 RPC 路径。

**Q：仅当作 RPC 引擎，不要 Web 后台怎么办？**
设 `DisableWebAdmin: true`，所有 `/api` 路由和静态文件都不会注册。

**Q：前端开发代理不通？**
`web/vite.config.js` 默认代理目标为 `localhost:5613`，与服务器默认 `5612` 不一致。要么改 vite 配置，要么用 `go run main.go -port 5613` 启动后端。

**Q：客户端断线怎么处理？**
服务器自动从队列移除离线客户端。客户端连续 3 次心跳失败标记为不健康，路由会优先选择健康节点。重连后自动重新注册。

**Q：如何修改默认管理员密码？**
登录后调用 `POST /api/current/password`，或在 Web 后台「我的」页面修改。

**Q：生产部署清单？**
- `Mode: release`
- 启用 HTTPS（`HttpsServices.IsEnable: true`）
- 反向代理前缀使用 `RouterReplace`
- 配置 `Alert.SMTP` 接收告警
- PostgreSQL 定期备份；首次启动后立即修改 admin 密码

## 相关资源

- [SEKIRO Java 原版](https://github.com/yint-tech/sekiro)
- [Gin](https://gin-gonic.com/) · [GORM](https://gorm.io/) · [gorilla/websocket](https://github.com/gorilla/websocket)
- 设计文档：`docs/`

## 许可证

Apache 2.0，与原 SEKIRO 项目保持一致。
