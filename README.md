# Sekiro RPC - Go 语言实现

SEKIRO 是一个多语言、分布式、网络拓扑无关的服务发布平台。

这是 Java 版本的 Go 语言实现。

## 项目结构

```
sekiro-go/
├── cmd/
│   ├── server/       # 服务器端启动程序
│   ├── client/       # 客户端示例
│   └── invoker/      # 调用端示例
├── pkg/
│   ├── server/       # 服务器端核心
│   │   ├── bootstrap.go        # 服务器启动
│   │   ├── client_manager.go   # 客户端管理
│   │   └── detector/           # 协议检测
│   │       ├── detector.go     # 协议检测器
│   │       ├── sekiro_matcher.go
│   │       ├── http_matcher.go
│   │       ├── sekiro_handler.go
│   │       └── http_handler.go
│   ├── client/       # 客户端 SDK
│   │   ├── client.go # SekiroClient
│   │   └── invoker.go# SekiroInvoker
│   ├── protocol/     # 通信协议
│   │   ├── packet.go # 数据包定义和编解码
│   │   └── packet_type.go # 数据包类型
│   ├── compress/     # 压缩算法
│   │   ├── gzip.go
│   │   ├── snappy.go
│   │   ├── none.go
│   │   └── manager.go
│   └── eventbus/     # 事件总线
│       ├── eventbus.go
│       └── events.go
└── internal/
    └── utils/
        └── logger/   # 日志工具
            └── logger.go
```

## 快速开始

### 1. 启动服务器

```bash
cd sekiro-go
go run cmd/server/main.go -port 5612
```

### 2. 启动客户端

```bash
go run cmd/client/main.go -server localhost:5612 -group test-group -client-id test-1
```

### 3. 调用服务

```bash
go run cmd/invoker/main.go -server localhost:5612 -group test-group -api test
```

## 核心功能

### 服务器端

- **协议检测**: 自动识别 Sekiro 二进制协议和 HTTP 协议
- **客户端管理**: 注册、注销、状态管理
- **负载均衡**: 多客户端轮询分配
- **压缩支持**: Gzip、Snappy、None

### 客户端 SDK

```go
import "github.com/sekiro-go/sekiro-go/pkg/client"

// 创建客户端
c := client.NewSekiroClient("my-group", "my-client-id", "localhost", 5612)

// 启动
if err := c.Start(); err != nil {
    log.Fatal(err)
}

// 注册处理器
c.Register(func(request []byte) ([]byte, error) {
    // 处理请求
    return []byte("response"), nil
})
```

### 调用端 SDK

```go
import "github.com/sekiro-go/sekiro-go/pkg/client"

// 创建调用端
invoker := client.NewSekiroInvoker([]string{"localhost:5612"})
defer invoker.Destroy()

// 调用
resp, err := invoker.Invoke(&client.InvokeRequest{
    Group:  "my-group",
    Api:    "my-api",
    Params: map[string]interface{}{"key": "value"},
})
```

## 协议说明

### 数据包格式

```
[Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
```

- **Magic**: 8 字节魔数 (0x73656b69726f0000)
- **Length**: 包体长度
- **Type**: 包类型
- **SerialNumber**: 序列号
- **Headers**: 头部键值对
- **Data**: 数据载荷

### 包类型

| 类型 | 值 | 方向 | 说明 |
|------|---|------|------|
| HEARTBEAT | 0 | 双向 | 心跳包 |
| C_REGISTER | 16 | C→S | 客户端注册 |
| C_INVOKE_RESPONSE | 17 | C→S | 调用响应 |
| C_OFFLINE | 18 | C→S | 客户端下线 |
| S_INVOKE | 32 | S→C | 服务器调用 |
| I_INVOKE | 49 | I→S | 调用端请求 |

## 与 Java 版本对比

| 功能 | Java 版本 | Go 版本 |
|------|----------|--------|
| 网络框架 | Netty | 原生 net + bufio |
| JSON 序列化 | FastJSON | encoding/json (简化实现) |
| 压缩 | Java Gzip/Snappy | compress/gzip + golang/snappy |
| 日志 | Logback | zap |
| 并发 | 线程池 | goroutine + channel |

## 当前状态

✅ 已完成:
- 协议层（数据包编解码）
- 压缩模块（Gzip、Snappy、None）
- 服务器启动和协议检测
- HTTP 处理器（基础）
- 客户端 SDK 框架
- 调用端 SDK 框架
- 事件总线

⚠️ 待完善:
- WebSocket 支持
- 完整的路由转发逻辑
- 客户端注册完整流程
- 调用响应的异步处理
- 单元测试和集成测试
- 与 Java 版本的互操作性测试

## 构建

```bash
# 获取依赖
go mod tidy

# 构建所有
go build ./...

# 构建服务器
go build -o sekiro-server ./cmd/server

# 构建客户端
go build -o sekiro-client ./cmd/client

# 构建调用端
go build -o sekiro-invoker ./cmd/invoker
```

## 许可证

与原 Sekiro 项目保持一致。
