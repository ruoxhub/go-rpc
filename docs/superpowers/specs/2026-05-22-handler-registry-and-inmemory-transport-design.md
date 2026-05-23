# 设计文档：管理端 Handler 泛型注册器 + InMemoryTransport

- **日期**：2026-05-22
- **批次**：P0 第一批（PRD `docs/2026-05-12-prd.md` 中 P0 两项）
- **状态**：Spec 草案待审阅
- **范围**：PRD 中 `泛型 handler 注册器（统一 API 层）` + `InMemoryTransport（测试基础设施）` 两项

## 0. 上下文

`docs/2026-05-12-prd.md` 列出了基于 MCP Go SDK 的 10 项借鉴改进，按 P0-P3 划分。本批锁定 P0 两项，对应到本仓库的真实痛点：

- **管理端 14 个 handler 文件**（`pkg/server/handlers/*.go`）每个 handler 在重写"绑定 → 校验 → 调 repo → model→VO 映射 → 响应"模板，最痛的是 `for ... append(vos, VO{...})` 字段映射循环
- **集成测试**仅有 `httptest.NewRecorder` 单层 mock，覆盖不到 WS 主链路的 register → invoke → response 端到端流程

PRD 中两条描述与现状有偏差，落实修正：

1. PRD "WebSocket 通信耦合在 handler.go，没有 Transport 抽象" → 实际 `pkg/server/transport/Connection` 接口及 `tcp_conn.go` / `ws_conn.go` 已经存在。本批新增 `inmemory_conn.go` 即可，**不动接口**
2. PRD "invoke 用 map[string]any" → 实际 `InvokeRequest` 是强类型 struct（`pkg/server/api/handlers.go:58-66`），`Params interface{}` 是为透传业务参数，**不需要重做**

## 1. 目标与非目标

### 目标（必须达成，可量化）

| 维度 | 当前基线 | 目标 |
|---|---|---|
| 管理端 handler 重复代码 | 14 文件，list/CRUD 平均 25-40 行模板 | 每个 handler ≤ 10 行 |
| 列表查询 model→VO 映射 | 每 list handler 手写 `for...append` 10-30 行 | 一个 mapper 函数即可 |
| 类型安全 | `c.ShouldBindJSON(&req)` 后才知道结构 | 注册时声明 `Req`/`Resp` 类型，编译时检查 |
| client↔server 集成测试 | 仅 `httptest.NewRecorder` 单层 mock | `transport.NewInMemoryPair()` 让 register→invoke→response 全链路无网络可测 |
| handler 单测覆盖率 | `pkg/server/handlers/` 仅 `register_test.go` | 关键 handler（user/group/alert）至少 1 个 happy path + 1 个错误路径 |

### 非目标（明确不做）

1. **不动业务端** `pkg/server/api/handlers.go`（已有 `RequestBuilder` 抽象）
2. **不动鉴权/审计/限流**（继续靠 middleware 和显式调用，不塞进泛型注册器）
3. **不引入 OpenAPI/Swagger 自动生成**（属 P2，下一批）
4. **不做错误码体系重构**（属 P1，下一批；本批仅复用现有 `Response{Code,Message,Data,Total}`）
5. **不扩展 Transport 多协议支持**（QUIC/gRPC 不在本批；只补 InMemory 实现）
6. **不重构现有 `mockConn`**（保持兼容；InMemory 是新增对等实现）

### 不变量（硬约束）

- `pkg/server/handlers/response.go` 函数签名字节不变
- `pkg/server/transport/Connection` 接口字节不变
- `pkg/server/handlers/routes.go` 字节不变
- 所有 handler 函数签名仍是 `func(*gin.Context)`，路由调用点零变化
- 所有对外 JSON 响应字段名/类型/嵌套不变（前端零改动）

### 三板斧总结

> 用两个泛型工具消除 handler 模板，用一对内存管道消除集成测试的网络依赖。

## 2. 架构与文件布局

```
pkg/server/handlers/
├── registry.go               [新增]  泛型工具 BindAndCall / BindQueryAndCall / ListAndMap + sentinel error
├── registry_test.go          [新增]  泛型工具单测
├── response.go               [保留]  Response/Success/Error 不动
├── alert.go                  [改写]  迁移到泛型工具
├── group.go                  [改写]  部分迁移（事务 handler 保留）
├── user.go                   [改写]  部分迁移（GetCurrentUser 用 gin.H 不迁）
├── trace.go / metric.go / sysconfig.go / anonymous.go / login.go  [改写]
├── audit.go / authz.go / constants.go / routes.go                 [不动]
└── integration_test.go       [新增]  端到端 register→invoke→response 测试

pkg/server/transport/
├── connection.go             [保留]  Connection 接口不动
├── tcp_conn.go / ws_conn.go  [保留]
├── inmemory_conn.go          [新增]  InMemoryConnection + NewInMemoryPair
└── inmemory_conn_test.go     [新增]  7 项不变量测试

pkg/server/websocket/
└── handler.go                [改]    新增 HandleConnection(ctx, transport.Connection) 入口

pkg/client/
└── client.go                 [改]    新增 NewRpcClientWithConn 测试入口
```

### 两个泛型工具的接口契约

```go
// pkg/server/handlers/registry.go
package handlers

import "github.com/gin-gonic/gin"

// BindAndCall 处理带 body 的写操作（POST/PUT/DELETE）。
// 流程: ShouldBindJSON → 调 fn → Success(data) / Error
//   - 绑定失败 → BadRequest(err.Error())
//   - fn 返回 *HTTPError → Error(c, code, message)
//   - fn 返回 ErrHandled → 不写响应（fn 已自行 c.JSON）
//   - fn 返回其他 error → InternalError(err.Error())
func BindAndCall[Req any, Resp any](
    c *gin.Context,
    fn func(c *gin.Context, req Req) (Resp, error),
)

// BindQueryAndCall 处理带 Query 参数的读操作（GET 详情/单查询）。
// 流程: ShouldBindQuery → 调 fn → Success(data) / Error
func BindQueryAndCall[Req any, Resp any](
    c *gin.Context,
    fn func(c *gin.Context, req Req) (Resp, error),
)

// ListAndMap 处理列表查询 + model→VO 映射 + 总数。
// 流程: ShouldBindQuery(req) → query(req) → mapper 映射每个 item → SuccessWithTotal
//   - query 签名严格要求 func(Req) ([]Item, int64, error)
//   - 空列表保证序列化为 []，不为 null
func ListAndMap[Req any, Item any, VO any](
    c *gin.Context,
    query func(req Req) ([]Item, int64, error),
    mapper func(Item) VO,
)
```

### Sentinel Error 与 HTTPError

```go
var ErrHandled = errors.New("response already written by handler")

type HTTPError struct {
    Code    int
    Message string
}

func (e *HTTPError) Error() string { return e.Message }

func NewHTTPError(code int, message string) *HTTPError { return &HTTPError{Code: code, Message: message} }

func ErrBadRequest(msg string) error  { return NewHTTPError(400, msg) }
func ErrUnauthorized(msg string) error { return NewHTTPError(401, msg) }
func ErrForbidden(msg string) error   { return NewHTTPError(403, msg) }
func ErrNotFound(msg string) error    { return NewHTTPError(404, msg) }
func ErrConflict(msg string) error    { return NewHTTPError(409, msg) }
```

注册器内用 `errors.As` 解包 `*HTTPError`，兼容 `fmt.Errorf("...: %w", err)` 多层 wrap。

### InMemoryConnection 契约

```go
// pkg/server/transport/inmemory_conn.go
// NewInMemoryPair 返回一对相互连接的 Connection。
// 任何一端 Send 的数据，会成为另一端 Receive 的输入。
//
// 保证：
//   - a.Send → b.Receive；b.Send → a.Receive（双向独立）
//   - 任一端 Close 后，对端 Receive 返回 io.EOF
//   - Send 是带缓冲非阻塞的（缓冲 64）
//   - 并发安全：可以多 goroutine 同时 Send/Receive
//   - 数据隔离：Send 内部拷贝切片，对端不受调用方后续修改影响
func NewInMemoryPair() (Connection, Connection)
```

实现要点：每个实例两条 channel（inbound/outbound）+ `sync.Once` 关闭 + Send 内部 `copy()` 隔离切片。

## 3. 横切关注点：鉴权 / 审计 / 事务 / 错误共存

| 关注点 | 处理方式 |
|---|---|
| 用户/管理员鉴权 | 已在 `routes.go` 由 middleware 处理，handler 进入时已有 user，泛型工具不感知 |
| 资源级鉴权（如分组所有权） | fn 内显式调 `authorizeGroupAccess(c, ...)`，失败返回 `ErrForbidden` 或 `ErrHandled`（如已自行写响应） |
| 当前用户取用 | fn 内调 `middleware.GetCurrentUser(c)` |
| 审计日志 | fn 成功路径末尾调 `auditXxx(c, ...)` |
| DB 事务 | 跨多 repo 调用的 handler 不迁移（如 `group.go:Delete`） |
| 字段级校验 | `binding:"required"` 标签 |
| 跨字段校验 | fn 内显式调（如 `validateAlertOperator`），失败返回 `ErrBadRequest` |
| 业务错误（已存在/找不到） | `ErrConflict("...")` / `ErrNotFound("...")` |

### 三种典型迁移模式

**模式 1：纯 CRUD**（理想态）
```go
func (h *UserHandler) Add(c *gin.Context) {
    BindAndCall(c, h.add)
}

func (h *UserHandler) add(c *gin.Context, req AddUserRequest) (int64, error) {
    count, err := h.userRepo.CountByUserName(req.UserName)
    if err != nil {
        return 0, fmt.Errorf("count user: %w", err)
    }
    if count > 0 {
        return 0, ErrBadRequest("user already exists")
    }
    // ... 业务逻辑
    return user.ID, nil
}
```

**模式 2：带资源鉴权 + 审计**
```go
func (h *AlertHandler) UpdateAlertRule(c *gin.Context) {
    BindAndCall(c, h.updateAlertRule)
}

func (h *AlertHandler) updateAlertRule(c *gin.Context, req UpdateAlertRuleRequest) (*model.AlertRule, error) {
    if req.Operator != nil && !isValidOperator(*req.Operator) {
        return nil, ErrBadRequest("非法的操作符...")
    }
    rule, err := h.alertRepo.FindRuleByID(req.ID)
    if err != nil || rule == nil {
        return nil, ErrNotFound("规则不存在")
    }
    // ... 字段更新
    if err := h.alertRepo.UpdateRule(rule); err != nil {
        return nil, fmt.Errorf("update rule: %w", err)
    }
    if h.evaluator != nil {
        h.evaluator.ReloadRules()
    }
    return rule, nil
}
```

**模式 3：列表 + VO 映射**
```go
func (h *AlertHandler) GetAlertRules(c *gin.Context) {
    ListAndMap(c,
        h.alertRepo.FindRulesByQuery,  // func(model.AlertRuleQuery) ([]model.AlertRule, int64, error)
        toAlertRuleVO,                  // func(model.AlertRule) AlertRuleVO
    )
}
```

**模式 4：不迁移**（保留原状，详见附录 A）
- `user.go:GetCurrentUser`：返回 `gin.H{...}` 动态拼接
- `user.go:RefreshToken`：返回 `gin.H{...}`
- `group.go:Delete`：跨 repo DB 事务
- `group.go:GetDetail`：返回 `gin.H{...}`
- `login.go:Login` / `Logout`：写 cookie + token + 多步流程

### 迁移可行性盘点

| 文件 | handler 数 | 可迁移 | 不迁移 |
|---|---|---|---|
| user.go | 7 | 5 | 2（GetCurrentUser/RefreshToken） |
| group.go | 9 | 6 | 3（Delete/GetDetail + 1 待定） |
| alert.go | 6 | 6 | 0 |
| trace.go / metric.go / sysconfig.go / anonymous.go | 估 18-20 | 估 13-15 | 估 5 |
| login.go | 估 4-5 | 部分 | 部分 |
| **合计** | **~45-50** | **~30-35** | **~10-15** |

迁移率目标 ≥ 65%。

## 4. InMemoryConnection 实现 + 端到端集成测试

### 实现选型

匹配现有 `Connection` 的消息级语义。每方向一条独立 channel，`sync.Once` 保证幂等关闭。

```go
type inMemoryConn struct {
    inbound   chan []byte
    outbound  chan []byte
    closed    chan struct{}
    closeOnce sync.Once
    addr      string
}

func (c *inMemoryConn) Send(data []byte) error {
    select {
    case <-c.closed:
        return errors.New("connection closed")
    default:
    }
    buf := make([]byte, len(data))
    copy(buf, data)
    select {
    case c.outbound <- buf:
        return nil
    case <-c.closed:
        return errors.New("connection closed")
    }
}

func (c *inMemoryConn) Receive() ([]byte, error) {
    select {
    case msg, ok := <-c.inbound:
        if !ok {
            return nil, io.EOF
        }
        return msg, nil
    case <-c.closed:
        select {
        case msg, ok := <-c.inbound:
            if !ok {
                return nil, io.EOF
            }
            return msg, nil
        default:
            return nil, io.EOF
        }
    }
}

func (c *inMemoryConn) Close() error {
    c.closeOnce.Do(func() {
        close(c.closed)
        close(c.outbound)
    })
    return nil
}

func (c *inMemoryConn) RemoteAddr() string { return c.addr }

func NewInMemoryPair() (Connection, Connection) {
    aToB := make(chan []byte, 64)
    bToA := make(chan []byte, 64)
    a := &inMemoryConn{inbound: bToA, outbound: aToB, closed: make(chan struct{}), addr: "inmemory-A"}
    b := &inMemoryConn{inbound: aToB, outbound: bToA, closed: make(chan struct{}), addr: "inmemory-B"}
    return a, b
}
```

### 7 项不变量测试

| # | 不变量 | 测试用例 |
|---|---|---|
| 1 | a.Send 字节按序到达 b.Receive | `TestInMemoryPair_Order` 连发 100 条带序号消息 |
| 2 | a.Close 后 b.Receive 返回 `io.EOF` | `TestInMemoryPair_CloseSignalsEOF` |
| 3 | 关闭后 a.Send 返回 error | `TestInMemoryPair_SendAfterClose` |
| 4 | 多 goroutine 并发 Send 不丢/不串扰 | `TestInMemoryPair_ConcurrentSend` 4×250 |
| 5 | Send 内部拷贝（修改原切片不影响对端） | `TestInMemoryPair_DataIsolation` |
| 6 | 双向独立：a 关闭不影响 b→a 之外的方向 | `TestInMemoryPair_DirectionalClose` |
| 7 | 重复 Close 不 panic | `TestInMemoryPair_DoubleClose` |

### 端到端集成测试样板

```go
// pkg/server/handlers/integration_test.go
func TestEndToEnd_RegisterAndInvoke(t *testing.T) {
    serverConn, clientConn := transport.NewInMemoryPair()

    manager := client.NewClientManager()
    timeoutMgr := forwarder.NewTimeoutManager(nil)
    wsHandler := ws.NewHandler(manager, timeoutMgr, nil, nil)
    defer wsHandler.Shutdown()

    go wsHandler.HandleConnection(context.Background(), serverConn)

    rpcClient := client.NewRpcClientWithConn("test-group", "client-1", clientConn)
    go rpcClient.RunReadLoop()

    sendRegister(t, clientConn, "test-group", "client-1")

    require.Eventually(t, func() bool {
        return len(manager.GetClientsByGroup("test-group")) == 1
    }, time.Second, 10*time.Millisecond)

    // 模拟 invoke：API 层 → wsHandler.SendInvokeRequest → 客户端读到 → 客户端 Send 响应 → API 收到
    // ...
}
```

### 配套子任务

| 子任务 | 文件 | 说明 |
|---|---|---|
| `ws.Handler.HandleConnection(ctx, transport.Connection)` | `pkg/server/websocket/handler.go` | 不感知 `*websocket.Conn`，只走 transport 接口 |
| `client.NewRpcClientWithConn(group, clientID, conn)` | `pkg/client/client.go` | 测试入口；不发起拨号，直接挂接已存在的 conn |

集成测试**不引入** sqlite/dockertest，只跑 register/invoke 主链路。鉴权依赖测试继续走 `handlers_test.go` 的 mock 路径。

## 5. 迁移计划与回归策略

### 6-commit 阶段化拆分（单 PR 内）

```
阶段 1：地基（独立无依赖）
  commit 1: feat(transport): 新增 InMemoryConnection + 7 项不变量测试
  commit 2: feat(handlers): 新增泛型注册器 BindAndCall/ListAndMap + 单测

阶段 2：横切支撑
  commit 3: feat(ws): ws.Handler 增加 HandleConnection(ctx, Connection) 入口
  commit 4: feat(client): pkg/client 增加 NewRpcClientWithConn 测试入口
  commit 5: test: 新增端到端集成测试 register→invoke→response

阶段 3：批量迁移
  commit 6: refactor(handlers): 14 文件迁移到泛型注册器（按文件分块）
```

### 迁移顺序（commit 6 内部）

| 序 | 文件 | 复杂度 | 备注 |
|---|---|---|---|
| 1 | `alert.go` | 低 | 最干净的 CRUD，做样板 |
| 2 | `user.go` | 中 | GetCurrentUser/RefreshToken 不迁 |
| 3 | `metric.go` | 低 | 只读 + 映射 |
| 4 | `trace.go` | 低 | 只读 |
| 5 | `sysconfig.go` | 中 | 含日志查询 |
| 6 | `anonymous.go` | 中 | 含转换分组 |
| 7 | `group.go` | 高 | Delete 用事务、GetDetail 用 gin.H 不迁 |
| 8 | `login.go` | 高 | cookie/token 多保留原状 |

### 回归命令（每 commit 必跑，输出留档）

```bash
go test -race -count=1 ./pkg/server/... -v
go test -race -count=1 ./pkg/client/... -v
go vet ./...
go build ./...
```

### 前端兼容性手工抽查

**执行时机**：commit 6（批量迁移）完成后、PR 合并前。
**执行人**：实施者本人。
**输出物**：抽查截图或文字记录贴到 PR 描述里。

启动 `./sekiro-server -c config.yaml` + `cd web && npm run dev`，登录后命中 `/users`、`/groups`、`/groups/:name`、`/alerts/rules`、`/traces` 5 个页面，确认无 JSON 解析错误、字段缺失、列表空白。

抽查 1 个 POST（创建分组）+ 1 个 PUT（更新 QPS）+ 1 个 DELETE（删告警规则），确认成功 + 失败两种路径。

### Golden test（curl byte-for-byte 对比）作为 follow-up，不在本批

### 撤退按钮

| 风险点 | 回滚 |
|---|---|
| 整个 PR 出问题 | revert 整个 PR |
| 阶段 1 OK 但阶段 3 个别文件翻车 | revert commit 6 的具体文件，保留 registry 工具 |
| 集成测试不稳定 | 用 build tag `//go:build integration` 隔离 |

### 工作量

| 阶段 | 工时 |
|---|---|
| 阶段 1 | 0.5 天 |
| 阶段 2 | 0.5 天 |
| 阶段 3 | 1.5 天 |
| 测试 + 前端联调 | 0.5 天 |
| **合计** | **3 天** |

### 阻塞与依赖

| 依赖 | 状态 |
|---|---|
| Go ≥ 1.18（泛型） | ✅ `go.mod` 显示 `go 1.25.0` |
| `transport.Connection` 接口稳定 | ✅ 已存在 |
| `ws.Handler` 内部读写循环可参数化 | ⚠️ plan 阶段读 `pkg/server/websocket/handler.go` 验证 |
| 现有 handler 单测 | ⚠️ 仅 `register_test.go`，本批必须补 alert/user 关键用例 |

## 6. 验收清单与闭环复盘

### 功能验收（PR 合并前必须全绿）

- [ ] `pkg/server/handlers/registry.go` 提供 `BindAndCall` / `BindQueryAndCall` / `ListAndMap` 三个泛型工具
- [ ] `registry.go` 提供 `ErrHandled` + `HTTPError` + 5 个便捷构造函数（`ErrBadRequest/ErrNotFound/ErrConflict/ErrForbidden/ErrUnauthorized`）
- [ ] `pkg/server/transport/inmemory_conn.go` 提供 `NewInMemoryPair() (Connection, Connection)`
- [ ] `pkg/server/websocket/handler.go` 暴露 `HandleConnection(ctx, transport.Connection)`
- [ ] `pkg/client/client.go` 暴露 `NewRpcClientWithConn(group, clientID, conn)`
- [ ] 14 个 handler 文件迁移完成，迁移率 ≥ 65%
- [ ] 不能迁移的 handler 在内部注释说明原因，并列入本 spec 的"不迁移清单"

### 量化指标

| 指标 | 测量方式 | 目标 |
|---|---|---|
| 管理端 handler 平均行数 | `wc -l pkg/server/handlers/*.go` 改造前后对比（除 registry.go） | ↓ ≥ 30% |
| `vos = append(vos, ...)` 出现次数 | grep 计数 | ↓ ≥ 60% |
| `pkg/server/handlers` 单测覆盖率 | `go test -cover` | ≥ 50% |
| `pkg/server/transport` 单测覆盖率 | `go test -cover` | ≥ 80% |
| 端到端集成测试用例数 | `TestEndToEnd_*` 计数 | ≥ 1 |

### 回归证据（粘贴在 PR 描述里，无证据 = 不通过）

```bash
go test -race -count=1 ./... -v 2>&1 | tail -40
go vet ./... 2>&1
go build ./... 2>&1
go test -cover ./pkg/server/handlers/... ./pkg/server/transport/...
```

### 不变量自审

- [ ] `pkg/server/handlers/response.go` 字节未改
- [ ] `pkg/server/transport/connection.go` 字节未改
- [ ] `pkg/server/handlers/routes.go` 字节未改
- [ ] 所有 handler 函数签名仍是 `func(*gin.Context)`
- [ ] 所有对外 JSON 字段名/类型/嵌套未变

### 闭环复盘 SOP（PR 合并后 3 天内必做）

按复盘四步法：

1. **回顾目标**：把 §1 目标表格逐条标 ✅/⚠️/❌
2. **评估结果**：实际 vs 预期，列偏差原因
3. **分析原因**：哪些迁移比预期容易/卡住？集成测试发现了哪些之前漏掉的 bug？
4. **抽 SOP**：输出 `docs/handlers-migration-playbook.md`（≤ 150 行）：
   - 四种迁移模式判定流程图
   - sentinel error cheat sheet
   - InMemoryPair 集成测试样板代码
   - "迁移完成"自检清单

### 风险登记册

| 风险 | 等级 | 触发条件 | 应对 |
|---|---|---|---|
| Go 版本 < 1.18 | 阻塞 | `go.mod` < 1.18 | ✅ 已确认 1.25.0，不触发 |
| InMemoryPair 压测下死锁 | 中 | 缓冲塞满 + 双向同时阻塞 | 提供 `WithBufferSize(int)` option；测试加 `-timeout 30s` |
| sentinel error 被 wrap 后丢失 | 中 | 迁移者用 `%v` 而非 `%w` | Playbook 强调 `%w`；registry 内 `errors.As` 兼容多层 wrap |
| 前端断言 `data == null` vs `[]` | 中 | 列表为空时 `Response.Data` 序列化差异 | 改造前后 curl 对比；`ListAndMap` 内部确保返回 `[]` |
| PR review 卡壳 | 低 | review 周期 > 3 天 | 6-commit 拆分；最坏抽 commit 1+2 单独先合 |

### 三板斧总结

> 本批 P0 用两个泛型工具消除 handler 模板，用一对内存管道消除集成测试网络依赖，量化指标 + 闭环 SOP 让收益可验证、可复用。

## 附录 A：本批不迁移清单（实施时按文件维护）

| handler | 不迁移原因 |
|---|---|
| `user.go:GetCurrentUser` | 返回 `gin.H{...}` 动态字段 |
| `user.go:RefreshToken` | 返回 `gin.H{"apiToken": ...}` 动态字段 |
| `group.go:Delete` | 跨 repo DB 事务（Devices + Actions + Group） |
| `group.go:GetDetail` | 返回 `gin.H{...}` 动态字段 |
| `login.go:Login` | 写 cookie + token + 多步流程 |
| `login.go:Logout` | 无 body，写 cookie |

## 附录 B：术语

- **Handler**：本文档中专指 `pkg/server/handlers/*.go` 中的管理端 HTTP handler
- **VO**：View Object，handler 返回给前端的 DTO（区别于 `pkg/model/` 的 DB 实体）
- **Sentinel error**：预定义的特殊错误值，用于 fn 与注册器之间通信
- **InMemoryPair**：本设计新增的一对相互连接的 `transport.Connection`
