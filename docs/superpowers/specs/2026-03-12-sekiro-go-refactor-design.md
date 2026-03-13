# Sekiro Go 版本重构设计文档

**日期：** 2026-03-12
**作者：** Claude (基于 Java Sekiro3 实现分析)
**状态：** 已批准

---

## 1. 背景与目标

### 1.1 背景

当前 Go 版本的 Sekiro 实现存在以下问题：
- HTTP 请求解析使用手写实现，代码冗长且不支持高级特性
- ClientManager 使用 `sync.RWMutex`，高并发下存在锁竞争
- 仅支持简单轮询路由，缺少一致性 Hash 和指定客户端路由
- 缺少流量控制和超时管理机制
- WebSocket 客户端注册和请求转发逻辑不完整

### 1.2 目标

参考 Java Sekiro3 实现，对 Go 版本进行全面重构：
1. 使用标准库 `net/http` 替换手写 HTTP 解析
2. 使用 channel + goroutine 模式实现无锁并发
3. 实现三种路由策略（轮询、指定客户端、一致性 Hash）
4. 实现空队列延迟退避机制
5. 完善 WebSocket 客户端注册和请求转发流程

### 1.3 设计原则

- **API 兼容性：** 保持现有 API 接口完全兼容（路径、参数格式）
- **渐进式重构：** 分阶段实施，每个阶段可独立验证
- **Go 最佳实践：** 使用 channel 并发模型，符合 Go 语言哲学
- **代码质量：** 按功能重新组织目录结构，提高可维护性

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                      HTTP Server                         │
│  (net/http.Server + websocket.Upgrader)                 │
└─────────────────────────────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌────────────┐   ┌────────────┐   ┌────────────┐
   │  /invoke   │   │ /register  │   │  /groupList │
   │  API Handler│   │ WS Upgrade │   │  /clientQueue│
   └────────────┘   └────────────┘   └────────────┘
          │                 │
          ▼                 ▼
   ┌─────────────────────────────────┐
   │         Router (路由中心)        │
   │  - RoundRobin (轮询)            │
   │  - SpecifiedClient (指定客户端)  │
   │  - ConsistentHash (一致性 Hash)  │
   └─────────────────────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   ┌────────────┐   ┌────────────┐   ┌────────────┐
   │  Group A   │   │  Group B   │   │  Group C   │
   │  (channel) │   │  (channel) │   │  (channel) │
   └────────────┘   └────────────┘   └────────────┘
          │
          ▼
   ┌─────────────────────────────────┐
   │      SekiroClient 容器           │
   │  - WebSocket 连接               │
   │  - 待响应请求追踪               │
   │  - 序列号管理                   │
   └─────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 并发模型 |
|------|------|----------|
| `HTTPServer` | HTTP 服务器，处理 API 和 WebSocket 升级 | 标准库多 goroutine |
| `SekiroGroup` | 分组管理，维护客户端列表和路由策略 | 单 goroutine + channel |
| `ClientManager` | 管理所有分组，提供分组查找 | RWMutex (仅保护 map) |
| `SekiroClient` | 客户端容器，管理连接和请求追踪 | 独立 goroutine |
| `BackoffController` | 流量控制，空队列延迟退避 | 无状态计算 |

---

## 3. 目录结构

```
pkg/server/
├── bootstrap.go              # 服务器启动入口
├── config.go                 # 配置结构
│
├── api/                      # HTTP API 处理
│   ├── http_server.go        # HTTP 服务器（标准库 net/http）
│   ├── handlers.go           # API 处理器（invoke/groupList/clientQueue）
│   └── websocket.go          # WebSocket 升级处理
│
├── router/                   # 路由中心
│   ├── group.go              # SekiroGroup 分组管理
│   ├── strategy.go           # 三种路由策略实现
│   └── hash.go               # 一致性 Hash 工具
│
├── client/                   # 客户端管理
│   ├── manager.go            # ClientManager（channel 并发）
│   ├── client.go             # SekiroClient 客户端结构
│   └── pool.go               # 客户端池（轮询队列、离线队列）
│
├── forwarder/                # 请求转发
│   ├── invoker.go            # 请求转发器
│   ├── tracker.go            # 请求追踪（InvokeRecord）
│   └── timeout.go            # 超时管理
│
├── flow/                     # 流量控制
│   ├── limiter.go            # 流量限制器
│   └── backoff.go            # 延迟退避机制
│
└── websocket/                # WebSocket 处理
    ├── handler.go            # WebSocket 消息处理器
    └── frame.go              # WebSocket 帧处理
```

---

## 4. 详细设计

### 4.1 阶段一：HTTP 解析标准化

**当前问题：**
- `http_handler.go` 手写 HTTP 解析约 260 行代码
- 需要手动处理 Keep-Alive、Content-Length 等细节
- 不支持 chunked 传输等高级特性

**改进方案：**

```go
// pkg/server/api/http_server.go
type HTTPServer struct {
    server      *http.Server
    router      *http.ServeMux
    wsUpgrader  *websocket.Upgrader
    handlerMap  map[string]http.HandlerFunc
    invokeHandler InvokeHandler
}

func (s *HTTPServer) Start(addr string) error {
    s.server = &http.Server{
        Addr:         addr,
        Handler:      s.router,
        ReadTimeout:  30 * time.Second,
        WriteTimeout: 30 * time.Second,
    }
    return s.server.ListenAndServe()
}

func (s *HTTPServer) handleWebSocketUpgrade(w http.ResponseWriter, r *http.Request) {
    wsConn, err := s.wsUpgrader.Upgrade(w, r, nil)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    // 移交 WebSocket 处理器
    s.handlerMap["/ws"](wsConn, r)
}
```

**API 路由表：**

| 路径 | 方法 | 处理器 | 功能 |
|------|------|--------|------|
| `/business/invoke` | POST/GET | `handleInvoke` | RPC 调用 |
| `/business-demo/invoke` | POST/GET | `handleInvoke` | RPC 调用（演示） |
| `/business/groupList` | GET | `handleGroupList` | 获取分组列表 |
| `/business/clientQueue` | GET | `handleClientQueue` | 获取客户端队列 |
| `/business/register` | WebSocket | `handleWebSocketUpgrade` | 客户端注册 |
| `/register` | WebSocket | `handleWebSocketUpgrade` | 客户端注册（简化） |

---

### 4.2 阶段二：ClientManager 并发重构

**当前问题：**
- `sync.RWMutex` 在高并发下存在竞争
- 路由逻辑和客户端管理耦合

**改进方案：**

```go
// pkg/server/client/manager.go
type ClientManager struct {
    groups map[string]*SekiroGroup
    mu     sync.RWMutex // 仅保护 groups map
}

// SekiroGroup 每个分组一个独立的 goroutine
type SekiroGroup struct {
    name        string
    commandChan chan groupCommand  // 所有操作通过 channel 发送
    clients     map[string]*SekiroClient
    consistentMap *treemap.Map  // 一致性 Hash
    queue       []*SekiroClient  // 轮询队列
    offline     map[string]*SekiroClient  // 离线队列
}

type groupCommand struct {
    typ      commandType
    client   *SekiroClient
    clientId string
    callback chan commandResult
}

func (g *SekiroGroup) runLoop() {
    for cmd := range g.commandChan {
        switch cmd.typ {
        case cmdRegister:
            g.handleRegister(cmd.client)
        case cmdUnregister:
            g.handleUnregister(cmd.clientId)
        case cmdAllocate:
            g.handleAllocate(cmd.callback)
        // ... 其他命令
        }
    }
}
```

**并发模型：**
```
外部调用 ──► commandChan ──► goroutine 处理 ──► 返回结果
           (无锁队列)      (单线程安全)
```

---

### 4.3 阶段三：三种路由策略

**路由策略实现：**

```go
// pkg/server/router/strategy.go
type RoutingStrategy int

const (
    RouteRoundRobin RoutingStrategy = iota  // 轮询
    RouteSpecifiedClient                      // 指定客户端
    RouteConsistentHash                       // 一致性 Hash
)

func (g *SekiroGroup) Allocate(params RouteParams) (*SekiroClient, error) {
    // 1. 指定客户端优先
    if params.ClientID != "" {
        return g.fetchByClientID(params.ClientID)
    }
    // 2. 一致性 Hash
    if params.ConsistentKey != "" {
        return g.consistentHashAllocate(params.ConsistentKey)
    }
    // 3. 默认轮询
    return g.roundRobinAllocate()
}

// 一致性 Hash 实现
func (g *SekiroGroup) consistentHashAllocate(key string) (*SekiroClient, error) {
    hash := murmurHash(key)
    // 在有序 Map 中查找第一个 >= hash 的节点
    entry := g.consistentMap.Ceiling(hash)
    if entry == nil {
        // 循环查找，返回第一个节点
        entry = g.consistentMap.Min()
    }
    if entry == nil {
        return nil, errors.New("no client available")
    }
    return entry.Value.(*SekiroClient), nil
}
```

---

### 4.4 阶段四：流量控制与超时管理

**空队列延迟退避机制：**

```go
// pkg/server/flow/backoff.go
type BackoffController struct {
    emptyCount     int
    firstEmptyTime time.Time
    mu             sync.Mutex
}

func (b *BackoffController) RecordEmpty() time.Duration {
    b.mu.Lock()
    defer b.mu.Unlock()

    if b.emptyCount == 0 {
        b.firstEmptyTime = time.Now()
    }
    b.emptyCount++

    // Java 版退避逻辑的 Go 实现
    if b.emptyCount <= 5 {
        return 0
    }
    if b.emptyCount <= 10 {
        return time.Duration(b.emptyCount-4) * time.Second
    }
    if b.emptyCount < 100 {
        if time.Since(b.firstEmptyTime) > 10*time.Minute {
            return 15 * time.Second
        }
        return 10 * time.Second
    }
    if time.Since(b.firstEmptyTime) > 30*time.Minute {
        return 20 * time.Second
    }
    return 15 * time.Second
}

func (b *BackoffController) RecordSuccess() {
    b.mu.Lock()
    defer b.mu.Unlock()
    b.emptyCount = 0
    b.firstEmptyTime = time.Time{}
}
```

**超时管理：**

```go
// pkg/server/forwarder/timeout.go
type InvokeRecord struct {
    seq              int
    client           *SekiroClient
    request          *InvokeRequest
    responseChan     chan *protocol.SekiroPacket
    timeout          time.Duration
    timer            *time.Timer
    isSegment        bool  // 分段传输模式
}

func (r *InvokeRecord) StartTimeout() {
    r.timer = time.AfterFunc(r.timeout, func() {
        if r.isSegment && time.Now().Before(r.deadline) {
            // 分段传输模式，延期
            r.StartTimeout()
            return
        }
        // 超时，返回错误
        r.response(CommonRes.Failed("timeout"))
    })
}
```

---

### 4.5 阶段五：WebSocket 客户端注册

**注册流程：**

```go
// pkg/server/websocket/handler.go
type WebSocketHandler struct {
    conn        *websocket.Conn
    group       *SekiroGroup
    clientId    string
    recvChan    chan *protocol.SekiroPacket
    pendingReq  map[int]*InvokeRecord  // 待响应的请求
    seqGen      atomic.Int32
    mu          sync.RWMutex
}

func (h *WebSocketHandler) Handle(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
        }

        packet, err := h.Receive()
        if err != nil {
            if err == io.EOF {
                logger.Debugf("WebSocket connection closed")
                return nil
            }
            return err
        }

        if err := h.handlePacket(packet); err != nil {
            logger.Errorf("Handle packet error: %v", err)
        }
    }
}

func (h *WebSocketHandler) handleRegister(packet *protocol.SekiroPacket) error {
    group := packet.GetHeader("sekiroGroup")
    clientID := packet.GetHeader("clientId")

    if group == "" || clientID == "" {
        logger.Warn("group or clientId is empty")
        h.conn.Close()
        return nil
    }

    // 注册到分组
    h.group = getOrCreateGroup(group)
    h.clientId = clientID

    client := NewSekiroClient(group, clientID, h)
    h.group.Register(client)

    logger.Infof("Client registered: group=%s, clientId=%s", group, clientID)
    return nil
}
```

---

## 5. API 兼容性

所有 API 接口保持与 Java 版完全兼容：

**请求格式：**
```json
POST /business/invoke
Content-Type: application/json

{
    "group": "test-group",
    "clientId": "client-001",      // 可选，指定客户端
    "constantInvoke": "user-123",  // 可选，一致性 Hash 键
    "timeout": 15000,              // 可选，超时毫秒
    "action": "getUserInfo",
    "params": {...}
}
```

**响应格式：**
```json
{
    "status": 0,
    "message": "success",
    "clientId": "client-001",
    "data": {...}
}
```

---

## 6. 实施计划

### 阶段一：HTTP 解析标准化
- [ ] 创建 `pkg/server/api/http_server.go`
- [ ] 创建 `pkg/server/api/handlers.go`
- [ ] 创建 `pkg/server/api/websocket.go`
- [ ] 删除旧 `http_handler.go`
- [ ] 测试 HTTP API 和 WebSocket 升级

### 阶段二：ClientManager 并发重构
- [ ] 创建 `pkg/server/client/manager.go`
- [ ] 创建 `pkg/server/client/client.go`
- [ ] 创建 `pkg/server/client/pool.go`
- [ ] 实现 `SekiroGroup` 的 goroutine + channel 模型
- [ ] 并发测试

### 阶段三：三种路由策略
- [ ] 创建 `pkg/server/router/strategy.go`
- [ ] 创建 `pkg/server/router/hash.go`（一致性 Hash）
- [ ] 实现轮询、指定客户端、一致性 Hash 三种策略
- [ ] 路由测试

### 阶段四：流量控制与超时管理
- [ ] 创建 `pkg/server/flow/backoff.go`
- [ ] 创建 `pkg/server/forwarder/timeout.go`
- [ ] 实现延迟退避机制
- [ ] 实现超时管理
- [ ] 压力测试

### 阶段五：WebSocket 客户端注册
- [ ] 创建 `pkg/server/websocket/handler.go`
- [ ] 完善注册和请求转发逻辑
- [ ] 端到端测试

---

## 7. 验证标准

- [ ] 所有单元测试通过
- [ ] HTTP API 与 Java 版行为一致
- [ ] WebSocket 客户端注册成功
- [ ] 三种路由策略工作正常
- [ ] 空队列延迟退避机制生效
- [ ] 超时管理正常
- [ ] 压力测试无明显性能问题
