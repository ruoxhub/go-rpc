# pkg/ 目录结构重构设计

## 背景

当前 `pkg/` 目录存在以下结构性问题：

1. **依赖方向错误**：`pkg/client/`（客户端 SDK）导入了 `pkg/server/transport/`，客户端包不应依赖服务端包。
2. **`pkg/server/` 过于庞大**：72 个 Go 文件分布在 12 个子包中，其中 `api/`（16 文件）和 `handlers/`（18 文件）职责重叠。
3. **重复定义**：`DefaultGroupActions` 在 `handlers/constants.go` 和 `websocket/handler.go` 各定义一份；`handlers/response.go` 和 `api/response.go` 有重叠的响应结构体。
4. **utils 分散**：根目录 `utils/` 和 `pkg/utils/` 并存。
5. **入口点与文档不符**：`agents.md` 提到 `cmd/server/main.go`，实际入口在根目录 `main.go`。

## 目标

- 修复依赖方向问题，客户端 SDK 不依赖任何服务端包
- 拆分 `pkg/server/` 大包，子包平铺到 `pkg/` 下
- 合并 `api/` 和 `handlers/` 为统一的 HTTP 处理层
- 消除重复代码定义
- 统一目录布局和导入规则
- 为未来扩展预留合理结构

## 方案选型

评估了 3 种方案：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A. 扁平化 | 子包直接平铺到 `pkg/` 下 | 改动最小，Go 社区惯用 | `pkg/` 下包数较多（18 个） |
| B. 分层分组 | 引入 `pkg/core/` + `pkg/server/` 两层 | 层次分明 | 嵌套更深，导入路径变长 |
| C. 领域导向 | 按业务域分组（infra/data/rpc/admin/gateway） | 语义清晰 | 边界模糊，迁移成本最高 |

**选定方案 A（扁平化）**。理由：每个包职责已单一明确，无需额外分组层；Go 标准库和知名项目（k8s、docker）倾向扁平结构；改动量最小。

## 新目录结构

```
pkg/
├── protocol/              二进制协议编解码（不变）
│   ├── packet.go
│   ├── packet_type.go
│   └── bufwriter.go
│
├── compress/              压缩层（不变）
│   ├── gzip.go
│   ├── snappy.go
│   ├── none.go
│   └── manager.go
│
├── model/                 数据模型（不变 + 新增 group.go）
│   ├── database.go
│   ├── alert.go
│   ├── trace.go
│   ├── openai.go
│   └── group.go           新增：DefaultGroupActions 常量
│
├── eventbus/              事件总线（不变）
│   ├── eventbus.go
│   └── events.go
│
├── database/              数据库初始化 + repository/（不变）
│   ├── database.go
│   └── repository/
│
├── transport/             从 server/transport/ 提升
│   ├── connection.go
│   ├── tcp_conn.go
│   └── ws_conn.go
│
├── client/                从 server/client/ 移入（服务端客户端管理）
│   ├── client.go          RpcClient
│   ├── group.go           RpcGroup (actor model)
│   └── manager.go         ClientManager
│
├── client/sdk/            原 pkg/client/ 下沉为 SDK 子包
│   ├── client.go          RpcClient (TCP 客户端)
│   └── invoker.go         RpcInvoker
│
├── config/                从 server/config/ 移入
│   └── service.go
│
├── flow/                  从 server/flow/ 移入
│   ├── backoff.go
│   └── ratelimit.go
│
├── forwarder/             从 server/forwarder/ 移入
│   ├── timeout.go
│   └── streamframe.go
│
├── middleware/             从 server/middleware/ 移入
│   ├── auth.go
│   ├── auth_cache.go
│   ├── logging.go
│   ├── trace.go
│   └── ratelimit.go
│
├── router/                从 server/router/ 移入
│   ├── hash.go
│   └── strategy.go
│
├── alert/                 从 server/alert/ 移入
│   ├── evaluator.go
│   └── notifier.go
│
├── metrics/               从 server/metrics/ 移入
│   └── collector.go
│
├── handler/               合并 server/api/ + server/handlers/
│   ├── routes.go          统一路由注册（含 http_server.go 的 Gin engine 配置）
│   ├── invoke.go          RPC 调用接口（原 api/handlers.go）
│   ├── chat.go            OpenAI 兼容接口（原 api/chat_completions.go）
│   ├── qwen.go            Qwen 专用接口（原 api/qwen.go）
│   ├── stream.go          流式 holdback 状态机（原 api/stream_holdback.go）
│   ├── websocket.go       WebSocket 升级（原 api/websocket.go）
│   ├── response.go        统一响应格式（合并 api/response.go + handlers/response.go）
│   ├── login.go           登录注册（原 handlers/login.go）
│   ├── user.go            用户管理（原 handlers/user.go）
│   ├── group.go           分组管理（原 handlers/group.go）
│   ├── alert.go           告警管理（原 handlers/alert.go）
│   ├── metric.go          指标查询（原 handlers/metric.go）
│   ├── trace.go           链路追踪（原 handlers/trace.go）
│   ├── sysconfig.go       系统配置（原 handlers/sysconfig.go）
│   ├── anonymous.go       匿名分组（原 handlers/anonymous.go）
│   ├── authz.go           授权辅助（原 handlers/authz.go）
│   ├── audit.go           审计日志（原 handlers/audit.go）
│   ├── constants.go       共享常量（原 handlers/constants.go）
│   ├── handlers_test.go   原 api/handlers_test.go
│   ├── chat_test.go       原 api/chat_completions_test.go
│   ├── qwen_test.go       原 api/qwen_test.go
│   ├── websocket_test.go  原 api/websocket_test.go
│   ├── routes_test.go     原 api/http_server_test.go
│   └── login_test.go      原 handlers/register_test.go
│
│   注：handler/websocket.go（WebSocket 升级）与 pkg/websocket/handler.go（WebSocket 消息处理）
│   分属不同包，无命名冲突。前者处理 HTTP→WS 升级，后者处理 WS 连接上的消息循环。
│
├── websocket/             从 server/websocket/ 移入
│   └── handler.go
│
├── utils/                 合并 pkg/utils/ + 根目录 utils/
│   ├── password/
│   ├── traceid/
│   ├── code.go
│   └── file.go
│
```

## 依赖规则

### 分层约束（只能向下依赖）

```
第 0 层（叶子包，无内部依赖）
  protocol, model, eventbus, transport, flow, utils

第 1 层（仅依赖第 0 层）
  compress    → protocol
  database    → model
  config      → database
  forwarder   → (无内部依赖)

第 2 层（依赖第 0-1 层）
  client      → transport, eventbus
  middleware  → database, config, flow, utils/traceid
  router      → client
  alert       → database
  metrics     → database

第 3 层（依赖第 0-2 层）
  websocket   → database, eventbus, client, forwarder, transport
  handler     → database, eventbus, client, config, forwarder,
                metrics, middleware, router, websocket, utils/password

第 4 层（组合根）
  main.go     → 所有包（组装入口）
```

### 关键约束

1. `client/sdk/`（SDK 包）只能依赖第 0 层：protocol、compress、transport，不允许依赖任何服务端包。
2. `handler/` 是最上层消费者，可以依赖所有其他包，但不被其他包依赖（除 main.go）。
3. 禁止循环依赖：任何包不得直接或间接依赖自身。
4. `transport/` 是独立基础设施，不依赖 protocol、model 或任何上层包。

## Handler 合并策略

### 路由注册统一

```go
// handler/routes.go
func SetupRoutes(engine *gin.Engine, deps *Dependencies) {
    // 公开 RPC 接口（无需认证）
    rpc := engine.Group("/rpc-api")
    registerRpcRoutes(rpc, deps)

    // OpenAI 兼容接口
    v1 := engine.Group("/v1")
    registerV1Routes(v1, deps)

    // Qwen 专用接口
    qwen := engine.Group("/api")
    registerQwenRoutes(qwen, deps)

    // WebSocket
    engine.GET("/ws", deps.wsHandler.HandleUpgrade)

    // 管理后台（需认证）
    admin := engine.Group("/api").Use(deps.authMiddleware.Authenticate)
    registerAdminRoutes(admin, deps)
}
```

### 响应格式统一

合并前有 4 种响应结构体（`BusinessResponse`、`BusinessExtraResponse`、`Response`、`RpcApiResponse`），合并后精简为 3 种，并统一字段类型：

```go
// handler/response.go

// ApiResponse 管理后台 API 响应（用于 /api/* 管理端点）
// 保留原 handlers/Response 的 Total 字段用于分页
type ApiResponse struct {
    Code    int         `json:"code"`
    Message string      `json:"message"`
    Data    interface{} `json:"data,omitempty"`
    Total   int64       `json:"total,omitempty"`
}

// RpcResponse RPC 调用响应（用于 /rpc-api/* 和 /business/* 对外接口）
// 统一原 api/BusinessResponse 和 handlers/RpcApiResponse（两者字段完全相同）
// 前端 Login.jsx 依赖 status === 0 判断成功，类型必须为 int
type RpcResponse struct {
    Status  int         `json:"status"`
    Message string      `json:"message"`
    Data    interface{} `json:"data,omitempty"`
}

// RpcExtraResponse RPC 调用响应（带分组和客户端信息）
// 保留原 api/BusinessExtraResponse 的扩展字段
type RpcExtraResponse struct {
    Status   int         `json:"status"`
    Message  string      `json:"message"`
    Group    string      `json:"group,omitempty"`
    ClientID string      `json:"clientId,omitempty"`
    Data     interface{} `json:"data,omitempty"`
}
```

- 管理后台统一用 `ApiResponse`（code/message/data/total）
- 对外 RPC 接口统一用 `RpcResponse`（status/message/data），消除 `BusinessResponse` 与 `RpcApiResponse` 的重复定义
- 需要返回分组/客户端信息的场景用 `RpcExtraResponse`

## 重复代码消除

### DefaultGroupActions

将 `DefaultGroupActions` 从 `handlers/constants.go` 和 `websocket/handler.go` 移到 `pkg/model/group.go`（新增文件），handler 和 websocket 均从 model 读取，避免反向依赖。

### utils 合并

根目录 `utils/`（code.go, file.go）移入 `pkg/utils/`，消除两个 utils 包并存的混乱。

### login.go 全局 DB 访问

`handlers/login.go` 中直接调用 `database.GetDB()` 的独立函数改为通过 Repository 接口注入，与其他 handler 保持一致。

## 入口点调整

将 `pkg/server/bootstrap.go` 的组装逻辑合并到 `main.go`，删除 `pkg/server/` 目录。`main.go` 承担组合根职责：CLI flag 解析、配置加载、组件组装、服务启动。

## 文件变更清单

| 操作 | 原路径 | 新路径 |
|------|--------|--------|
| 移动 | `pkg/server/transport/*` | `pkg/transport/` |
| 移动 | `pkg/server/client/*` | `pkg/client/` |
| 移动 | `pkg/client/*` | `pkg/client/sdk/` |
| 移动 | `pkg/server/config/*` | `pkg/config/` |
| 移动 | `pkg/server/flow/*` | `pkg/flow/` |
| 移动 | `pkg/server/forwarder/*` | `pkg/forwarder/` |
| 移动 | `pkg/server/middleware/*` | `pkg/middleware/` |
| 移动 | `pkg/server/router/*` | `pkg/router/` |
| 移动 | `pkg/server/alert/*` | `pkg/alert/` |
| 移动 | `pkg/server/metrics/*` | `pkg/metrics/` |
| 移动+合并 | `pkg/server/api/*` + `pkg/server/handlers/*` | `pkg/handler/` |
| 移动 | `pkg/server/websocket/*` | `pkg/websocket/` |
| 移动 | `utils/*`（根目录） | `pkg/utils/` |
| 合并到 main | `pkg/server/bootstrap.go` | `main.go` |
| 新增 | — | `pkg/model/group.go` |
| 删除 | `pkg/server/` 目录 | — |

## 迁移步骤

按依赖层次从底层到顶层逐步迁移，每步完成后 `go build ./...` 和 `go test ./...` 验证：

1. `transport/` 提升到 `pkg/transport/`，修复 `client/sdk/` 导入路径
2. `utils/` 合并到 `pkg/utils/`
3. `client SDK` 移到 `pkg/client/sdk/`
4. `server/client/` 移到 `pkg/client/`
5. `config/` `flow/` `forwarder/` 提升
6. `middleware/` `router/` `alert/` `metrics/` 提升
7. `server/websocket/` 移到 `pkg/websocket/`
8. `api/` + `handlers/` 合并为 `pkg/handler/`
9. 消除重复代码（DefaultGroupActions、response 统一、login.go 注入化）
10. `bootstrap.go` 合并到 `main.go`，删除 `pkg/server/`

## 测试策略

- 现有测试随文件一起移动，只修改 import 路径，不改变测试逻辑
- 不新增功能或测试
- 每步迁移后立即编译和运行测试验证
- 最终运行 `go vet ./...` 检查静态分析
