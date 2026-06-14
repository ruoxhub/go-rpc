# go-rpc 增强设计：汲取 JsRpc 与 Sekiro 优点

日期：2026-06-14
状态：已批准

## 背景

go-rpc 已有完整的管理平台、鉴权、指标、告警、流式响应等能力。通过对比分析 JsRpc（轻量实用）和 Sekiro-open（架构成熟），识别出多个可借鉴的特性。本设计分两阶段将这些特性引入 go-rpc，所有改动向下兼容现有 WebSocket 客户端。

## 项目对比摘要

| 维度 | go-rpc | JsRpc | Sekiro-open |
|---|---|---|---|
| 协议 | JSON over WS | JSON over WS | 二进制 + JSON/WS |
| 路由 | 轮询+指定+一致性哈希 | 随机（健康优先） | 队列轮询+一致性哈希+绑定 |
| 管理 | React SPA + DB + 鉴权 | 内嵌 HTML 控制台 | 无（开源版） |
| 客户端管理 | 注册/注销 | 注册/注销/踢除/模糊匹配 | 注册/注销 |
| execjs | 无 | 有 | 无 |
| 链路追踪 | middleware 层有 | 无 | 请求级 trace_id 贯穿 |

## 约束

- WebSocket 消息协议可扩展但必须向下兼容（老客户端不受影响）
- 不做 execjs 远程执行 JS 功能（本期）
- 管理界面增强现有 React SPA，不新增内嵌控制台

---

## 阶段一：服务端改动（不动协议）

### 1. 客户端模糊匹配

**来源**：JsRpc 的 `fuzzy=true` 参数

**改动文件**：
- `pkg/client/group.go` — 新增 `FindClientByFuzzy` 方法
- `pkg/router/strategy.go` — `RouteParams` 新增 `Fuzzy` 字段
- `pkg/handler/invoke.go` — `InvokeRequest` 新增 `Fuzzy` 字段
- `pkg/handler/routes.go` — clientQueue 接口支持 fuzzy 参数

**详细设计**：

`InvokeRequest` 新增可选字段：
```go
type InvokeRequest struct {
    // ...existing fields...
    Fuzzy bool `json:"fuzzy,omitempty"`
}
```

`RpcGroup` 新增模糊查找命令：
```go
const cmdFuzzyFind commandType = iota + 5 // 追加到现有命令类型之后

func (g *RpcGroup) FindClientByFuzzy(substr string) *RpcClient {
    callback := make(chan commandResult, 1)
    if !g.sendCommand(groupCommand{
        typ:      cmdFuzzyFind,
        clientID: substr,
        callback: callback,
    }) {
        return nil
    }
    return g.waitCallback(callback).client
}
```

`handleCommand` 中新增 `cmdFuzzyFind` 分支：
- 遍历 `g.clients`，`strings.Contains(id, substr)` 筛选
- 健康且在线的客户端优先
- 多个匹配时随机选择
- 无健康客户端时退化为不健康客户端中随机选择

`Router.Route` 调整：
- 当 `params.ClientID != "" && params.Fuzzy == true` 时，调用 `group.FindClientByFuzzy(params.ClientID)` 替代 `group.GetClient(params.ClientID)`

`clientQueue` 接口扩展：
- `GET /business/clientQueue?group=xxx&clientId=xxx&fuzzy=true` 返回匹配的客户端列表

**兼容性**：`fuzzy` 参数可选，默认 `false`，不影响现有调用。

**测试**：
- 3 个客户端 "client-abc", "client-def", "test-abc"，fuzzy 匹配 "abc" 返回 2 个候选
- 1 健康 1 不健康时，优先返回健康的
- 无匹配时返回 nil

### 2. 客户端踢除 API

**来源**：JsRpc 的 `DELETE /kick`

**改动文件**：
- `pkg/handler/group.go` — 新增 `HandleKickClient` 方法
- `pkg/handler/routes.go` — 注册路由
- `pkg/eventbus/events.go` — 新增 `EventClientKicked` 事件类型

**详细设计**：

```go
// HandleKickClient handles DELETE /business/kick
func (h *APIHandler) HandleKickClient(c *gin.Context) {
    group := c.Query("group")
    clientID := c.Query("clientId")

    if group == "" {
        BadRequest(c, "group parameter required")
        return
    }

    // 权限校验
    if !h.authorizeRegisteredGroupAccess(c, group) {
        return
    }

    rpcGroup := h.clientManager.GetGroup(group)
    if rpcGroup == nil {
        NotFound(c, "group not found")
        return
    }

    if clientID == "" {
        // 踢除整个组的所有客户端（逐个 Unregister，不用 Close 以免销毁 group goroutine）
        for _, c := range rpcGroup.GetAllClients() {
            rpcGroup.Unregister(c.ClientID)
        }
        OK(c, "all clients kicked from group")
        return
    }

    // 踢除单个客户端
    if !rpcGroup.HasClient(clientID) {
        NotFound(c, "client not found")
        return
    }

    rpcGroup.Unregister(clientID)

    // 发布事件
    if h.eventBus != nil {
        h.eventBus.Publish(eventbus.EventClientKicked, &eventbus.ClientKickedEvent{
            Group:    group,
            ClientID: clientID,
            Time:     time.Now(),
        })
    }

    OK(c, "client kicked")
}
```

路由注册：
```go
api.DELETE("/business/kick", h.HandleKickClient)
```

**事件类型**：
```go
const EventClientKicked EventType = "client.kicked"

type ClientKickedEvent struct {
    Group    string
    ClientID string
    Time     time.Time
}
```

**兼容性**：纯新增 API，不影响现有接口。

**测试**：
- 踢除存在的客户端，验证连接关闭
- 踢除不存在的客户端，返回 404
- 无权限时返回 403

### 3. 队列轮询策略

**来源**：Sekiro 的队列轮询（用后移到队尾）

**改动文件**：
- `pkg/client/group.go` — 修改 `allocate()` 方法

**详细设计**：

将 `allocate()` 从"遍历选择"改为"取队头健康客户端、移到队尾"：

```go
func (g *RpcGroup) allocate() *RpcClient {
    if len(g.order) == 0 {
        return nil
    }

    // 第一轮：找健康的在线客户端
    for i := 0; i < len(g.order); i++ {
        id := g.order[0]
        g.order = append(g.order[1:], id) // rotate

        client, ok := g.clients[id]
        if !ok {
            continue
        }
        if client.GetStatus() == StatusOnline && client.GetHealthStatus() {
            return client
        }
    }

    // 第二轮：找任意在线客户端
    for i := 0; i < len(g.order); i++ {
        id := g.order[0]
        g.order = append(g.order[1:], id)

        client, ok := g.clients[id]
        if !ok {
            continue
        }
        if client.GetStatus() == StatusOnline {
            return client
        }
    }

    // 兜底：返回第一个客户端
    if len(g.order) > 0 {
        return g.clients[g.order[0]]
    }
    return nil
}
```

**注意**：Router 的 `routeByRoundRobin` 保持不变（用计数器取模），它和 Group 的 `allocate()` 职责分离：
- Router 决定"用哪种策略"
- Group 的 `allocate()` 负责"在组内如何分配客户端"

当 Router 选择 RoundRobin 策略时，调用 `group.AllocateClient()` 而非自己遍历。

**兼容性**：纯服务端内部改动，对客户端和 API 接口完全透明。

**测试**：
- 3 个健康客户端，连续 allocate 6 次，验证顺序 A→B→C→A→B→C
- 2 个客户端，1 个不健康，验证总是分配到健康的
- 所有客户端不健康时，仍然能分配（退化行为）

### 4. 链路追踪 ID 贯穿

**来源**：Sekiro 的 `__invoke_trace_id`

**改动文件**：
- `pkg/websocket/handler.go` — `SendInvokeRequest` 接收并传递 trace_id
- `pkg/handler/invoke.go` — 生成 trace_id 并传递到 WS 层
- `pkg/websocket/handler.go` — `RpcMessage` 新增 `TraceID` 字段

**详细设计**：

`RpcMessage` 新增字段：
```go
type RpcMessage struct {
    // ...existing fields...
    TraceID string `json:"trace_id,omitempty"`
}
```

`SendInvokeRequest` 签名扩展：
```go
func (h *Handler) SendInvokeRequest(sekiroClient *client.RpcClient, sequence, group, clientID string, data []byte, traceID string) error {
    // ...
    fullMsg["trace_id"] = traceID
    // ...
}
```

调用方 `invoke.go` 中传递 trace_id：
```go
tid := traceID(c) // 复用 response.go 中已有的 helper，从 gin.Context 取 trace_id
if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, group, targetClient.ClientID, reqDataJSON, tid); err != nil {
    // ...
}
```

日志增强：关键日志点统一带 trace_id：
```go
logger.Infof("[trace=%s] Request sent: sequence=%s, group=%s, clientId=%s", traceID, sequence, group, targetClient.ClientID)
```

客户端回包时如果带了 `trace_id`，`handleInvokeResponse` 中记录日志并验证一致性。

**兼容性**：`trace_id` 在 WS 消息中是可选字段，老客户端不认识会忽略。

**测试**：
- 验证 invoke 请求的 WS 消息中包含 `trace_id`
- 验证 HTTP 响应中的 `trace_id` 与请求一致

---

## 阶段二：协议扩展 + 管理 UI

### 5. 协议检测（同端口多协议）

**来源**：Sekiro-open 的 `detector/` 模块

**新增文件**：
- `pkg/detector/detector.go` — 协议检测器
- `pkg/detector/http_matcher.go` — HTTP 协议匹配
- `pkg/detector/ws_matcher.go` — WebSocket 协议匹配
- `pkg/detector/sekiro_matcher.go` — Sekiro 二进制协议匹配

**详细设计**：

```go
type ProtocolDetector struct {
    matchers []ProtocolMatcher
}

type ProtocolMatcher interface {
    Name() string
    Match(firstBytes []byte) bool
}

// Peek 读取 TCP 连接的前 N 字节（不消费），交给 matcher 判断协议
// 根据结果将连接分发给对应的 handler
```

配置项：
```yaml
sekiro_protocol:
  enabled: false  # 默认关闭，不影响现有流量
```

开启后，在现有 Gin 引擎前加一层 TCP listener：
- 读取首字节 → 匹配协议 → HTTP/WS 继续走 Gin，Sekiro 二进制走 `pkg/protocol/` 解码器
- 默认关闭，不影响现有部署

### 6. Action 注册表增强

**来源**：Sekiro 的 `ActionHandler` + JsRpc 的 `_registerActions`

**改动文件**：
- DB migration：`group_actions` 表新增 `description` 和 `params_schema` 列
- `pkg/handler/` — 新增 action 查询 API
- `pkg/websocket/handler.go` — `handleBind` 扩展持久化 schema

**新增 API**：
```
GET /business/actions?group=xxx          # 列出组内所有 actions 及 schema
GET /business/actions?group=xxx&name=yyy # 查看单个 action 详情
```

可选增强：当 action 有 `params_schema` 时，invoke 请求自动校验参数格式，校验失败返回明确错误码。

### 7. React 管理平台增强

**改动文件**：`web/src/` 下的相关组件

新增功能：
- **客户端监控面板**：展示每个 group 下的客户端列表、健康状态、在线时长、已注册 actions
- **客户端操作**：踢除按钮（调用 `DELETE /business/kick`）、查看 actions 列表
- **Action 浏览器**：按 group 分组展示已注册 actions、参数 schema、快速测试按钮
- **链路追踪查看器**（可选第三阶段）：按 trace_id 查看完整调用链路

---

## 实施顺序

| 步骤 | 特性 | 改动文件数 | 依赖 |
|---|---|---|---|
| 1 | 队列轮询 | 1 (`group.go`) | 无 |
| 2 | 客户端模糊匹配 | 4 | 无 |
| 3 | 客户端踢除 API | 3 | 无 |
| 4 | 链路追踪 ID | 2 | 无 |
| 5 | 协议检测 | 4 (新增) | 无 |
| 6 | Action 注册表 | 3 + migration | 步骤 4 |
| 7 | 管理 UI 增强 | 多文件 | 步骤 1-6 的 API |

步骤 1-4 可独立开发、独立 PR、独立验证。步骤 5-7 按序推进。

## 不做的事情

- **execjs 远程执行 JS** — 需要客户端配合，本期不做
- **注解绑定模式** — 需要客户端 SDK 配合，本期不做
- **内嵌轻量控制台** — 用户选择增强现有 React SPA
- **多语言 SDK** — 工程量大，后续考虑
