# go-rpc 阶段一增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 go-rpc 服务端交付四个独立特性（队列轮询、客户端模糊匹配、客户端踢除 API、链路追踪 ID 贯穿），每个特性作为独立 PR，复用现有 actor-model 架构与统一响应信封。

**Architecture:** 四个特性均围绕 `pkg/client/group.go`（actor goroutine + channel）与 `pkg/handler/invoke.go`（业务转发入口）扩展。WebSocket 协议所有新增字段均带 `omitempty`，对老客户端透明。各 PR 之间互不依赖，可独立合入。

**Tech Stack:** Go 1.24, Gin, Gorilla WebSocket, PostgreSQL (GORM), actor-model goroutine + channel, `pkg/utils/traceid` context 注入。

**关键约定：**
- `RpcGroup` 所有对 `clients` map / `order` slice 的读写都在 `runLoop` goroutine 内串行化，新增命令类型只需追加到 `commandType` iota 块。
- `RpcClient.GetStatus()` / `GetHealthStatus()` 是带锁的读访问器；`StatusOnline` 表示客户端可服务。
- `traceid.FromContext(c.Request.Context())` 由中间件注入；`pkg/handler/response.go` 已有 `traceID(c)` helper。
- 所有 HTTP 响应使用 `OK()` / `Fail()` / `BadRequest()` / `NotFound()` / `Forbidden()` 等统一信封。

---

## 文件结构总览

| 文件路径 | 职责 | 涉及 PR |
|---|---|---|
| `pkg/client/group.go` | RpcGroup actor：命令分发、allocate、fuzzy 查找 | PR-1, PR-2 |
| `pkg/client/group_test.go` | RpcGroup 单元测试 | PR-1, PR-2 |
| `pkg/router/strategy.go` | Router：策略选择（RoundRobin / Specified / Hash） | PR-2 |
| `pkg/handler/invoke.go` | APIHandler：invoke / groupList / clientQueue / kick 处理 | PR-2, PR-3, PR-4 |
| `pkg/handler/invoke_test.go` | APIHandler 单元测试 | PR-3 |
| `pkg/websocket/handler.go` | WS Handler：消息收发、SendInvokeRequest 签名 | PR-4 |
| `pkg/handler/chat.go` | chat 业务调用 SendInvokeRequest | PR-4 |
| `pkg/handler/qwen.go` | qwen 业务调用 SendInvokeRequest | PR-4 |
| `pkg/eventbus/events.go` | 事件类型与结构定义 | PR-3 |
| `main.go` | 业务路由注册（`/business/*`） | PR-3 |

---

### Task 1: 队列轮询分配（PR-1）

将 `RpcGroup.allocate()` 从"遍历选第一个健康"改为"取队头、用后旋转到队尾"，实现 Sekiro 风格的队列轮询。

**Files:**
- Modify: `go-rpc/pkg/client/group.go:114-137` （`allocate()` 方法）
- Modify: `go-rpc/pkg/client/group_test.go:65-92` （`TestRpcGroup_AllocateClient`）

- [ ] **Step 1: 在 group_test.go 追加三个队列轮询测试**

在 `TestRpcGroup_HasClient` 之后追加以下三个测试函数（不改动已有测试，只追加）：

```go
func TestRpcGroup_AllocateClient_RoundRobinOrder(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	for _, id := range []string{"A", "B", "C"} {
		c := NewRpcClient("test-group", id, nil)
		c.SetStatus(StatusOnline)
		group.Register(c)
	}

	// 前 3 次：A → B → C（每次取队头、旋转到队尾）
	for _, want := range []string{"A", "B", "C"} {
		got := group.AllocateClient()
		if got == nil || got.ClientID != want {
			t.Fatalf("expected %s, got %v", want, got)
		}
	}
	// 再来一轮验证循环：A → B → C
	for _, want := range []string{"A", "B", "C"} {
		got := group.AllocateClient()
		if got == nil || got.ClientID != want {
			t.Fatalf("second round: expected %s, got %v", want, got)
		}
	}
}

func TestRpcGroup_AllocateClient_SkipsUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c1 := NewRpcClient("test-group", "A", nil)
	c1.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c1.MarkFailure() // 触发熔断器打开
	}
	group.Register(c1)

	c2 := NewRpcClient("test-group", "B", nil)
	c2.SetStatus(StatusOnline)
	group.Register(c2)

	// A 不健康，总是轮到 B
	for i := 0; i < 3; i++ {
		got := group.AllocateClient()
		if got == nil || got.ClientID != "B" {
			t.Fatalf("iteration %d: expected B, got %v", i, got)
		}
	}
}

func TestRpcGroup_AllocateClient_FallbackToUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c1 := NewRpcClient("test-group", "A", nil)
	c1.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c1.MarkFailure()
	}
	group.Register(c1)

	c2 := NewRpcClient("test-group", "B", nil)
	c2.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c2.MarkFailure()
	}
	group.Register(c2)

	// 所有客户端都不健康，但仍能分配（兜底行为）
	got := group.AllocateClient()
	if got == nil {
		t.Fatal("expected a fallback client, got nil")
	}
	if got.ClientID != "A" && got.ClientID != "B" {
		t.Fatalf("unexpected client: %s", got.ClientID)
	}
}
```

- [ ] **Step 2: 运行新增测试，验证失败**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/client -run 'TestRpcGroup_AllocateClient_(RoundRobinOrder|SkipsUnhealthy|FallbackToUnhealthy)' -v
```

预期：`TestRpcGroup_AllocateClient_RoundRobinOrder` 失败（旧 allocate 不保证顺序，可能拿到 B 或 C 而非 A）；`SkipsUnhealthy` 和 `FallbackToUnhealthy` 可能通过，但不影响下一步。

- [ ] **Step 3: 重写 group.go 的 allocate() 方法**

用以下实现替换 `pkg/client/group.go:114-137` 的 `allocate()` 方法（保留 `// allocate` 注释风格，其余精确替换）：

```go
// allocate 从 order 队头取可用客户端、用后旋转到队尾，实现队列轮询。
// 三轮优先级：健康且在线 → 任意在线 → 任意客户端。
// 仅在实际分配时旋转；未命中的轮次不改变队列顺序。
func (g *RpcGroup) allocate() *RpcClient {
	if len(g.order) == 0 {
		return nil
	}

	// 第一轮：健康且在线
	for i := 0; i < len(g.order); i++ {
		id := g.order[i]
		client, ok := g.clients[id]
		if !ok {
			continue
		}
		if client.GetStatus() == StatusOnline && client.GetHealthStatus() {
			if i > 0 {
				g.order = append(g.order[i+1:], g.order[:i+1]...)
			}
			return client
		}
	}

	// 第二轮：任意在线
	for i := 0; i < len(g.order); i++ {
		id := g.order[i]
		client, ok := g.clients[id]
		if !ok {
			continue
		}
		if client.GetStatus() == StatusOnline {
			if i > 0 {
				g.order = append(g.order[i+1:], g.order[:i+1]...)
			}
			return client
		}
	}

	// 兜底：返回队列第一个客户端
	return g.clients[g.order[0]]
}
```

- [ ] **Step 4: 运行所有 group 测试验证通过**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/client -v
```

预期：所有 `TestRpcGroup_*` 测试通过，包括原有的 `TestRpcGroup_AllocateClient`（"空组返回 nil"、"只返回在线客户端"）和新增的三个测试。

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd D:/crawler-rpc/go-rpc
go test ./...
```

预期：无失败。`pkg/router` 的 RoundRobin 仍走计数器取模路径，不受影响。

- [ ] **Step 6: 提交**

```bash
cd D:/crawler-rpc/go-rpc
git add pkg/client/group.go pkg/client/group_test.go
git commit -m "feat(client): queue round-robin allocation with tail rotation"
```

**验收：**
- 3 个健康客户端连续 6 次 allocate 产生 A→B→C→A→B→C 序列
- 混合健康/不健康时优先返回健康客户端
- 所有客户端不健康时兜底仍能分配
- 现有 `TestRpcGroup_AllocateClient` 与 `TestHandleInvoke_RoundRobinSelectsDifferentClients` 不受影响

---

### Task 2: 客户端模糊匹配（PR-2）

在 invoke 请求上支持 `fuzzy=true`，按 ClientID 子串匹配候选客户端，健康优先 + 多个候选时随机选择。

**Files:**
- Modify: `go-rpc/pkg/client/group.go` （新增 cmdFuzzyFind 命令 + FindClientByFuzzy 方法）
- Modify: `go-rpc/pkg/client/group_test.go` （新增模糊匹配测试）
- Modify: `go-rpc/pkg/router/strategy.go:29-44,76-103` （RouteParams 加 Fuzzy 字段，Route 加 fuzzy 分支）
- Modify: `go-rpc/pkg/handler/invoke.go:66-74,238-260,287-290` （InvokeRequest/InvokeBuilder/RequestBuilder 加 Fuzzy）

- [ ] **Step 1: 在 group_test.go 追加模糊匹配测试**

在文件末尾追加：

```go
func TestRpcGroup_FindClientByFuzzy_HealthFirst(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	abcUnhealthy := NewRpcClient("test-group", "client-abc-1", nil)
	abcUnhealthy.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		abcUnhealthy.MarkFailure()
	}
	group.Register(abcUnhealthy)

	abcHealthy := NewRpcClient("test-group", "client-abc-2", nil)
	abcHealthy.SetStatus(StatusOnline)
	group.Register(abcHealthy)

	other := NewRpcClient("test-group", "client-def", nil)
	other.SetStatus(StatusOnline)
	group.Register(other)

	// 模糊匹配 "abc" 应该命中 abc-1 和 abc-2，但优先返回健康的 abc-2
	got := group.FindClientByFuzzy("abc")
	if got == nil {
		t.Fatal("expected a fuzzy match, got nil")
	}
	if got.ClientID != "client-abc-2" {
		t.Errorf("expected healthy match client-abc-2, got %s", got.ClientID)
	}

	// 不匹配任何客户端
	if group.FindClientByFuzzy("xyz") != nil {
		t.Error("expected nil for non-matching substring")
	}
}

func TestRpcGroup_FindClientByFuzzy_FallbackToUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c := NewRpcClient("test-group", "only-unhealthy", nil)
	c.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c.MarkFailure()
	}
	group.Register(c)

	got := group.FindClientByFuzzy("unhealthy")
	if got == nil {
		t.Fatal("expected fallback to unhealthy client, got nil")
	}
	if got.ClientID != "only-unhealthy" {
		t.Errorf("expected only-unhealthy, got %s", got.ClientID)
	}
}

func TestRpcGroup_FindClientByFuzzy_EmptyGroup(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	if group.FindClientByFuzzy("anything") != nil {
		t.Error("expected nil for empty group")
	}
}
```

- [ ] **Step 2: 运行新增测试，验证编译失败**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/client -run 'TestRpcGroup_FindClientByFuzzy' -v
```

预期：编译失败，`group.FindClientByFuzzy undefined`。

- [ ] **Step 3: 在 group.go 添加 cmdFuzzyFind 命令与 FindClientByFuzzy 方法**

3.1 在 `pkg/client/group.go` 顶部文件头追加 `"math/rand"` import（与现有 `"errors"`、`"sync"` 并列）。

3.2 在 `commandType` iota 块中追加 `cmdFuzzyFind`（紧跟 `cmdAllocate` 之后）：

```go
const (
	cmdRegister commandType = iota
	cmdUnregister
	cmdGetClient
	cmdGetAllClients
	cmdAllocate
	cmdFuzzyFind
)
```

3.3 在 `handleCommand` 的 switch 末尾追加 `cmdFuzzyFind` 分支（紧接 `case cmdAllocate` 之后）：

```go
	case cmdFuzzyFind:
		cmd.callback <- commandResult{client: g.fuzzyFind(cmd.clientID)}
```

3.4 在 `allocate()` 方法之后新增 `fuzzyFind()` 私有方法：

```go
// fuzzyFind 按 ClientID 子串匹配候选客户端：健康且在线优先，多个候选时随机选择。
// 无健康候选时退化为任意在线候选；无在线候选时返回 nil。
func (g *RpcGroup) fuzzyFind(substr string) *RpcClient {
	var healthy []*RpcClient
	var online []*RpcClient

	for id, c := range g.clients {
		if !strings.Contains(id, substr) {
			continue
		}
		if c.GetStatus() != StatusOnline {
			continue
		}
		online = append(online, c)
		if c.GetHealthStatus() {
			healthy = append(healthy, c)
		}
	}

	if len(healthy) > 0 {
		return healthy[rand.Intn(len(healthy))]
	}
	if len(online) > 0 {
		return online[rand.Intn(len(online))]
	}
	return nil
}
```

3.5 在文件末尾（`ErrNoClientAvailable` 之前或之后）追加公开方法：

```go
// FindClientByFuzzy finds a client whose ClientID contains substr. 已关停时返回 nil。
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

3.6 确认 import 块包含 `"strings"`（与 `"errors"`、`"sync"`、`"math/rand"` 并列）。

- [ ] **Step 4: 运行 group 测试验证通过**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/client -v
```

预期：所有 `TestRpcGroup_FindClientByFuzzy_*` 通过；原有测试不受影响。

- [ ] **Step 5: 扩展 RouteParams 与 Router.Route**

5.1 在 `pkg/router/strategy.go` 的 `RouteParams` struct 中追加 `Fuzzy` 字段（在 `Payload interface{}` 之后）：

```go
	// Fuzzy enables substring matching on ClientID when true.
	// Only effective when ClientID is also non-empty.
	Fuzzy bool
```

5.2 修改 `Route()` 方法，把 "1. If ClientID is specified" 分支替换为：

```go
	// 1. If ClientID is specified, choose between exact and fuzzy lookup.
	if params.ClientID != "" {
		if params.Fuzzy {
			return group.FindClientByFuzzy(params.ClientID)
		}
		return r.routeBySpecifiedClient(group, params.ClientID)
	}
```

- [ ] **Step 6: 扩展 InvokeRequest / InvokeBuilder / RequestBuilder**

6.1 在 `pkg/handler/invoke.go` 的 `InvokeRequest` struct 中追加字段（在 `Stream bool` 之后）：

```go
	Fuzzy          bool        `json:"fuzzy,omitempty"`
```

6.2 在 `RequestBuilder` interface 中追加方法（在 `IsStream() bool` 之后）：

```go
	IsFuzzy() bool
```

6.3 在 `InvokeBuilder` struct 中追加字段（在 `Stream bool` 之后）：

```go
	Fuzzy          bool
```

6.4 修改 `newInvokeBuilder` 函数，在返回的 `&InvokeBuilder{...}` 中追加初始化：

```go
		Fuzzy:          req.Fuzzy,
```

6.5 在 `InvokeBuilder` 的 getter 块中追加方法（在 `IsStream() bool` 之后）：

```go
func (b *InvokeBuilder) IsFuzzy() bool              { return b.Fuzzy }
```

6.6 修改 `selectTargetClient` 的签名和 body，把 `clientID` 之后追加 `fuzzy bool` 参数，并在构造 `RouteParams` 时透传：

```go
func (h *APIHandler) selectTargetClient(groupName, clientID string, fuzzy bool, constantInvoke, action string, payload interface{}) (*client.RpcClient, error) {
	group := h.clientManager.GetGroup(groupName)
	if group == nil {
		if clientID != "" {
			return nil, fmt.Errorf("group %s not found", groupName)
		}
		return nil, nil
	}

	params := router.RouteParams{GroupName: groupName, ClientID: clientID, Fuzzy: fuzzy}
	if clientID == "" {
		params.ConstantInvoke = constantInvoke
		params.Action = action
		params.Payload = payload
	}

	selected := h.router.Route(group, params)
	if selected == nil {
		if clientID != "" {
			return nil, fmt.Errorf("client %s not found in group %s", clientID, groupName)
		}
		return nil, nil
	}

	if clientID != "" {
		logger.Infof("Route selected: strategy=specified, group=%s, clientId=%s, fuzzy=%v", groupName, selected.ClientID, fuzzy)
	} else {
		logger.Debugf("Route selected: group=%s, clientId=%s", groupName, selected.ClientID)
	}
	return selected, nil
}
```

6.7 修改 `handleForwardRequest` 中调用 `selectTargetClient` 的那一行（大约在 "BuildRequestData 错误延迟" 注释之后），把 `clientID` 后面追加 `builder.IsFuzzy()`：

```go
	targetClient, err := h.selectTargetClient(group, clientID, builder.IsFuzzy(), constantInvoke, reqAction, reqParams)
```

6.8 修改 `invokeRequestFromQuery` 函数（`parseBoolQuery` 附近），在返回的 struct 中追加：

```go
		Fuzzy:          parseBoolQuery(c.Query("fuzzy")),
```

6.9 修改 `bindInvokeRequest`，在 `if !req.Stream { ... }` 块之后追加对 query 中 fuzzy 的兜底读取（与 stream 同样处理）：

```go
	if !req.Fuzzy {
		if v := c.Query("fuzzy"); v != "" {
			req.Fuzzy = parseBoolQuery(v)
		}
	}
```

- [ ] **Step 7: 运行 handler 测试验证编译与行为**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/handler -v
```

预期：现有 invoke_test.go 全部通过；`selectTargetClient` 签名变更只影响内部调用，不会破坏外部测试。

- [ ] **Step 8: 运行全量测试**

```bash
cd D:/crawler-rpc/go-rpc
go test ./...
```

预期：无失败。

- [ ] **Step 9: 提交**

```bash
cd D:/crawler-rpc/go-rpc
git add pkg/client/group.go pkg/client/group_test.go pkg/router/strategy.go pkg/handler/invoke.go
git commit -m "feat: fuzzy client matching by ClientID substring with health priority"
```

**验收：**
- `POST /business/invoke` 携带 `{"group":"g","clientId":"abc","fuzzy":true}` 走模糊匹配
- `GET /business/invoke?group=g&clientId=abc&fuzzy=1` 同上（query 兼容）
- 健康候选优先；多个候选时随机选择
- 无匹配时返回 `no client available` 错误
- `fuzzy=false` 或缺省时保持原有精确匹配行为

---

### Task 3: 客户端踢除 API（PR-3）

新增 `DELETE /business/kick` 端点，支持踢除单个客户端或整个组的所有客户端，并发布 `client.kicked` 事件。

**Files:**
- Modify: `go-rpc/pkg/handler/invoke.go:29-37,76-102` （APIHandler 新增 eventBus 字段与 HandleKickClient 方法）
- Modify: `go-rpc/pkg/eventbus/events.go:6-16,72-79` （新增 EventClientKicked 与 ClientKickedEvent）
- Modify: `go-rpc/pkg/handler/invoke_test.go` （新增 HandleKickClient 测试）
- Modify: `go-rpc/main.go:373-379` （注册新路由）

- [ ] **Step 1: 在 events.go 追加事件类型与结构**

在 `pkg/eventbus/events.go` 的事件类型常量块中追加一行（紧跟 `EventInvokerDestroy` 之后）：

```go
	EventClientKicked                 = "client.kicked"
```

在文件末尾追加结构体定义：

```go
// ClientKickedEvent 客户端被踢除事件
type ClientKickedEvent struct {
	Group    string
	ClientID string // 为空时表示整组踢除
	Time     time.Time
}
```

- [ ] **Step 2: 在 invoke_test.go 追加 HandleKickClient 测试**

在文件末尾追加：

```go
func TestHandleKickClient_Single(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c := client.NewRpcClient("g1", "c1", nil)
	c.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c)

	handler := newTestAPIHandler(mockManager)
	handler.eventBus = eventbus.NewEventBus()

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick?group=g1&clientId=c1", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d, body=%s", w.Code, w.Body.String())
	}

	// 客户端应被注销
	if mockManager.GetClient("g1", "c1") != nil {
		t.Error("expected client to be unregistered after kick")
	}
}

func TestHandleKickClient_GroupNotFound(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())
	handler.eventBus = eventbus.NewEventBus()

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick?group=missing&clientId=c1", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// group not found 应返回 404
	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

func TestHandleKickClient_MissingGroup(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}
```

追加 import 至文件头 import 块：

```go
	"github.com/mrh30000/go-rpc/pkg/eventbus"
```

- [ ] **Step 3: 运行新增测试，验证编译失败**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/handler -run 'TestHandleKickClient' -v
```

预期：编译失败（`handler.HandleKickClient undefined`、`eventBus` 字段未定义）。

- [ ] **Step 4: 在 invoke.go 扩展 APIHandler**

4.1 在 `APIHandler` struct 中追加字段（在 `groupRepo repository.GroupRepository` 之后）：

```go
	eventBus         *eventbus.EventBus
```

4.2 在 `NewAPIHandler` 函数体的 `h := &APIHandler{...}` 字面量中追加初始化（在 `groupRepo: groupRepo,` 之后）：

```go
		eventBus:         eventBus,
```

- [ ] **Step 5: 在 invoke.go 追加 HandleKickClient 方法**

在 `HandleInvoke` 方法附近（建议紧跟 `HandleClientQueue` 之后）追加：

```go
// HandleKickClient handles DELETE /business/kick
//
// Query 参数:
//   - group (required): 目标分组
//   - clientId (optional): 目标客户端；为空时踢除整个分组的所有客户端
func (h *APIHandler) HandleKickClient(c *gin.Context) {
	groupName := c.Query("group")
	if groupName == "" {
		BadRequest(c, "group parameter required")
		return
	}
	if !h.authorizeRegisteredGroupAccess(c, groupName) {
		return
	}

	rpcGroup := h.clientManager.GetGroup(groupName)
	if rpcGroup == nil {
		NotFound(c, "group not found")
		return
	}

	clientID := c.Query("clientId")
	if clientID == "" {
		// 整组踢除：逐个 Unregister，避免 Close() 销毁 group goroutine
		for _, c := range rpcGroup.GetAllClients() {
			rpcGroup.Unregister(c.ClientID)
		}
		if h.eventBus != nil {
			h.eventBus.Publish(eventbus.EventClientKicked, &eventbus.ClientKickedEvent{
				Group:    groupName,
				ClientID: "",
				Time:     time.Now(),
			})
		}
		OK(c, "all clients kicked from group")
		return
	}

	if !rpcGroup.HasClient(clientID) {
		NotFound(c, "client not found")
		return
	}

	rpcGroup.Unregister(clientID)

	if h.eventBus != nil {
		h.eventBus.Publish(eventbus.EventClientKicked, &eventbus.ClientKickedEvent{
			Group:    groupName,
			ClientID: clientID,
			Time:     time.Now(),
		})
	}

	OK(c, "client kicked")
}
```

- [ ] **Step 6: 运行 handler 测试验证通过**

```bash
cd D:/crawler-rpc/go-rpc
go test ./pkg/handler -run 'TestHandleKickClient' -v
```

预期：三个 `TestHandleKickClient_*` 测试全部通过。

- [ ] **Step 7: 在 main.go 注册路由**

在 `main.go` 的 `business := s.optionalAuthGroup("/business")` 块中，在 `business.GET("/register", s.handleRegister)` 之后追加：

```go
		business.DELETE("/kick", s.apiHandler.HandleKickClient)
```

- [ ] **Step 8: 运行全量测试**

```bash
cd D:/crawler-rpc/go-rpc
go test ./...
```

预期：无失败。

- [ ] **Step 9: 提交**

```bash
cd D:/crawler-rpc/go-rpc
git add pkg/eventbus/events.go pkg/handler/invoke.go pkg/handler/invoke_test.go main.go
git commit -m "feat(api): add DELETE /business/kick for client eviction"
```

**验收：**
- `DELETE /business/kick?group=g1&clientId=c1` 踢除单个客户端，连接被关闭
- `DELETE /business/kick?group=g1` 踢除整组所有客户端（group goroutine 保持存活，可接受新连接）
- 未认证/无权限时由 `authorizeRegisteredGroupAccess` 返回 401/403
- `EventClientKicked` 事件被 EventBus 发布

---

### Task 4: 链路追踪 ID 贯穿（PR-4）

把中间件已注入到 Gin context 的 `trace_id` 透传到 WebSocket invoke 消息与客户端回包日志，便于端到端调用链定位。

**Files:**
- Modify: `go-rpc/pkg/websocket/handler.go:58-71,516-553` （RpcMessage 加 TraceID 字段，SendInvokeRequest 签名加 traceID）
- Modify: `go-rpc/pkg/handler/invoke.go:366-380,399-445` （forwardStream / dispatchInvokeRequest 传递 traceID）
- Modify: `go-rpc/pkg/handler/chat.go:174,217` （chat 业务传递空 traceID）
- Modify: `go-rpc/pkg/handler/qwen.go:164,277,413` （qwen 业务传递空 traceID）

- [ ] **Step 1: 在 handler.go 扩展 RpcMessage**

在 `pkg/websocket/handler.go` 的 `RpcMessage` struct 中，把 `Timestamp int64` 改为在其后追加 `TraceID` 字段：

```go
type RpcMessage struct {
	Type          MessageType     `json:"type"`
	Sequence      string          `json:"sequence,omitempty"`
	RpcSeq        string          `json:"__sekiro_seq__,omitempty"`
	Group         string          `json:"group,omitempty"`
	ClientID      string          `json:"clientId,omitempty"`
	Actions       []string        `json:"actions,omitempty"`
	ActionSchemas []ActionSchema  `json:"actionSchemas,omitempty"`
	Data          json.RawMessage `json:"data,omitempty"`
	Error         string          `json:"error,omitempty"`
	Status        int             `json:"status,omitempty"`
	Done          bool            `json:"done,omitempty"`
	Timestamp     int64           `json:"timestamp,omitempty"`
	TraceID       string          `json:"trace_id,omitempty"`
}
```

- [ ] **Step 2: 修改 SendInvokeRequest 签名与 body**

把 `pkg/websocket/handler.go` 的 `SendInvokeRequest` 函数签名从：

```go
func (h *Handler) SendInvokeRequest(sekiroClient *client.RpcClient, sequence, group, clientID string, data []byte) error {
```

改为：

```go
func (h *Handler) SendInvokeRequest(sekiroClient *client.RpcClient, sequence, group, clientID string, data []byte, traceID string) error {
```

在函数体中 `fullMsg["timestamp"] = time.Now().UnixMilli()` 之后追加：

```go
	if traceID != "" {
		fullMsg["trace_id"] = traceID
	}
```

在函数体中 `logger.Infof("Sending invoke message")` 替换为：

```go
	if traceID != "" {
		logger.Infof("Sending invoke message: trace=%s", traceID)
	} else {
		logger.Infof("Sending invoke message")
	}
```

- [ ] **Step 3: 修改 handleInvokeResponse 增加 trace_id 日志**

在 `pkg/websocket/handler.go` 的 `handleInvokeResponse` 方法中，把现有的：

```go
	logger.Infof("Invoke response received: sequence=%s, status=%d, Error=%s", sequence, msg.Status, errorMessage)
```

替换为：

```go
	if msg.TraceID != "" {
		logger.Infof("Invoke response received: trace=%s, sequence=%s, status=%d, Error=%s", msg.TraceID, sequence, msg.Status, errorMessage)
	} else {
		logger.Infof("Invoke response received: sequence=%s, status=%d, Error=%s", sequence, msg.Status, errorMessage)
	}
```

- [ ] **Step 4: 修改 invoke.go 的两个调用点**

4.1 在 `forwardStream` 方法中，把 `h.wsHandler.SendInvokeRequest(...)` 调用（在 `RegisterStream` 之后那一行）改为：

```go
	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, group, targetClient.ClientID, reqDataJSON, traceID(c)); err != nil {
```

4.2 在 `dispatchInvokeRequest` 方法中，把 `h.wsHandler.SendInvokeRequest(...)` 调用改为：

```go
	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, group, targetClient.ClientID, reqDataJSON, traceID(c)); err != nil {
```

注意：`dispatchInvokeRequest` 没有直接访问 `*gin.Context`。需要把 traceID 作为新参数透传：

- 修改 `dispatchInvokeRequest` 签名，在 `timeout time.Duration` 之后追加 `traceID string`：

```go
func (h *APIHandler) dispatchInvokeRequest(
	c *gin.Context,
	group string,
	targetClient *client.RpcClient,
	sequence string,
	reqDataJSON []byte,
	timeout time.Duration,
	traceID string,
) (*forwarder.InvokeResponse, bool) {
```

- 在 `dispatchInvokeRequest` 内部把 `h.wsHandler.SendInvokeRequest(...)` 的最后一个参数改成这个新形参 `traceID`。

- 在 `forwardUnary` 中调用 `dispatchInvokeRequest` 时追加 `traceID(c)`：

```go
	resp, ok := h.dispatchInvokeRequest(c, group, targetClient, sequence, reqDataJSON, timeout, traceID(c))
```

- [ ] **Step 5: 修改 chat.go 的两个调用点（占位传空串）**

在 `pkg/handler/chat.go` 的 `handleChatCompletionNonStream` 与 `handleChatCompletionStream` 方法中，把 `h.wsHandler.SendInvokeRequest(...)` 的调用末尾追加空串参数：

```go
	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, req.Group, targetClient.ClientID, reqDataJSON, ""); err != nil {
```

（两处都这样改）

- [ ] **Step 6: 修改 qwen.go 的三个调用点（占位传空串）**

在 `pkg/handler/qwen.go` 的 `qwenCreateChat`、`qwenStreamToOpenAI`、`qwenAggregateToOpenAI` 方法中，把 `h.wsHandler.SendInvokeRequest(...)` 的调用末尾追加空串参数：

```go
	if err := h.wsHandler.SendInvokeRequest(target, seq, qwenGroup, target.ClientID, reqJSON, ""); err != nil {
```

（三处都这样改）

- [ ] **Step 7: 运行全量测试**

```bash
cd D:/crawler-rpc/go-rpc
go test ./...
```

预期：所有测试通过。`websocket/stream_test.go` 等若直接调用 `SendInvokeRequest` 需要同样追加空串参数（如有编译错误请同步修复，传空串即可）。

- [ ] **Step 8: 提交**

```bash
cd D:/crawler-rpc/go-rpc
git add pkg/websocket/handler.go pkg/handler/invoke.go pkg/handler/chat.go pkg/handler/qwen.go
git commit -m "feat(tracing): propagate trace_id through invoke WebSocket messages"
```

**验收：**
- 调用 `POST /business/invoke` 时，发出的 WS invoke 消息包含 `trace_id` 字段（与 HTTP 响应中的 `trace_id` 一致）
- 客户端回包若带 `trace_id`，服务端日志按 `trace=<id>` 输出
- chat / qwen 业务路径不受影响（传空串，WS 消息中不带 `trace_id`）
- 老客户端不认识 `trace_id` 字段会忽略，行为不变

---

## 自检清单

实施完四个 PR 后，运行以下最终验证：

```bash
cd D:/crawler-rpc/go-rpc
go test ./...          # 全量测试
go build ./...         # 编译
go vet ./...           # 静态分析
```

功能回归：
- [ ] 3 个健康客户端连续 invoke 6 次，观察日志 clientId 字段呈现 A→B→C→A→B→C 轮询
- [ ] 用 `fuzzy=true` + 子串 clientId 调 invoke，能命中匹配的客户端
- [ ] 调 `DELETE /business/kick?group=...` 后，被踢客户端的 WS 连接关闭
- [ ] invoke HTTP 响应中的 `trace_id` 与 WS 消息中的 `trace_id` 一致
