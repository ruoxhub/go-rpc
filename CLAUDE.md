# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Sekiro RPC - Go 语言实现，是一个多语言、分布式、网络拓扑无关的服务发布平台。这是 Java 版本 Sekiro 的 Go 语言实现。

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
go test -run TestSekiroPacket ./pkg/protocol/...
```

## 项目架构

```
pkg/
├── client/           # 客户端 SDK (SekiroClient, SekiroInvoker)
├── compress/         # 压缩算法 (Gzip, Snappy, None)
├── eventbus/         # 事件总线
├── protocol/         # 通信协议层 (数据包编解码)
└── server/           # 服务器端核心
    ├── api/          # HTTP API 处理器 (Gin 框架)
    ├── client/       # 客户端管理 (分组、轮询)
    ├── detector/     # 协议检测器
    ├── flow/         # 流量控制 (延迟退避)
    ├── forwarder/    # 请求转发和超时管理
    ├── router/       # 路由策略 (轮询、一致性 Hash)
    └── websocket/    # WebSocket 消息处理

cmd/
├── server/           # 服务器端启动程序
├── client/           # 客户端示例
└── invoker/          # 调用端示例

internal/
├── config/           # YAML 配置管理
└── utils/
    └── logger/       # zap 日志工具
```

## 核心模块

### 服务器端 (pkg/server)

- **bootstrap.go**: 服务器启动入口，使用 Gin 框架处理 HTTP 和 WebSocket
- **api/handlers.go**: HTTP API 处理器 (`/business/invoke`, `/business/groupList`, `/business/clientQueue`)
- **client/manager.go**: 客户端分组管理，支持轮询和指定客户端路由
- **router/strategy.go**: 三种路由策略（轮询、指定客户端、一致性 Hash）
- **forwarder/timeout.go**: 请求超时管理和追踪
- **flow/backoff.go**: 空队列延迟退避机制
- **websocket/handler.go**: WebSocket 消息处理和客户端注册

### 客户端 SDK (pkg/client)

- **client.go**: SekiroClient - WebSocket 客户端，支持注册和请求处理
- **invoker.go**: SekiroInvoker - 调用端，支持向服务器发送 RPC 调用

### 协议层 (pkg/protocol)

数据包格式：
```
[Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
```

包类型：
- HEARTBEAT (0): 心跳包
- C_REGISTER (16): 客户端注册
- C_INVOKE_RESPONSE (17): 调用响应
- C_OFFLINE (18): 客户端下线
- S_INVOKE (32): 服务器调用
- I_INVOKE (49): 调用端请求

## API 端点

| 路径 | 方法 | 说明 |
|------|------|------|
| `/business/invoke` | POST/GET | RPC 调用 |
| `/business/groupList` | GET | 获取分组列表 |
| `/business/clientQueue` | GET | 获取客户端队列 |
| `/business/register` | WebSocket | 客户端注册 |
| `/business/execjs` | POST/GET | 执行 JS 代码 |
| `/business/cookie` | POST/GET | 获取 Cookie |
| `/business/html` | GET | 获取 HTML |

## 配置

支持 YAML 配置文件 (`config.yaml`)：

```yaml
BasicListen: ":5612"
Host: "0.0.0.0"
Port: 5612
DefaultTimeOut: 30
Mode: "release"  # debug/release
Cors: true
CloseLog: false
CloseWebLog: false
```

## 开发注意事项

- 项目使用 Gin 框架处理 HTTP 路由和中间件
- WebSocket 使用 gorilla/websocket 库
- 日志使用 uber-go/zap
- 压缩支持 Gzip 和 Snappy
- 当前 branch `feat/refactor-api-with-gin` 已完成从原生 net/http 到 Gin 的迁移
