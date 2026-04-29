# Rpc RPC - Go 语言实现

[![Go Version](https://img.shields.io/badge/go-1.25.0-blue.svg)](https://golang.org)
[![License](https://img.shields.io/badge/license-Apache2.0-green.svg)](LICENSE)

SEKIRO 是一个多语言、分布式、网络拓扑无关的服务发布平台。

这是 Java 版本 Rpc 的 Go 语言实现，支持 WebSocket 通信、HTTP API、路由负载均衡等核心功能。

## 目录

- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [核心功能](#核心功能)
- [SDK 使用](#sdk-使用)
- [API 接口](#api-接口)
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
│   ├── eventbus/             # 事件总线
│   │   ├── eventbus.go
│   │   └── events.go
│   ├── protocol/             # 通信协议层 (数据包编解码)
│   │   ├── packet.go
│   │   └── packet_type.go
│   └── server/               # 服务器端核心
│       ├── api/              # HTTP API 处理器 (Gin 框架)
│       │   ├── handlers.go
│       │   └── http_server.go
│       ├── client/           # 客户端管理 (分组、轮询)
│       │   ├── manager.go
│       │   └── group.go
│       ├── detector/         # 协议检测器
│       │   └── detector.go
│       ├── flow/             # 流量控制 (延迟退避)
│       │   └── backoff.go
│       ├── forwarder/        # 请求转发和超时管理
│       │   └── timeout.go
│       ├── router/           # 路由策略 (轮询、一致性 Hash)
│       │   └── strategy.go
│       └── websocket/        # WebSocket 消息处理
│           └── handler.go
├── internal/                 # 内部包
│   ├── config/               # YAML 配置管理
│   │   └── config.go
│   └── utils/
│       └── logger/           # zap 日志工具
│           └── logger.go
├── sample/                   # 示例代码
│   └── demo-go/
├── config.yaml               # 配置文件模板
└── go.mod                    # Go 模块定义
```

## 快速开始

### 环境要求

- Go 1.25.0 或更高版本

### 1. 安装依赖

```bash
go mod tidy
```

### 2. 启动服务器

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

### 3. 启动客户端

```bash
# 启动客户端 (连接到服务器)
go run cmd/client/main.go -server localhost:5612 -group test-group -client-id test-1
```

### 4. 调用服务

```bash
# 使用调用端发起 RPC 调用
go run cmd/invoker/main.go -server localhost:5612 -group test-group -api test
```

### 5. HTTP API 调用示例

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

### HTTP API 端点

| 路径 | 方法 | 说明 | 参数 |
|------|------|------|------|
| `/business/groupList` | GET | 获取分组列表 | - |
| `/business/clientQueue` | GET | 获取客户端队列 | `group` |
| `/business/invoke` | POST/GET | RPC 调用 | `group`, `clientId`, `action`, `params`, `timeout` |
| `/business/register` | WebSocket | 客户端注册 | `group`, `clientId` |
| `/business/execjs` | POST/GET | 执行 JS 代码 | `group`, `clientId`, `code` |
| `/business/cookie` | POST/GET | 获取 Cookie | `group`, `clientId` |
| `/business/html` | POST/GET | 获取 HTML | `group`, `clientId` |

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
| pkg/protocol | ✅ 通过 |
| pkg/compress | ✅ 通过 |
| pkg/eventbus | ✅ 通过 |
| pkg/client | ✅ 通过 |
| pkg/server/client | ✅ 通过 |
| pkg/server/detector | ✅ 通过 |
| pkg/server/flow | ✅ 通过 |
| pkg/server/forwarder | ✅ 通过 |
| pkg/server/router | ✅ 通过 |
| pkg/server/websocket | ✅ 通过 |

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

A: 服务器会自动检测客户端离线并从未分配列表中移除，客户端重连后会自动重新注册。

### Q: 如何部署到生产环境？

A: 建议配置：
1. 设置 `Mode: release`
2. 启用 HTTPS
3. 配置合适的超时时间
4. 使用反向代理（Nginx）处理路由前缀

### Q: 支持哪些压缩算法？

A: 当前支持 Gzip 和 Snappy 两种压缩算法，可通过配置文件选择。

## 构建

```bash
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
