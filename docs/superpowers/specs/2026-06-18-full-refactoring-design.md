# go-rpc 全面重构设计文档

**日期**: 2026-06-18
**方案**: 方案 A — 安全优先 + 逐模块渐进
**兼容性要求**: 完全向后兼容（API 路由、请求/响应格式、SDK 接口不变）
**测试要求**: 每步必测

---

## 1. 背景与问题清单

通过 GitNexus + CodeGraph 深度分析，识别出以下 6 大类问题：

### 1.1 安全问题
| ID | 问题 | 位置 | 风险 |
|----|------|------|------|
| S1 | WebSocket CheckOrigin 无条件返回 true | `pkg/handler/http_server.go:57` | 高 |
| S2 | CORS 空白名单 = 允许所有来源 + Credentials | `pkg/middleware/cors.go:39` | 高 |
| S3 | Token 可通过 query 参数传递，URL 日志泄露 | `pkg/middleware/auth.go:98` | 中 |
| S4 | 登录接口无独立限流，可暴力枚举 | `pkg/handler/login.go` | 中 |

### 1.2 并发安全问题
| ID | 问题 | 位置 | 风险 |
|----|------|------|------|
| C1 | RateLimiter.Stop select+default 非原子，double-close panic | `pkg/flow/ratelimit.go:41-47` | 高 |
| C2 | auth_cache GC goroutine 无 stop channel，进程退出时泄漏 | `pkg/middleware/auth_cache.go:87-95` | 中 |
| C3 | SDK Client readLoop 每包起 goroutine，无上限 | `pkg/client/sdk/client.go:102` | 中 |

### 1.3 资源管理问题
| ID | 问题 | 位置 | 风险 |
|----|------|------|------|
| R1 | Shutdown 未关闭 gorm.DB 底层连接池 | `main.go:586-618` | 中 |
| R2 | TimeoutManager.Shutdown 无 sync.Once，double-close panic | `pkg/forwarder/timeout.go:308` | 中 |
| R3 | database.go 混用 log.Printf 和 logger | `pkg/database/database.go:115,127,146` | 低 |

### 1.4 架构问题
| ID | 问题 | 位置 | 风险 |
|----|------|------|------|
| A1 | 全局可变状态：DB 单例、包级 cache、atomic pointer | 多文件 | 高 |
| A2 | Handler 依赖注入不一致：包级 Set 函数 vs 构造函数注入 | `handler/*.go` | 中 |
| A3 | middleware 通过包级全局变量持有依赖 | `middleware/auth.go` | 中 |

### 1.5 测试缺口
WebSocket handler、middleware ratelimit/trace、alert evaluator、forwarder 等关键路径无测试覆盖。

### 1.6 索引健康
GitNexus FTS 全文搜索索引缺失，索引落后 HEAD 2 个 commit。

---

## 2. 总体策略

按风险从高到低分 5 个阶段推进，每阶段独立可验证、可发布。

```
阶段1: 安全修复 → 阶段2: 并发修复 → 阶段3: 资源管理
  → 阶段4: 架构统一（DI 重构）→ 阶段5: 测试补齐 + 索引
```

---

## 3. 阶段 1：安全修复

### 3.1 WebSocket CheckOrigin 收紧 (S1)

**文件**: `pkg/handler/http_server.go`

**改动**: 将 `CheckOrigin` 从无条件 `true` 改为复用 `sameOriginOrNoOrigin()` + CORS 白名单双重检查。开发环境通过 `HTTPConfig.LocalDebug` 放行。

```go
CheckOrigin: func(r *http.Request) bool {
    if cfg.LocalDebug { return true }
    return sameOriginOrNoOrigin(r)
}
```

**测试**: `http_server_test.go` — `TestCheckOrigin_SameOrigin`、`TestCheckOrigin_CrossOrigin`、`TestCheckOrigin_NoOrigin`、`TestCheckOrigin_LocalDebug`。

### 3.2 CORS 空名单行为修正 (S2)

**文件**: `pkg/middleware/cors.go`

**改动**: `isOriginAllowed()` 空名单时返回 `false`（禁止跨域），显式配置 `"*"` 才放行所有来源。

```go
func isOriginAllowed(origin string, whitelist []string) bool {
    if len(whitelist) == 0 { return false }
    for _, w := range whitelist {
        if w == "*" || w == origin { return true }
    }
    return false
}
```

**向后兼容注意**: 当前生产部署若依赖空名单 = 全放行行为，需配置 `CORS_ORIGINS` 环境变量。在 `.env.example` 中添加说明。

**测试**: `cors_test.go` — `TestCORS_EmptyWhitelist`、`TestCORS_StarWildcard`、`TestCORS_ExactMatch`、`TestCORS_NoMatch`。

### 3.3 Token 查询参数废弃 (S3)

**文件**: `pkg/middleware/auth.go`

**改动**: `ExtractAuthTokenFromRequest` 新增 `allowQueryToken bool` 参数，默认 `false`。通过 `sys_config` 表配置 `ALLOW_QUERY_TOKEN` 控制。query token 提取时输出废弃警告日志。

**向后兼容注意**: 使用 query token 的客户端需迁移到 header 方式，或临时开启配置。

**测试**: `auth_test.go` — `TestExtractToken_HeaderBearer`、`TestExtractToken_QueryDisabled`、`TestExtractToken_QueryEnabled`、`TestExtractToken_FormParam`。

### 3.4 登录接口限流 (S4)

**文件**: `pkg/middleware/login_ratelimit.go`（新增）

**改动**: 新增 `LoginRateLimitMiddleware()`，按 IP 限流 5 QPS。在 `routes.go` 的 `/api/login` 路由上注册。

**测试**: `login_ratelimit_test.go` — `TestLoginRateLimit_AllowsNormalTraffic`、`TestLoginRateLimit_BlocksExcessive`、`TestLoginRateLimit_IsolatesByIP`。

---

## 4. 阶段 2：并发修复

### 4.1 RateLimiter.Stop sync.Once (C1)

**文件**: `pkg/flow/ratelimit.go`

**改动**: 新增 `stopOnce sync.Once` 字段，`Stop()` 改为 `stopOnce.Do(func() { close(rl.stopChan) })`。

**测试**: `ratelimit_test.go` — `TestRateLimiter_StopConcurrent`（100 goroutine 并发 Stop，无 panic）、`TestRateLimiter_StopIdempotent`。

### 4.2 auth_cache GC goroutine 可停止 (C2)

**文件**: `pkg/middleware/auth_cache.go`

**改动**: `cache[T]` 新增 `stopChan chan struct{}` + `stopOnce sync.Once`。`gcLoop()` 改为 `select` 监听 `stopChan`。新增 `Stop()` 方法和包级 `ShutdownCaches()` 函数。`main.go` 的 `Shutdown()` 中调用 `middleware.ShutdownCaches()`。

**测试**: `auth_cache_test.go` — `TestCache_GCStopsOnSignal`、`TestCache_StopIdempotent`。

### 4.3 SDK Client 同步处理 (C3)

**文件**: `pkg/client/sdk/client.go`

**改动**: `readLoop()` 中移除 `go c.handlePacket(packet)`，改为同步调用。heartbeat 直接在 readLoop 内处理。

**测试**: `client_test.go` — `TestReadLoop_SequentialProcessing`、`TestReadLoop_NoGoroutineLeak`。

---

## 5. 阶段 3：资源管理

### 5.1 Shutdown 关闭 DB 连接池 (R1)

**文件**: `main.go`

**改动**: `Shutdown()` 末尾添加 `s.db.DB().Close()`，`s.db == nil` 时跳过。

**测试**: `main_test.go` — `TestShutdown_ClosesDatabasePool`。

### 5.2 TimeoutManager.Shutdown sync.Once (R2)

**文件**: `pkg/forwarder/timeout.go`

**改动**: 新增 `shutdownOnce sync.Once` 字段，整个 `Shutdown()` 逻辑包裹在 `Do()` 内。

**测试**: `timeout_test.go` — `TestTimeoutManager_ShutdownConcurrent`、`TestTimeoutManager_ShutdownIdempotent`。

### 5.3 日志混用统一 (R3)

**文件**: `pkg/database/database.go`

**改动**: 3 处 `log.Printf` / `log.Println` 替换为 `logger.Infof` / `logger.Warnf`。

**验证**: `go vet ./...` + 编译通过。

---

## 6. 阶段 4：架构统一（依赖注入重构）

### 6.1 AppDependencies 聚合结构体

**新增文件**: `pkg/deps/deps.go`

```go
package deps

type AppDependencies struct {
    DB            *gorm.DB
    UserRepo      repository.UserRepository
    GroupRepo     repository.GroupRepository
    LoginGroupRepo repository.GroupRepository
    ConfigService config.Service
    EventBus      *eventbus.EventBus
}
```

不引入 DI 框架，手写组装。

### 6.2 middleware 依赖注入改造

**文件**: `pkg/middleware/auth.go`

**改动**: 新增 `AuthMiddleware` 结构体，持有 `userRepo`、`tokenCache`、`groupCache`。提供 `NewAuthMiddleware()` 构造函数和 `Authenticate()`、`OptionalAuth()` 方法。

**兼容策略**: 保留旧的包级 `Authenticate()` 函数作为 thin wrapper，内部委托 `globalAuth.Authenticate()`。`SetupGlobalAuth()` 初始化 `globalAuth`。

**测试**: `auth_middleware_test.go` — `TestAuthMiddleware_Authenticate`、`TestLegacyWrapper_DelegatesCorrectly`。

### 6.3 handler 依赖注入改造

**文件**: `pkg/handler/login.go`

**改动**: 新增 `LoginHandler` 结构体 + `NewLoginHandler()` 构造函数。`HandleLogin` 从包级函数变为方法。`loginUserRepo` 包级变量移除。

同理处理其他 handler 的包级 Set 函数：`SetLoginGroupRepository` 等。

**测试**: `login_handler_test.go` — `TestLoginHandler_Success`、`TestLoginHandler_BadCredentials`、`TestLoginHandler_RepoUnavailable`。

### 6.4 main.go 组装流程重构

**改动**: `Start()` 中创建 `AppDependencies` 实例，用其构造 `AuthMiddleware`、`LoginHandler`、`APIHandler` 等。路由注册 `registerRoutes()` 接受 handler 实例参数。移除所有 `handler.Set*()` 和 `middleware.Set*()` 调用。

**测试**: `main_test.go` — 重构后的 `NewServer` + `registerRoutes` 端到端验证。

### 6.5 database.DB 全局单例处理

**策略**: 本阶段不消除全局变量（改动面太大）。改为：
- `main.go` 统一通过 `s.db` 字段访问
- 新增模块通过构造函数接收 `*gorm.DB`
- AGENTS.md 中标记 `database.DB` 为 deprecated

### 6.6 改动影响矩阵

| 文件 | 变更类型 | 风险 |
|------|----------|------|
| `pkg/deps/deps.go` | 新增 | 低 |
| `pkg/middleware/auth.go` | 新增 AuthMiddleware + 兼容 wrapper | 中 |
| `pkg/middleware/auth_cache.go` | 暴露 cache 构造 + ShutdownCaches | 低 |
| `pkg/handler/login.go` | LoginHandler 结构体化 | 中 |
| `pkg/handler/routes.go` | 路由注册接受 handler 实例 | 中 |
| `main.go` | 组装逻辑重写 | 高 |

---

## 7. 阶段 5：测试补齐 + 索引健康

### 7.1 WebSocket Handler 测试

**文件**: `pkg/websocket/handler_test.go`（新增）

| 测试 | 场景 |
|------|------|
| `TestHandleConnection_NormalLifecycle` | 正常连接 → 心跳 → 关闭 |
| `TestHandleConnection_HeartbeatTimeout` | 心跳超时断开 |
| `TestHandleConnection_PanicRecovery` | panic 被 defer recover 捕获 |
| `TestProcessMessage_InvokeResponse` | invoke 响应路由到 TimeoutManager |
| `TestProcessMessage_StreamChunk` | 流式分块推送到 StreamRecord |
| `TestProcessMessage_MalformedJSON` | 畸形 JSON 不 panic |
| `TestHandleBind_NewActions` | 客户端上报新 action 写入 DB |
| `TestHandleBind_AnonymousGroup` | 匿名分组跳过同步 |

**Mock**: `httptest` + gorilla `Dialer`；mock ClientManager、TimeoutManager、GroupRepository。

### 7.2 Middleware 集成测试

**文件**: `pkg/middleware/ratelimit_test.go`、`pkg/middleware/trace_test.go`（新增/扩充）

| 测试 | 场景 |
|------|------|
| `TestRateLimitMiddleware_AnonymousUser` | 匿名用户按 IP 限流 |
| `TestRateLimitMiddleware_AuthenticatedUser` | 认证用户按 quota 限流 |
| `TestRateLimitMiddleware_ZeroQPS` | QPS=0 放行 |
| `TestTraceMiddleware_SkipsHealthCheck` | 内部路径不记录 |
| `TestTraceMiddleware_BatchFlush` | 批量写入触发 |

### 7.3 Alert Evaluator 测试

**文件**: `pkg/alert/evaluator_test.go`（新增）

| 测试 | 场景 |
|------|------|
| `TestEvaluateRule_ThresholdExceeded` | 超阈值触发 |
| `TestEvaluateRule_DedupeWindow` | 去重窗口 |
| `TestCheckThreshold_AllOperators` | 六种运算符 |
| `TestEvaluator_StartStop` | 启停不泄漏 goroutine |

### 7.4 GitNexus 索引重建

```bash
npx gitnexus analyze --force
```

验证：`gitnexus_query({query: "error handling"})` 返回非空。

### 7.5 测试运行基准

```bash
go build ./...           # 编译通过
go vet ./...             # 静态分析通过
go test ./... -count=1   # 全量测试通过
go test -race ./...      # 竞态检测通过
```

---

## 8. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 阶段 4 架构改动影响阶段 1-3 的代码 | 阶段 1-3 的代码设计为结构体方法优先，便于阶段 4 迁移 |
| CORS 行为变化导致生产跨域请求失败 | `.env.example` 中明确说明，提供迁移窗口 |
| query token 废弃影响现有客户端 | 配置开关 `ALLOW_QUERY_TOKEN` 提供过渡期 |
| `database.DB` 全局变量未消除 | 标记 deprecated，新代码禁止引用，后续版本清理 |

---

## 9. 不做的事

- **不引入 DI 框架**（Wire/Fx）— 项目规模不需要
- **不消除 `database.DB` 全局变量** — 改动面太大，标记 deprecated 渐进迁移
- **不修改外部 API 路由或请求/响应格式** — 完全向后兼容
- **不修改 SDK 对外接口** — `pkg/client/sdk/` 的公开 API 不变
- **不重构 `pkg/client/group.go` 的 actor 模型** — 该设计合理，无需改动
