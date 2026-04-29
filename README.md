# Rpc RPC - Go 语言实现

[![Go Version](https://img.shields.io/badge/go-1.25.0-blue.svg)](https://golang.org)
[![License](https://img.shields.io/badge/license-Apache2.0-green.svg)](LICENSE)

SEKIRO 是一个多语言、分布式、网络拓扑无关的服务发布平台。

这是 Java 版本 Rpc 的 Go 语言实现，支持 WebSocket 通信、HTTP API、前端管理界面、路由负载均衡、监控告警、调用追踪等核心功能。

## 目录

- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [核心功能](#核心功能)
- [SDK 使用](#sdk-使用)
- [API 接口](#api-接口)
- [前端管理界面](#前端管理界面)
- [协议说明](#协议说明)
- [路由策略](#路由策略)
- [测试](#测试)
- [与 Java 版本对比](#与-java-版本对比)
- [常见问题](#常见问题)

## 项目结构

```
sekiro-go/
├── cmd/                      # 可执行程序入口
│   ├── server/               # 服务器端启动程序
│   │   └── main.go
│   ├── client/               # 客户端示例
│   │   └── main.go
│   └── invoker/              # 调用端示例
│       └── main.go
├── pkg/                      # 核心包
│   ├── client/               # 客户端 SDK (RpcClient, RpcInvoker)
│   │   ├── client.go
│   │   └── invoker.go
│   ├── compress/             # 压缩算法 (Gzip, Snappy, None)
│   │   ├── gzip.go
│   │   ├── snappy.go
│   │   ├── none.go
│   │   └── manager.go
│   ├── database/             # PostgreSQL 数据库连接与迁移
│   ├── eventbus/             # 事件总线
│   ├── model/                # GORM 数据模型
│   ├── protocol/             # 通信协议层 (数据包编解码)
│   │   ├── packet.go
│   │   └── packet_type.go
│   └── server/               # 服务器端核心
│       ├── api/              # HTTP API 处理器 (Gin 框架)
│       ├── client/           # 客户端管理 (分组、轮询)
│       ├── config/           # 运行时配置服务
│       ├── detector/         # 协议检测器
│       ├── flow/             # 流量控制 (延迟退避、限流)
│       ├── forwarder/        # 请求转发和超时管理
│       ├── handlers/         # Web 管理后台 API 处理器
│       ├── metrics/          # 监控指标采集与聚合
│       ├── middleware/       # Gin 中间件 (认证、CORS、日志、限流、追踪)
│       ├── router/           # 路由策略 (轮询、一致性 Hash)
│       ├── alert/            # 告警规则评估与通知
│       └── websocket/        # WebSocket 消息处理
├── internal/                 # 内部包
│   ├── config/               # YAML 配置管理
│   └── utils/
│       └── logger/           # zap 日志工具
├── web/                      # React 前端管理界面
│   ├── src/
│   ├── dist/                 # 构建产物 (go:embed 嵌入)
│   └── package.json
├── deploy/                   # 部署脚本
│   └── postgres/             # 数据库迁移脚本
├── sample/                   # 示例代码
│   ├── demo-go/              # Go SDK 示例
│   ├── frida/                # Frida 脚本示例
│   └── go/sekio/             # 旧版 SDK 示例
├── config.yaml               # 配置文件模板
└── go.mod                    # Go 模块定义
```

## 快速开始

### 环境要求

- Go 1.25.0 或更高版本
- PostgreSQL 12+（服务器端必需）
- Node.js 18+（前端开发必需）

### 1. 安装依赖

```bash
go mod tidy
```

### 2. 配置数据库

创建 PostgreSQL 数据库并修改 `config.yaml`：

```yaml
Database:
  Host: "localhost"
  Port: 5432
  User: "postgres"
  Password: "postgres"
  DBName: "sekiro"
  SSLMode: "disable"
```

或使用 `deploy/postgres/migration.sql` 手动初始化。

### 3. 构建前端（可选，但 `go build` 需要 `web/dist` 存在）

```bash
cd web && npm install && npm run build
```

### 4. 启动服务器

```bash
# 方式 1：使用默认配置 (端口 5612)
go run cmd/server/main.go

# 方式 2：指定端口和主机
go run cmd/server/main.go -port 5612 -host 0.0.0.0

# 方式 3：启用调试日志
go run cmd/server/main.go -debug

# 方式 4：使用配置文件
go run cmd/server/main.go -c config.yaml
```

### 5. 启动客户端

```bash
# 启动客户端 (连接到服务器)
go run cmd/client/main.go -server localhost:5612 -group test-group -client-id test-1
```

### 6. 调用服务

```bash
# 使用调用端发起 RPC 调用
go run cmd/invoker/main.go -server localhost:5612 -group test-group -api test
```

### 7. HTTP API 调用示例

```bash
# 获取分组列表
curl http://localhost:5612/business/groupList

# 获取客户端队列
curl http://localhost:5612/business/clientQueue?group=test-group

# 发起 RPC 调用
curl -X POST http://localhost:5612/business/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "group": "test-group",
    "action": "test",
    "params": {"key": "value"}
  }'

# 执行 JS 代码
curl http://localhost:5612/business/execjs?group=test-group&code=document.title

# 获取 Cookie
curl http://localhost:5612/business/cookie?group=test-group

# 获取 HTML
curl http://localhost:5612/business/html?group=test-group
```

## 配置说明

### 配置文件 (config.yaml)

```yaml
# 基础监听配置
BasicListen: ":5612"

# 主机和端口 (可选，与 BasicListen 二选一)
Host: "0.0.0.0"
Port: 5612

# RPC 调用默认超时时间（秒）
DefaultTimeOut: 30

# 日志配置
CloseLog: false        # 关闭日志
CloseWebLog: false     # 关闭 Web 访问日志

# 运行模式：debug 或 release
Mode: release

# 启用 CORS 跨域
Cors: true

# HTTPS 配置（可选）
HttpsServices:
  IsEnable: false
  HttpsListen: ":5643"
  PemPath: "certs/server.pem"
  KeyPath: "certs/server.key"

# 路由前缀替换（反向代理场景）
RouterReplace:
  IsEnable: false
  ReplaceRoute: "/sekiro"

# 数据库配置（必需）
Database:
  Host: "localhost"
  Port: 5432
  User: "postgres"
  Password: "postgres"
  DBName: "sekiro"
  SSLMode: "disable"

# 告警 SMTP 配置（可选）
Alert:
  SMTP:
    Host: "smtp.example.com"
    Port: 587
    Username: "alert@example.com"
    Password: "password"
    From: "alert@example.com"
    UseTLS: true
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-port` | 服务器端口 | 5612 |
| `-host` | 服务器主机 | 0.0.0.0 |
| `-debug` | 启用调试日志 | false |
| `-local-debug` | 启用本地调试模式 | false |
| `-c` | 配置文件路径 | config.yaml |

## 核心功能

### 服务器端

| 功能 | 说明 |
|------|------|
| **协议检测** | 自动识别 Rpc 二进制协议和 HTTP/WebSocket 协议 |
| **客户端管理** | 客户端注册、注销、状态管理、分组管理 |
| **负载均衡** | 支持轮询、指定客户端、一致性 Hash 三种路由策略 |
| **压缩支持** | Gzip、Snappy、None 三种压缩方式 |
| **超时管理** | 可配置的 RPC 调用超时和追踪机制 |
| **心跳检测** | WebSocket 心跳保活和超时断开 |
| **用户认证** | Bearer Token 认证，支持管理员与普通用户权限 |
| **分组权限** | 分组可绑定用户，未授权用户无法访问 |
| **QPS 限流** | 基于用户和 IP 的速率限制，支持配置调整 |
| **监控指标** | 分钟/小时/天维度的调用次数与延迟统计 |
| **调用追踪** | 完整的请求链路追踪与详情查询 |
| **告警系统** | 基于规则的告警评估，支持 SMTP/Webhook 通知 |
| **前端界面** | React + Ant Design 管理后台，嵌入 Go 二进制 |
| **CORS 支持** | 跨域请求支持 |
| **HTTPS** | 可选的 HTTPS 加密传输 |

### 客户端 SDK

```go
package main

import (
    "log"
    "github.com/mrh30000/go-rpc/pkg/client"
)

func main() {
    // 创建客户端
    c := client.NewRpcClient("my-group", "my-client-id", "localhost", 5612)

    // 启动客户端
    if err := c.Start(); err != nil {
        log.Fatal(err)
    }

    // 注册处理器
    c.Register(func(request []byte) ([]byte, error) {
        // 处理请求逻辑
        return []byte(`{"result": "success"}`), nil
    })

    // 保持运行
    select {}
}
```

### 调用端 SDK

```go
package main

import (
    "fmt"
    "log"
    "github.com/mrh30000/go-rpc/pkg/client"
)

func main() {
    // 创建调用端
    invoker := client.NewRpcInvoker([]string{"localhost:5612"})
    defer invoker.Destroy()

    // 发起调用
    resp, err := invoker.Invoke(&client.InvokeRequest{
        Group:   "my-group",
        Api:     "my-api",
        Params:  map[string]interface{}{"key": "value"},
        Timeout: 30, // 超时时间（秒）
    })

    if err != nil {
        log.Fatal(err)
    }

    fmt.Printf("Response: code=%d, message=%s, data=%v\n",
        resp.Code, resp.Message, resp.Data)
}
```

## SDK 使用

### RpcClient API

| 方法 | 说明 |
|------|------|
| `NewRpcClient(group, clientID, serverHost string, serverPort int)` | 创建客户端实例 |
| `Start() error` | 连接到服务器并启动消息处理 |
| `Register(handler func([]byte) ([]byte, error))` | 注册请求处理器 |
| `Destroy(waitSeconds int64)` | 销毁客户端连接 |

### RpcInvoker API

| 方法 | 说明 |
|------|------|
| `NewRpcInvoker(serverList []string)` | 创建调用端实例 |
| `NewRpcInvokerWithToken(apiToken string, serverList []string)` | 创建带 API Token 的调用端 |
| `Invoke(req *InvokeRequest) (*InvokeResponse, error)` | 发起 RPC 调用 |
| `Destroy()` | 销毁调用端 |

### InvokeRequest 结构

```go
type InvokeRequest struct {
    Group   string                 // 目标分组
    Api     string                 // API 名称
    Params  map[string]interface{} // 请求参数
    Timeout time.Duration          // 超时时间
}
```

### InvokeResponse 结构

```go
type InvokeResponse struct {
    Code    int         `json:"code"`    // 响应码
    Message string      `json:"message"` // 响应消息
    Data    interface{} `json:"data"`    // 响应数据
}
```

## API 接口

### 公开 HTTP API 端点

| 路径 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/health` | GET | 健康检查 | - |
| `/business/groupList` | GET | 获取分组列表 | - |
| `/business/clientQueue` | GET | 获取客户端队列 | `group` |
| `/business/invoke` | POST/GET | RPC 调用 | `group`, `clientId`, `action`, `params`, `timeout` |
| `/business/register` | WebSocket | 客户端注册 | `group`, `clientId` |
| `/business/execjs` | POST/GET | 执行 JS 代码 | `group`, `clientId`, `code` |
| `/business/cookie` | POST/GET | 获取 Cookie | `group`, `clientId` |
| `/business/html` | POST/GET | 获取 HTML | `group`, `clientId` |
| `/v1/chat/completions` | POST | OpenAI 兼容接口 | - |

### 认证相关接口

| 路径 | 方法 | 说明 |
|------|------|------|
| `/rpc-api/user-info/login` | POST | 用户登录 |
| `/rpc-api/user-info/register` | POST | 用户注册 |
| `/rpc-api/user-info/userInfo` | GET | 获取当前用户信息 |
| `/rpc-api/system/systemNotice` | GET | 系统公告 |
| `/rpc-api/system/systemInfo` | GET | 系统信息 |
| `/rpc-api/frontend/listGroup` | GET | 前端分组列表 |
| `/rpc-api/frontend/anonymousGroupList` | GET | 匿名分组列表 |
| `/rpc-api/frontend/groupDetail` | GET | 分组详情 |

### 管理后台 API（需要认证）

| 路径 | 方法 | 说明 |
|------|------|------|
| `/api/users` | GET/POST/DELETE | 用户管理 |
| `/api/users/qps` | PUT | 更新用户 QPS |
| `/api/current` | GET | 当前用户信息 |
| `/api/current/password` | POST | 修改密码 |
| `/api/current/token/refresh` | POST | 刷新 Token |
| `/api/groups` | GET/POST/DELETE | 分组管理 |
| `/api/groups/:groupName` | GET | 分组详情 |
| `/api/groups/:groupName/devices` | GET | 设备列表 |
| `/api/groups/devices` | DELETE/PUT | 删除/禁用设备 |
| `/api/groups/:groupName/actions` | GET | 动作列表 |
| `/api/groups/actions` | POST/DELETE | 添加/删除动作 |
| `/api/anonymous-groups` | GET/DELETE/POST | 匿名分组管理 |
| `/api/sysconfig` | GET/PUT | 系统配置 |
| `/api/sysconfig/nodes` | GET | 服务节点 |
| `/api/sysconfig/logs` | GET | 系统日志 |
| `/api/sysconfig/app-logs` | GET | 应用日志 |
| `/api/metrics` | GET | 监控指标 |
| `/api/metrics/dashboard` | GET | 仪表盘数据 |
| `/api/traces` | GET | 追踪列表 |
| `/api/traces/:traceId` | GET | 追踪详情 |
| `/api/alerts/rules` | GET/POST/PUT/DELETE | 告警规则 |
| `/api/alerts/history` | GET | 告警历史 |

### API 响应格式

**成功响应：**
```json
{
    "status": 0,
    "message": "success",
    "data": {...}
}
```

**失败响应：**
```json
{
    "status": -1,
    "message": "error message"
}
```

### 调用示例

```bash
# 获取分组列表
curl http://localhost:5612/business/groupList
# 响应：{"status":0,"message":"success","data":["group1","group2"]}

# 获取某分组的客户端列表
curl "http://localhost:5612/business/clientQueue?group=my-group"
# 响应：{"status":0,"message":"success","data":["client1","client2"]}

# RPC 调用 (GET)
curl "http://localhost:5612/business/invoke?group=my-group&action=myApi&params=%7B%22key%22%3A%22value%22%7D"

# RPC 调用 (POST)
curl -X POST http://localhost:5612/business/invoke \
  -H "Content-Type: application/json" \
  -d '{"group":"my-group","action":"myApi","params":{"key":"value"}}'
```

## 前端管理界面

项目包含基于 React + Ant Design 的 Web 管理后台，通过 `//go:embed dist` 嵌入 Go 二进制。

### 前端开发

```bash
cd web
npm install
npm run dev    # 端口 3000，代理 /business、/api、/rpc-api → localhost:5613
```

> **注意**：Vite 开发代理目标为 `localhost:5613`，但服务器默认监听 `5612`。请修改 `web/vite.config.js` 中的代理目标，或启动服务器时指定 `-port 5613`。

### 前端构建

```bash
cd web && npm run build   # 输出到 web/dist/
```

构建完成后，`go build` 会将 `web/dist/` 嵌入二进制。

### 默认管理员账号

数据库迁移完成后自动创建：
- 用户名：`admin`
- 密码：`admin123`

## 协议说明

### 数据包格式

```
[Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
```

| 字段 | 大小 | 说明 |
|------|------|------|
| Magic | 8 字节 | 魔数 (0x73656b69726f0000) |
| Length | 4 字节 | 包体长度 |
| Type | 1 字节 | 包类型 |
| SerialNumber | 4 字节 | 序列号 |
| Headers | 可变 | 头部键值对 |
| Data | 可变 | 数据载荷 |

### 包类型定义

| 类型 | 值 | 方向 | 说明 |
|------|-----|------|------|
| HEARTBEAT | 0 | 双向 | 心跳包 |
| C_REGISTER | 16 | C→S | 客户端注册 |
| C_INVOKE_RESPONSE | 17 | C→S | 调用响应 |
| C_OFFLINE | 18 | C→S | 客户端下线 |
| S_INVOKE | 32 | S→C | 服务器调用 |
| I_INVOKE | 49 | I→S | 调用端请求 |

### WebSocket 消息格式

**请求消息：**
```json
{
    "type": "invoke",
    "group": "my-group",
    "clientId": "client-1",
    "action": "my-api",
    "params": {"key": "value"},
    "__sekiro_seq__": "sequence-id"
}
```

**响应消息：**
```json
{
    "type": "invoke_response",
    "status": 0,
    "data": {"result": "success"},
    "__sekiro_seq__": "sequence-id"
}
```

**心跳消息：**
```json
{
    "type": "heartbeat",
    "timestamp": 1234567890
}
```

## 路由策略

服务器支持三种客户端路由策略：

### 1. 轮询策略 (Round Robin)

默认策略，按顺序分配请求到分组内的客户端。

```go
// 不指定 clientId 时自动使用轮询
invoker.Invoke(&InvokeRequest{
    Group: "my-group",
    Api:   "my-api",
})
```

### 2. 指定客户端

直接路由到特定客户端。

```go
invoker.Invoke(&InvokeRequest{
    Group:    "my-group",
    ClientID: "specific-client",
    Api:      "my-api",
})
```

### 3. 一致性 Hash 策略

根据请求参数的一致性 Hash 值路由，保证相同参数的请求总是到达同一客户端。

```go
// 通过 constantInvoke 参数启用
curl "http://localhost:5612/business/invoke?group=my-group&action=myApi&constantInvoke=true"
```

## 测试

### 运行所有测试

```bash
go test ./... -v
```

### 运行单个包的测试

```bash
# 协议层测试
go test ./pkg/protocol/... -v

# 压缩模块测试
go test ./pkg/compress/... -v

# 客户端 SDK 测试
go test ./pkg/client/... -v

# 服务器端测试
go test ./pkg/server/... -v
```

### 运行单个测试

```bash
go test -run TestRpcPacket ./pkg/protocol/...
go test -run TestGzipCompress ./pkg/compress/...
```

### 测试状态

| 模块 | 测试状态 |
|------|---------|
| pkg/protocol | 通过 |
| pkg/compress | 通过 |
| pkg/eventbus | 通过 |
| pkg/client | 通过 |
| pkg/server/client | 通过 |
| pkg/server/detector | 通过 |
| pkg/server/flow | 通过 |
| pkg/server/forwarder | 通过 |
| pkg/server/router | 通过 |
| pkg/server/websocket | 通过 |

## 与 Java 版本对比

| 功能 | Java 版本 | Go 版本 |
|------|----------|--------|
| 网络框架 | Netty | gorilla/websocket + Gin |
| JSON 序列化 | FastJSON | encoding/json |
| 压缩 | Java Gzip/Snappy | compress/gzip + golang/snappy |
| 日志 | Logback | uber-go/zap |
| 并发 | 线程池 | goroutine + channel |
| 配置 | properties | yaml.v3 |
| HTTP 框架 | 原生 Servlet | Gin |
| 数据库 | MySQL/自建 | PostgreSQL + GORM |
| 管理界面 | JSP/Vue | React + Ant Design |
| 监控告警 | 无 | 内置指标 + 告警规则 |
| 调用追踪 | 无 | 内置链路追踪 |

## 常见问题

### Q: 端口已经被占用怎么办？

A: 使用 `-port` 参数指定其他端口：
```bash
go run cmd/server/main.go -port 8080
```

### Q: 如何启用调试模式？

A: 使用 `-debug` 参数或设置配置文件中的 `Mode: debug`：
```bash
go run cmd/server/main.go -debug
```

### Q: 客户端断线后如何处理？

A: 服务器会自动检测客户端离线并从未分配列表中移除，客户端重连后会自动重新注册。连续 3 次心跳失败后客户端会被标记为不健康。

### Q: 如何部署到生产环境？

A: 建议配置：
1. 设置 `Mode: release`
2. 启用 HTTPS
3. 配置合适的超时时间
4. 使用反向代理（Nginx）处理路由前缀
5. 配置 PostgreSQL 并定期备份
6. 设置告警 SMTP 以接收系统告警

### Q: 支持哪些压缩算法？

A: 当前支持 Gzip 和 Snappy 两种压缩算法，可通过配置选择。

### Q: `go build` 报错 `pattern dist: no matching files found`？

A: 必须先构建前端生成 `web/dist/`：
```bash
cd web && npm install && npm run build
```

### Q: 前端开发时代理报错？

A: Vite 代理默认目标为 `localhost:5613`，而服务器默认端口是 `5612`。请修改 `web/vite.config.js` 中的代理目标，或启动服务器时指定 `-port 5613`。

## 构建

```bash
# 构建前端（必须先执行）
cd web && npm run build

# 构建服务器
go build -o sekiro-server ./cmd/server

# 构建客户端
go build -o sekiro-client ./cmd/client

# 构建调用端
go build -o sekiro-invoker ./cmd/invoker
```

## 相关资源

- [Java 版本 Rpc](https://github.com/yuaotian/Rpc)
- [Gin 框架文档](https://gin-gonic.com/)
- [gorilla/websocket](https://github.com/gorilla/websocket)

## 许可证

与原 Rpc 项目保持一致（Apache 2.0）。
