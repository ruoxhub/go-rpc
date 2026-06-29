# Architecture Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete 5 architecture optimizations from `project-analysis.md` chapter 4 plus fix 2 code/documentation fissures.

**Architecture:** Six independent batches (B1→B2→B3→B4→B5→B6) with dependency chain. Each batch produces independently compilable, testable, and rollback-able software. B4 is high-risk (12 call sites + 6 handler fields); B3 medium-risk (API shape change); others low-to-medium risk.

**Tech Stack:** Go 1.21+ (generics), GORM, Gin, PostgreSQL, zap logger

**Spec:** `docs/superpowers/specs/2026-06-28-arch-optimization-design.md`

---

## File Structure

### B1 Fissure Repair
- **Modify:** `pkg/eventbus/eventbus.go:46` (comment fix)
- **Modify:** `pkg/router/strategy.go:16-26` (delete dead enum)
- **Test:** `pkg/eventbus/eventbus_test.go`, `pkg/router/strategy_test.go`

### B2 Config Hot-Reload Sinking EventBus
- **Modify:** `pkg/config/service.go:143` (Refresh signature)
- **Create:** `pkg/eventbus/events.go` (EventConfigChanged + ConfigChangedEvent)
- **Modify:** `pkg/handler/sysconfig.go:19,113` (remove db field, Refresh call)
- **Modify:** `pkg/handler/routes.go:37` (NewSysConfigHandler signature)
- **Modify:** `main.go:237` (Refresh call site)
- **Modify:** `pkg/middleware/auth.go` (tokenCache/groupCache subscribe)
- **Test:** `pkg/config/service_test.go`

### B3 EventBus Generic Type Safety
- **Modify:** `pkg/eventbus/eventbus.go` (add Subscribe[T]/Publish[T])
- **Modify:** `pkg/eventbus/helper.go` (delete funcEqual)
- **Modify:** `main.go:259-273` (3 subscriptions)
- **Modify:** `pkg/handler/invoke.go:93-99` (2 subscriptions)
- **Modify:** `pkg/client/manager.go:155` (Publish)
- **Modify:** `pkg/websocket/handler.go:152,160` (2 Publish)
- **Modify:** `pkg/handler/invoke.go:170,189` (2 Publish)
- **Test:** `pkg/eventbus/eventbus_test.go`, `pkg/client/manager_test.go`

### B4 DI Refactoring
- **Modify:** `pkg/middleware/auth.go:22-277` (extend AuthMiddleware)
- **Modify:** `main.go:224,259-273,546,570,623` (inject authMW)
- **Modify:** `pkg/handler/deps.go` (embed AppDependencies)
- **Modify:** `pkg/handler/invoke.go:626,658,667` (use h.authMW)
- **Modify:** `pkg/handler/login.go:87` (use h.authMW)
- **Modify:** `pkg/handler/user.go:142,160,219,220` (use h.authMW)
- **Modify:** `pkg/handler/group.go:122,172,236` (use h.authMW)
- **Modify:** `pkg/handler/anonymous.go:325` (use h.authMW)
- **Modify:** `pkg/handler/routes.go:51` (authMW.Authenticate method)
- **Test:** `pkg/middleware/auth_token_test.go`, `pkg/middleware/auth_cache_test.go`, `pkg/middleware/auth_test.go`

### B5 Route Strategy Chain
- **Create:** `pkg/router/strategy_specified.go` (SpecifiedStrategy)
- **Create:** `pkg/router/strategy_hash.go` (ConsistentHashStrategy)
- **Create:** `pkg/router/strategy_roundrobin.go` (RoundRobinStrategy)
- **Modify:** `pkg/router/strategy.go:79-109` (refactor Route)
- **Modify:** `pkg/router/router.go` (NewRouter signature)
- **Modify:** `main.go` (NewRouter call with configSvc)
- **Test:** `pkg/router/strategy_specified_test.go`, `pkg/router/strategy_hash_test.go`, `pkg/router/strategy_roundrobin_test.go`, `pkg/router/router_test.go`

### B6 Auth/Rate-Limit Observability
- **Modify:** `pkg/middleware/auth.go:42,48,264` (add metrics.Incr)
- **Modify:** `pkg/middleware/ratelimit.go:42` (add metrics.Incr)
- **Modify:** `pkg/middleware/anonymous.go` (add metrics.Incr)
- **Create:** `pkg/metrics/noop_collector.go` (noopCollector)
- **Test:** `pkg/middleware/auth_test.go`, `pkg/middleware/ratelimit_test.go`, `pkg/metrics/noop_collector_test.go`

---

## B1: Fissure Repair (Zero Risk)

### Task 1: Fix EventBus Misleading Comment

**Files:**
- Modify: `pkg/eventbus/eventbus.go:46`

- [ ] **Step 1: Update Publish comment**

```go
// Publish 向所有注册的处理器发布事件。
// 当前为同步派发：在调用方 goroutine 内顺序调用所有 handler，
// 慢订阅者会阻塞发布者。如需异步语义，由订阅方自行启动 goroutine。
func (eb *EventBus) Publish(eventType string, event interface{}) {
```

- [ ] **Step 2: Run existing tests**

Run: `go test ./pkg/eventbus/...`
Expected: PASS (no behavior change, only comment)

- [ ] **Step 3: Commit**

```bash
git add pkg/eventbus/eventbus.go
git commit -m "fix(eventbus): correct Publish comment (synchronous, not async)"
```

---

### Task 2: Delete RoutingStrategy Dead Enum

**Files:**
- Modify: `pkg/router/strategy.go:16-26`
- Test: `pkg/router/strategy_test.go`

- [ ] **Step 1: Verify enum is unused**

Run: `grep -r "RoutingStrategy\|RoundRobin\|SpecifiedClient\|ConsistentHash" --include="*.go" pkg/ main.go`
Expected: Only matches in `pkg/router/strategy.go` (definition) and comments/docs

- [ ] **Step 2: Delete enum and constants**

Remove lines 16-26 from `pkg/router/strategy.go`:
```go
// Delete these lines:
// type RoutingStrategy int
//
// const (
//     RoundRobin RoutingStrategy = iota
//     SpecifiedClient
//     ConsistentHash
// )
```

- [ ] **Step 3: Run tests**

Run: `go build ./... && go test ./pkg/router/...`
Expected: PASS (no references, so no breakage)

- [ ] **Step 4: Commit**

```bash
git add pkg/router/strategy.go
git commit -m "refactor(router): delete unused RoutingStrategy enum"
```

---

## B2: Config Hot-Reload Sinking EventBus

### Task 3: Add EventConfigChanged Event

**Files:**
- Create: `pkg/eventbus/events.go`

- [ ] **Step 1: Create events.go with ConfigChangedEvent**

```go
package eventbus

// EventConfigChanged 配置变更事件
const EventConfigChanged = "config.changed"

// ConfigChangedEvent 配置变更事件载荷
type ConfigChangedEvent struct {
    Keys []string // 变更的配置键集合
}
```

- [ ] **Step 2: Run tests**

Run: `go build ./pkg/eventbus/...`
Expected: PASS (new file, no references yet)

- [ ] **Step 3: Commit**

```bash
git add pkg/eventbus/events.go
git commit -m "feat(eventbus): add EventConfigChanged and ConfigChangedEvent"
```

---

### Task 4: Refactor Refresh to Use Repository

**Files:**
- Modify: `pkg/config/service.go:143`
- Modify: `pkg/config/service.go` (add repo field, constructor)

- [ ] **Step 1: Add repo field to service struct**

```go
type service struct {
    configs         sync.Map
    lastConfigsHash uint64
    mu              sync.RWMutex
    repo            repository.SysConfigRepository // 新增
}
```

- [ ] **Step 2: Update NewService constructor**

```go
func NewService(repo repository.SysConfigRepository) Service {
    return &service{
        repo: repo,
    }
}
```

- [ ] **Step 3: Refactor Refresh signature**

Replace `Refresh(db *gorm.DB) error` with:

```go
// Refresh 从数据库刷新配置
func (s *service) Refresh() error {
    if s.repo == nil {
        logger.Warn("配置仓库未初始化，跳过配置刷新")
        return nil
    }

    configs, err := s.repo.FindAll()
    if err != nil {
        logger.Error("查询配置失败", zap.Error(err))
        return err
    }

    // 创建新的配置映射
    newConfigs := make(map[string]string, len(configs))
    for _, cfg := range configs {
        newConfigs[cfg.ConfigKey] = cfg.ConfigValue
    }

    // 计算新配置的哈希值，用于检测变化
    newHash := s.computeConfigsHash(newConfigs)

    // 对比哈希值，只有配置真正变化时才更新
    s.mu.Lock()
    hasChanged := s.lastConfigsHash != newHash
    if hasChanged {
        // 原子性替换所有配置
        s.configs = sync.Map{}
        for k, v := range newConfigs {
            s.configs.Store(k, v)
        }
        s.lastConfigsHash = newHash
    }
    s.mu.Unlock()

    if hasChanged {
        logger.Info("配置已刷新", zap.Int("count", len(configs)))
    }

    return nil
}
```

- [ ] **Step 4: Update Service interface**

```go
type Service interface {
    GetConfig(key string) string
    GetConfigWithDefault(key, defaultValue string) string
    Refresh() error  // 移除 db 参数
    GetAllConfigs() map[string]string
    computeConfigsHash(configs map[string]string) uint64
}
```

- [ ] **Step 5: Run tests**

Run: `go build ./pkg/config/...`
Expected: FAIL (call sites still pass db parameter)

- [ ] **Step 6: Commit (WIP)**

```bash
git add pkg/config/service.go
git commit -m "WIP: refactor config service Refresh to use repository"
```

---

### Task 5: Update Refresh Call Sites

**Files:**
- Modify: `pkg/handler/sysconfig.go:19` (remove db field)
- Modify: `pkg/handler/sysconfig.go:113` (Refresh call)
- Modify: `pkg/handler/routes.go:37` (NewSysConfigHandler signature)
- Modify: `main.go:237` (Refresh call)

- [ ] **Step 1: Remove db field from SysConfigHandler**

In `pkg/handler/sysconfig.go:19`, delete:
```go
type SysConfigHandler struct {
    repo      repository.SysConfigRepository
    nodeRepo  repository.ServerNodeRepository
    logRepo   repository.SysLogRepository
    configSvc config.Service
    db        *gorm.DB  // 删除此行
}
```

- [ ] **Step 2: Update NewSysConfigHandler signature**

```go
func NewSysConfigHandler(repo repository.SysConfigRepository, nodeRepo repository.ServerNodeRepository, logRepo repository.SysLogRepository, configSvc config.Service) *SysConfigHandler {
    return &SysConfigHandler{
        repo:      repo,
        nodeRepo:  nodeRepo,
        logRepo:   logRepo,
        configSvc: configSvc,
    }
}
```

- [ ] **Step 3: Update Refresh call in sysconfig.go:113**

```go
func (h *SysConfigHandler) Refresh(c *gin.Context) {
    if err := h.configSvc.Refresh(); err != nil {  // 移除 db 参数
        response.ErrorResponse(c, http.StatusInternalServerError, "刷新配置失败: "+err.Error())
        return
    }
    response.SuccessResponse(c, nil)
}
```

- [ ] **Step 4: Update routes.go:37**

```go
sysConfigHandler := NewSysConfigHandler(deps.SysConfigRepo, deps.ServerNodeRepo, deps.SysLogRepo, deps.ConfigService)  // 移除 deps.DB
```

- [ ] **Step 5: Update main.go:237**

```go
if err := s.configService.Refresh(); err != nil {  // 移除 db 参数
    logger.Errorf("刷新配置失败: %v", err)
}
```

- [ ] **Step 6: Run build**

Run: `go build ./...`
Expected: PASS (all call sites updated)

- [ ] **Step 7: Commit**

```bash
git add pkg/handler/sysconfig.go pkg/handler/routes.go main.go
git commit -m "refactor(config): update Refresh call sites to remove db parameter"
```

---

### Task 6: Add changedKeys Diff and Publish Event

**Files:**
- Modify: `pkg/config/service.go:Refresh`
- Modify: `pkg/config/service.go` (add eventBus field, constructor)

- [ ] **Step 1: Add eventBus field to service**

```go
type service struct {
    configs         sync.Map
    lastConfigsHash uint64
    mu              sync.RWMutex
    repo            repository.SysConfigRepository
    eventBus        *eventbus.EventBus  // 新增
}
```

- [ ] **Step 2: Update NewService constructor**

```go
func NewService(repo repository.SysConfigRepository, eventBus *eventbus.EventBus) Service {
    return &service{
        repo:     repo,
        eventBus: eventBus,
    }
}
```

- [ ] **Step 3: Add changedKeys diff logic in Refresh**

Replace the `if hasChanged` block in `Refresh`:

```go
if hasChanged {
    // 原子性替换所有配置
    s.configs = sync.Map{}
    for k, v := range newConfigs {
        s.configs.Store(k, v)
    }
    s.lastConfigsHash = newHash

    // 计算变更 key 集合
    changedKeys := s.diffConfigKeys(newConfigs)

    // 发布配置变更事件
    if s.eventBus != nil && len(changedKeys) > 0 {
        s.eventBus.Publish(eventbus.EventConfigChanged, eventbus.ConfigChangedEvent{
            Keys: changedKeys,
        })
        logger.Info("发布配置变更事件", zap.Strings("keys", changedKeys))
    }
}
```

- [ ] **Step 4: Implement diffConfigKeys helper**

Add to `pkg/config/service.go`:

```go
// diffConfigKeys 对比新旧配置，返回变更 key 集合
func (s *service) diffConfigKeys(newConfigs map[string]string) []string {
    var changed []string
    oldKeys := make(map[string]bool)

    // 收集旧 key
    s.configs.Range(func(key, value interface{}) bool {
        if k, ok := key.(string); ok {
            oldKeys[k] = true
            // 检查值是否变化
            if newVal, exists := newConfigs[k]; !exists || newVal != value.(string) {
                changed = append(changed, k)
            }
        }
        return true
    })

    // 检查新增 key
    for k := range newConfigs {
        if !oldKeys[k] {
            changed = append(changed, k)
        }
    }

    return changed
}
```

- [ ] **Step 5: Update NewService call in main.go**

```go
s.configService = config.NewService(appDeps.SysConfigRepo, s.eventBus)
```

- [ ] **Step 6: Run tests**

Run: `go build ./... && go test ./pkg/config/...`
Expected: PASS (eventBus can be nil, graceful degradation)

- [ ] **Step 7: Commit**

```bash
git add pkg/config/service.go main.go
git commit -m "feat(config): publish EventConfigChanged with changedKeys on Refresh"
```

---

### Task 7: Subscribe tokenCache/groupCache to EventConfigChanged

**Files:**
- Modify: `pkg/middleware/auth.go` (tokenCache/groupCache subscribe)

- [ ] **Step 1: Add subscription in main.go after cache init**

In `main.go` after `middleware.SetTokenUserRepository(appDeps.UserRepo)`, add:

```go
// 订阅配置变更事件，失效相关缓存
s.eventBus.Subscribe(eventbus.EventConfigChanged, func(event interface{}) {
    if e, ok := event.(eventbus.ConfigChangedEvent); ok {
        for _, key := range e.Keys {
            // user 相关 key 变更 → 失效 tokenCache
            if strings.HasPrefix(key, "user.") || strings.HasPrefix(key, "token.") {
                middleware.InvalidateAllTokens()
                logger.Debug("tokenCache invalidated due to config change", zap.String("key", key))
            }
            // group 相关 key 变更 → 失效 groupCache
            if strings.HasPrefix(key, "group.") {
                middleware.InvalidateAllGroups()
                logger.Debug("groupCache invalidated due to config change", zap.String("key", key))
            }
        }
    }
})
```

- [ ] **Step 2: Add InvalidateAllTokens/InvalidateAllGroups to auth.go**

```go
// InvalidateAllTokens 清空所有 token 缓存
func InvalidateAllTokens() {
    if tc := defaultTokenCache.Load(); tc != nil {
        tc.Clear()
    }
}

// InvalidateAllGroups 清空所有 group 缓存
func InvalidateAllGroups() {
    if gc := defaultGroupCache.Load(); gc != nil {
        gc.Clear()
    }
}
```

- [ ] **Step 3: Add Clear method to cache**

In `pkg/middleware/cache.go` (or wherever cache is defined):

```go
// Clear 清空缓存
func (c *cache[T]) Clear() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.data = make(map[string]T)
}
```

- [ ] **Step 4: Run tests**

Run: `go build ./... && go test ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/middleware/auth.go pkg/middleware/cache.go main.go
git commit -m "feat(config): subscribe tokenCache/groupCache to EventConfigChanged"
```

---

### Task 8: Write Integration Test for Config Refresh

**Files:**
- Test: `pkg/config/service_test.go`

- [ ] **Step 1: Write test for Refresh publishes event**

```go
func TestService_Refresh_PublishesEvent(t *testing.T) {
    // Setup mock repo
    repo := &mockSysConfigRepo{
        configs: []model.SysConfig{
            {ConfigKey: "user.max_tokens", ConfigValue: "100"},
            {ConfigKey: "group.default_strategy", ConfigValue: "round_robin"},
        },
    }

    // Setup event bus
    eb := eventbus.New()
    var receivedKeys []string
    eb.Subscribe(eventbus.EventConfigChanged, func(event interface{}) {
        if e, ok := event.(eventbus.ConfigChangedEvent); ok {
            receivedKeys = e.Keys
        }
    })

    // Create service
    svc := NewService(repo, eb).(*service)

    // Initial refresh
    err := svc.Refresh()
    assert.NoError(t, err)
    assert.Empty(t, receivedKeys) // 首次无变更

    // Modify config
    repo.configs[0].ConfigValue = "200"

    // Second refresh
    err = svc.Refresh()
    assert.NoError(t, err)
    assert.Contains(t, receivedKeys, "user.max_tokens")
}
```

- [ ] **Step 2: Run test**

Run: `go test -run TestService_Refresh_PublishesEvent ./pkg/config/... -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add pkg/config/service_test.go
git commit -m "test(config): add integration test for Refresh event publishing"
```

---

## B3: EventBus Generic Type Safety

### Task 9: Add Generic Subscribe[T] and Publish[T]

**Files:**
- Modify: `pkg/eventbus/eventbus.go`

- [ ] **Step 1: Add generic Subscribe function**

```go
// Subscribe 泛型订阅：编译期绑定事件类型 T
// 内部包装为 func(interface{})，断言失败 panic（契约违反）
func Subscribe[T any](eb *EventBus, eventType string, handler func(T)) {
    wrapped := func(event interface{}) {
        e := event.(T)  // 集中断言，编译期 T 约束保证成立
        handler(e)
    }
    eb.Subscribe(eventType, wrapped)
}
```

- [ ] **Step 2: Add generic Publish function**

```go
// Publish 泛型发布：编译期绑定事件类型 T
func Publish[T any](eb *EventBus, eventType string, event T) {
    eb.Publish(eventType, event)
}
```

- [ ] **Step 3: Run build**

Run: `go build ./pkg/eventbus/...`
Expected: PASS (new functions, no call sites yet)

- [ ] **Step 4: Commit**

```bash
git add pkg/eventbus/eventbus.go
git commit -m "feat(eventbus): add generic Subscribe[T] and Publish[T]"
```

---

### Task 10: Migrate main.go Subscriptions to Generic

**Files:**
- Modify: `main.go:259-273`

- [ ] **Step 1: Migrate EventClientConnect subscription**

```go
// Before:
s.eventBus.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
    e := event.(*eventbus.ClientConnectEvent)  // 无 ok，panic 风险
    current := s.clientManager.GetClientsByGroup(e.Group)
    s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
})

// After:
eventbus.Subscribe(s.eventBus, eventbus.EventClientConnect, func(e eventbus.ClientConnectEvent) {
    current := s.clientManager.GetClientsByGroup(e.Group)
    s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
})
```

- [ ] **Step 2: Migrate EventClientDisconnect subscription**

```go
eventbus.Subscribe(s.eventBus, eventbus.EventClientDisconnect, func(e eventbus.ClientDisconnectEvent) {
    current := s.clientManager.GetClientsByGroup(e.Group)
    s.metricsCollector.Set("client.online", map[string]string{"group": e.Group}, float64(len(current)))
})
```

- [ ] **Step 3: Migrate EventClientHealthDegraded subscription**

```go
eventbus.Subscribe(s.eventBus, eventbus.EventClientHealthDegraded, func(e eventbus.ClientHealthDegradedEvent) {
    logger.Warnf("Client health degraded: group=%s, clientId=%s, failCount=%d",
        e.Group, e.ClientID, e.FailCount)
})
```

- [ ] **Step 4: Update Publish calls in main.go**

Find all `s.eventBus.Publish` calls and replace with `eventbus.Publish(s.eventBus, ...)`. Pass value instead of pointer:

```go
// Before:
s.eventBus.Publish(eventbus.EventClientConnect, &eventbus.ClientConnectEvent{...})

// After:
eventbus.Publish(s.eventBus, eventbus.EventClientConnect, eventbus.ClientConnectEvent{...})
```

- [ ] **Step 5: Run build**

Run: `go build ./...`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add main.go
git commit -m "refactor(eventbus): migrate main.go subscriptions to generic API"
```

---

### Task 11: Migrate invoke.go Subscriptions

**Files:**
- Modify: `pkg/handler/invoke.go:93-99`

- [ ] **Step 1: Migrate EventClientConnect subscription**

```go
// Before:
eventBus.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
    if e, ok := event.(*eventbus.ClientConnectEvent); ok {
        h.router.InvalidateRingCache(e.Group)
    }
})

// After:
eventbus.Subscribe(eventBus, eventbus.EventClientConnect, func(e eventbus.ClientConnectEvent) {
    h.router.InvalidateRingCache(e.Group)
})
```

- [ ] **Step 2: Migrate EventClientDisconnect subscription**

```go
eventbus.Subscribe(eventBus, eventbus.EventClientDisconnect, func(e eventbus.ClientDisconnectEvent) {
    h.router.InvalidateRingCache(e.Group)
})
```

- [ ] **Step 3: Migrate Publish calls in invoke.go**

Find all `eventBus.Publish` calls (lines 170, 189) and replace:

```go
// Before:
eventBus.Publish(eventbus.EventInvokeRequest, &eventbus.InvokeRequestEvent{...})

// After:
eventbus.Publish(eventBus, eventbus.EventInvokeRequest, eventbus.InvokeRequestEvent{...})
```

- [ ] **Step 4: Run tests**

Run: `go test ./pkg/handler/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/handler/invoke.go
git commit -m "refactor(eventbus): migrate invoke.go subscriptions to generic API"
```

---

### Task 12: Migrate Remaining Publish Calls

**Files:**
- Modify: `pkg/client/manager.go:155`
- Modify: `pkg/websocket/handler.go:152,160`

- [ ] **Step 1: Update manager.go Publish**

```go
// Before:
m.eventBus.Publish(eventbus.EventClientConnect, &eventbus.ClientConnectEvent{...})

// After:
eventbus.Publish(m.eventBus, eventbus.EventClientConnect, eventbus.ClientConnectEvent{...})
```

- [ ] **Step 2: Update handler.go Publish calls**

```go
// Before:
h.eventBus.Publish(eventbus.EventClientConnect, &eventbus.ClientConnectEvent{...})
h.eventBus.Publish(eventbus.EventClientDisconnect, &eventbus.ClientDisconnectEvent{...})

// After:
eventbus.Publish(h.eventBus, eventbus.EventClientConnect, eventbus.ClientConnectEvent{...})
eventbus.Publish(h.eventBus, eventbus.EventClientDisconnect, eventbus.ClientDisconnectEvent{...})
```

- [ ] **Step 3: Run build**

Run: `go build ./...`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/client/manager.go pkg/websocket/handler.go
git commit -m "refactor(eventbus): migrate remaining Publish calls to generic API"
```

---

### Task 13: Delete Unsubscribe and funcEqual Dead Code

**Files:**
- Modify: `pkg/eventbus/eventbus.go` (delete Unsubscribe)
- Modify: `pkg/eventbus/helper.go` (delete funcEqual)
- Test: `pkg/eventbus/eventbus_test.go`

- [ ] **Step 1: Verify Unsubscribe is unused**

Run: `grep -r "Unsubscribe" --include="*.go" pkg/ main.go`
Expected: Only matches in `pkg/eventbus/eventbus.go` (definition) and comments

- [ ] **Step 2: Delete Unsubscribe method**

Remove lines 32-44 from `pkg/eventbus/eventbus.go`:
```go
// Unsubscribe 取消订阅指定事件类型
func (eb *EventBus) Unsubscribe(eventType string, handler EventHandler) {
    eb.mu.Lock()
    defer eb.mu.Unlock()

    handlers := eb.handlers[eventType]
    for i, h := range handlers {
        if sameHandler(h, handler) {
            eb.handlers[eventType] = append(handlers[:i], handlers[i+1:]...)
            return
        }
    }
}
```

- [ ] **Step 3: Delete sameHandler and funcEqual**

Remove from `pkg/eventbus/eventbus.go`:
```go
// sameHandler 比较两个处理函数是否为同一个（通过地址）
func sameHandler(a, b EventHandler) bool {
    return funcEqual(a, b)
}
```

Delete entire `pkg/eventbus/helper.go` file.

- [ ] **Step 4: Run tests**

Run: `go build ./... && go test ./pkg/eventbus/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/eventbus/eventbus.go pkg/eventbus/helper.go
git commit -m "refactor(eventbus): delete unused Unsubscribe and funcEqual"
```

---

### Task 14: Update Tests to Use Generic API

**Files:**
- Test: `pkg/eventbus/eventbus_test.go`
- Test: `pkg/client/manager_test.go`

- [ ] **Step 1: Update eventbus_test.go**

Replace all `Subscribe` and `Publish` calls with generic versions:

```go
// Before:
eb.Subscribe("test.event", func(event interface{}) {
    e := event.(*TestEvent)
    ...
})
eb.Publish("test.event", &TestEvent{...})

// After:
eventbus.Subscribe(eb, "test.event", func(e TestEvent) {
    ...
})
eventbus.Publish(eb, "test.event", TestEvent{...})
```

- [ ] **Step 2: Update manager_test.go**

Similar migration for any Subscribe/Publish calls.

- [ ] **Step 3: Run tests**

Run: `go test -race ./pkg/eventbus/... ./pkg/client/...`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/eventbus/eventbus_test.go pkg/client/manager_test.go
git commit -m "test(eventbus): update tests to use generic API"
```

---

## B4: DI Refactoring

### Task 15: Extend AuthMiddleware with Cache Methods

**Files:**
- Modify: `pkg/middleware/auth.go`

- [ ] **Step 1: Extend AuthMiddleware struct**

```go
type AuthMiddleware struct {
    userRepo    TokenUserLookup
    groupLookup GroupConfigLookup   // 注入：典型为 groupRepo.FindGroupByName
    tokenCache  *cache[model.UserInfo]
    groupCache  *cache[model.GroupConfig]
    metrics     metrics.MetricCollector  // B6 注入，可空→用 noop
}
```

- [ ] **Step 2: Add FindUserByToken method**

```go
func (am *AuthMiddleware) FindUserByToken(token string) (*model.UserInfo, error) {
    // 先查缓存
    if am.tokenCache != nil {
        if user, ok := am.tokenCache.Get(token); ok {
            return user, nil
        }
    }

    // 缓存未命中，查数据库
    user, err := am.userRepo.FindUserByToken(token)
    if err != nil {
        return nil, err
    }

    // 写回缓存
    if am.tokenCache != nil && user != nil {
        am.tokenCache.Set(token, user, 5*time.Minute)
    }

    return user, nil
}
```

- [ ] **Step 3: Add LookupGroupConfig method**

```go
func (am *AuthMiddleware) LookupGroupConfig(name string) (*model.GroupConfig, error) {
    // 先查缓存
    if am.groupCache != nil {
        if group, ok := am.groupCache.Get(name); ok {
            return group, nil
        }
    }

    // 缓存未命中，查数据库
    group, err := am.groupLookup(name)
    if err != nil {
        return nil, err
    }

    // 写回缓存
    if am.groupCache != nil && group != nil {
        am.groupCache.Set(name, group, 5*time.Minute)
    }

    return group, nil
}
```

- [ ] **Step 4: Add InvalidateToken method**

```go
func (am *AuthMiddleware) InvalidateToken(token string) {
    if am.tokenCache != nil {
        am.tokenCache.Delete(token)
    }
}
```

- [ ] **Step 5: Add InvalidateGroup method**

```go
func (am *AuthMiddleware) InvalidateGroup(name string) {
    if am.groupCache != nil {
        am.groupCache.Delete(name)
    }
}
```

- [ ] **Step 6: Add Shutdown method**

```go
func (am *AuthMiddleware) Shutdown() {
    if am.tokenCache != nil {
        am.tokenCache.StopGC()
    }
    if am.groupCache != nil {
        am.groupCache.StopGC()
    }
}
```

- [ ] **Step 7: Run build**

Run: `go build ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add pkg/middleware/auth.go
git commit -m "feat(middleware): extend AuthMiddleware with cache management methods"
```

---

### Task 16: Update handler.Deps to Embed AppDependencies

**Files:**
- Modify: `pkg/handler/deps.go`

- [ ] **Step 1: Refactor Deps struct**

```go
type Deps struct {
    *deps.AppDependencies   // 嵌入：UserRepo/GroupRepo/DB/ConfigService/EventBus 自动提升
    ClientManager  *client.ClientManager
    SysConfigRepo  repository.SysConfigRepository
    ServerNodeRepo repository.ServerNodeRepository
    SysLogRepo     repository.SysLogRepository
    TraceRepo      repository.TraceRepository
    AlertRepo      repository.AlertRepository
    MetricRepo     repository.MetricRepository
    AuthMW         *middleware.AuthMiddleware   // 新增
}
```

- [ ] **Step 2: Run build**

Run: `go build ./pkg/handler/...`
Expected: PASS (embedding auto-promotes fields)

- [ ] **Step 3: Commit**

```bash
git add pkg/handler/deps.go
git commit -m "refactor(handler): embed AppDependencies in Deps struct"
```

---

### Task 17: Inject AuthMiddleware into main.go

**Files:**
- Modify: `main.go`

- [ ] **Step 1: Create AuthMiddleware instance**

In `main.go` after `appDeps` initialization, add:

```go
// 创建 AuthMiddleware 实例
authMW := middleware.NewAuthMiddleware(
    appDeps.UserRepo,
    appDeps.GroupRepo.FindGroupByName,
    nil, // metrics 在 B6 注入
)
s.authMW = authMW
```

- [ ] **Step 2: Add authMW field to Server struct**

```go
type Server struct {
    // ... existing fields ...
    authMW *middleware.AuthMiddleware  // 新增
}
```

- [ ] **Step 3: Remove SetTokenUserRepository call**

Delete line 224:
```go
middleware.SetTokenUserRepository(appDeps.UserRepo)
```

- [ ] **Step 4: Update ShutdownCaches call**

Replace line 623:
```go
// Before:
middleware.ShutdownCaches()

// After:
s.authMW.Shutdown()
```

- [ ] **Step 5: Run build**

Run: `go build ./...`
Expected: FAIL (call sites still use package-level functions)

- [ ] **Step 6: Commit (WIP)**

```bash
git add main.go
git commit -m "WIP: inject AuthMiddleware into Server"
```

---

### Task 18: Migrate Call Sites to Use authMW Methods

**Files:**
- Modify: `main.go:546,570`
- Modify: `pkg/handler/invoke.go:626,658,667`
- Modify: `pkg/handler/login.go:87`
- Modify: `pkg/handler/user.go:142,160,219,220`
- Modify: `pkg/handler/group.go:122,172,236`
- Modify: `pkg/handler/anonymous.go:325`

- [ ] **Step 1: Update main.go:546**

```go
// Before:
groupConfig, err := middleware.LookupGroupConfig(groupName, s.groupRepo.FindGroupByName)

// After:
groupConfig, err := s.authMW.LookupGroupConfig(groupName)
```

- [ ] **Step 2: Update main.go:570**

```go
// Before:
user, err := middleware.FindUserByToken(token)

// After:
user, err := s.authMW.FindUserByToken(token)
```

- [ ] **Step 3: Add authMW field to APIHandler**

In `pkg/handler/invoke.go`:
```go
type APIHandler struct {
    // ... existing fields ...
    authMW *middleware.AuthMiddleware  // 新增
}
```

Update `NewAPIHandler` signature to accept `authMW`.

- [ ] **Step 4: Update invoke.go:626,658,667**

```go
// Before:
groupConfig, err := middleware.LookupGroupConfig(groupName, h.groupRepo.FindGroupByName)
user, err := middleware.FindUserByToken(token)
middleware.InvalidateToken(token)

// After:
groupConfig, err := h.authMW.LookupGroupConfig(groupName)
user, err := h.authMW.FindUserByToken(token)
h.authMW.InvalidateToken(token)
```

- [ ] **Step 5: Update login.go, user.go, group.go, anonymous.go**

Similar pattern: add `authMW` field to each handler, replace package-level calls with method calls.

- [ ] **Step 6: Update routes.go:51**

```go
// Before:
api.Use(middleware.Authenticate())

// After:
api.Use(s.authMW.Authenticate())
```

- [ ] **Step 7: Run build**

Run: `go build ./...`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add main.go pkg/handler/
git commit -m "refactor(middleware): migrate all call sites to use AuthMiddleware methods"
```

---

### Task 19: Delete Package-Level Globals

**Files:**
- Modify: `pkg/middleware/auth.go`

- [ ] **Step 1: Delete package-level variables**

Remove from `pkg/middleware/auth.go`:
```go
var (
    defaultTokenCache   atomic.Pointer[cache[model.UserInfo]]
    defaultGroupCache   atomic.Pointer[cache[model.GroupConfig]]
    tokenUserRepoPtr    atomic.Pointer[TokenUserLookup]
)
```

- [ ] **Step 2: Delete package-level functions**

Remove:
```go
func SetTokenUserRepository(repo TokenUserLookup)
func FindUserByToken(token string) (*model.UserInfo, error)
func LookupGroupConfig(name string, lookup GroupConfigLookup) (*model.GroupConfig, error)
func InvalidateToken(token string)
func InvalidateGroup(name string)
func ShutdownCaches()
```

- [ ] **Step 3: Run build**

Run: `go build ./...`
Expected: PASS (all call sites migrated)

- [ ] **Step 4: Commit**

```bash
git add pkg/middleware/auth.go
git commit -m "refactor(middleware): delete package-level cache globals"
```

---

### Task 20: Update Tests to Use AuthMiddleware Instance

**Files:**
- Test: `pkg/middleware/auth_token_test.go`
- Test: `pkg/middleware/auth_cache_test.go`
- Test: `pkg/middleware/auth_test.go`

- [ ] **Step 1: Refactor tests to construct AuthMiddleware**

```go
// Before:
middleware.SetTokenUserRepository(mockRepo)
user, err := middleware.FindUserByToken("token")

// After:
am := middleware.NewAuthMiddleware(mockRepo, nil, nil)
user, err := am.FindUserByToken("token")
```

- [ ] **Step 2: Remove backup/restore logic**

Delete code that backs up and restores package-level globals (no longer needed).

- [ ] **Step 3: Run tests**

Run: `go test -race ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/middleware/auth_*_test.go
git commit -m "test(middleware): update tests to use AuthMiddleware instance"
```

---

## B5: Route Strategy Chain

### Task 21: Define Strategy Interface

**Files:**
- Modify: `pkg/router/strategy.go`

- [ ] **Step 1: Add Strategy interface**

```go
// Strategy 路由策略接口
type Strategy interface {
    Select(group *client.RpcGroup, params RouteParams) *client.RpcClient
}
```

- [ ] **Step 2: Add StrategyType constants**

```go
// StrategyType 策略类型
type StrategyType string

const (
    StrategyRoundRobin    StrategyType = "round_robin"
    StrategyConsistentHash StrategyType = "consistent_hash"
)
```

- [ ] **Step 3: Run build**

Run: `go build ./pkg/router/...`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/router/strategy.go
git commit -m "feat(router): add Strategy interface and type constants"
```

---

### Task 22: Implement SpecifiedStrategy

**Files:**
- Create: `pkg/router/strategy_specified.go`
- Test: `pkg/router/strategy_specified_test.go`

- [ ] **Step 1: Implement SpecifiedStrategy**

```go
package router

import "github.com/mrh30000/go-rpc/pkg/client"

// SpecifiedStrategy 指定客户端策略（含模糊匹配）
type SpecifiedStrategy struct{}

func (s *SpecifiedStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
    if params.ClientID == "" {
        return nil
    }

    // 精确匹配
    if c := group.GetClientByID(params.ClientID); c != nil && c.IsHealthy() {
        return c
    }

    // 模糊匹配（Fuzzy=true）
    if params.Fuzzy {
        for _, c := range group.GetClients() {
            if strings.Contains(c.GetID(), params.ClientID) && c.IsHealthy() {
                return c
            }
        }
    }

    return nil
}
```

- [ ] **Step 2: Write test**

```go
func TestSpecifiedStrategy_Select(t *testing.T) {
    strategy := &SpecifiedStrategy{}
    group := createMockGroup()

    // 精确匹配
    params := RouteParams{ClientID: "client-1"}
    c := strategy.Select(group, params)
    assert.NotNil(t, c)
    assert.Equal(t, "client-1", c.GetID())

    // 模糊匹配
    params = RouteParams{ClientID: "client", Fuzzy: true}
    c = strategy.Select(group, params)
    assert.NotNil(t, c)

    // 无匹配
    params = RouteParams{ClientID: "nonexistent"}
    c = strategy.Select(group, params)
    assert.Nil(t, c)
}
```

- [ ] **Step 3: Run test**

Run: `go test -run TestSpecifiedStrategy ./pkg/router/... -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/router/strategy_specified.go pkg/router/strategy_specified_test.go
git commit -m "feat(router): implement SpecifiedStrategy"
```

---

### Task 23: Implement ConsistentHashStrategy

**Files:**
- Create: `pkg/router/strategy_hash.go`
- Test: `pkg/router/strategy_hash_test.go`

- [ ] **Step 1: Implement ConsistentHashStrategy**

```go
package router

import "github.com/mrh30000/go-rpc/pkg/client"

// ConsistentHashStrategy 一致性 Hash 策略
type ConsistentHashStrategy struct {
    ringCache *ringCache
}

func (s *ConsistentHashStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
    hashKey := params.HashKey
    if hashKey == "" && !params.ConstantInvoke {
        return nil  // 无 hash key 且非 ConstantInvoke，返回 nil 让 Router 回退 RR
    }

    clients := filterEligibleClients(group.GetClients())
    if len(clients) == 0 {
        return nil
    }

    ring := s.ringCache.GetOrCreate(group.GetName(), clients)
    if hashKey == "" {
        hashKey = group.GetName()  // ConstantInvoke 用 group name 作 key
    }

    return ring.Get(hashKey)
}
```

- [ ] **Step 2: Write test**

```go
func TestConsistentHashStrategy_Select(t *testing.T) {
    strategy := &ConsistentHashStrategy{ringCache: newRingCache()}
    group := createMockGroup()

    // 有 hash key
    params := RouteParams{HashKey: "user-123"}
    c1 := strategy.Select(group, params)
    assert.NotNil(t, c1)

    // 相同 hash key 返回相同客户端
    c2 := strategy.Select(group, params)
    assert.Equal(t, c1.GetID(), c2.GetID())

    // 无 hash key 且非 ConstantInvoke → nil
    params = RouteParams{}
    c := strategy.Select(group, params)
    assert.Nil(t, c)
}
```

- [ ] **Step 3: Run test**

Run: `go test -run TestConsistentHashStrategy ./pkg/router/... -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/router/strategy_hash.go pkg/router/strategy_hash_test.go
git commit -m "feat(router): implement ConsistentHashStrategy"
```

---

### Task 24: Implement RoundRobinStrategy

**Files:**
- Create: `pkg/router/strategy_roundrobin.go`
- Test: `pkg/router/strategy_roundrobin_test.go`

- [ ] **Step 1: Implement RoundRobinStrategy**

```go
package router

import (
    "sync/atomic"
    "github.com/mrh30000/go-rpc/pkg/client"
)

// RoundRobinStrategy 轮询策略
type RoundRobinStrategy struct {
    counter atomic.Uint64
}

func (s *RoundRobinStrategy) Select(group *client.RpcGroup, params RouteParams) *client.RpcClient {
    clients := filterEligibleClients(group.GetClients())
    if len(clients) == 0 {
        return nil
    }

    idx := s.counter.Add(1) % uint64(len(clients))
    return clients[idx]
}
```

- [ ] **Step 2: Write test**

```go
func TestRoundRobinStrategy_Select(t *testing.T) {
    strategy := &RoundRobinStrategy{}
    group := createMockGroup()

    // 轮询
    c1 := strategy.Select(group, RouteParams{})
    c2 := strategy.Select(group, RouteParams{})
    c3 := strategy.Select(group, RouteParams{})

    assert.NotNil(t, c1)
    assert.NotNil(t, c2)
    assert.NotNil(t, c3)
    // 验证轮询分布（假设有 2 个客户端）
    assert.NotEqual(t, c1.GetID(), c2.GetID())
    assert.Equal(t, c1.GetID(), c3.GetID())
}
```

- [ ] **Step 3: Run test**

Run: `go test -run TestRoundRobinStrategy ./pkg/router/... -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/router/strategy_roundrobin.go pkg/router/strategy_roundrobin_test.go
git commit -m "feat(router): implement RoundRobinStrategy"
```

---

### Task 25: Refactor Router to Use Strategy Chain

**Files:**
- Modify: `pkg/router/strategy.go:79-109`
- Modify: `pkg/router/router.go`
- Modify: `main.go`

- [ ] **Step 1: Refactor Router struct**

```go
type Router struct {
    strategies struct {
        specified *SpecifiedStrategy
        hash      *ConsistentHashStrategy
        rr        *RoundRobinStrategy
    }
    configSvc config.Service
}

func NewRouter(configSvc config.Service) *Router {
    return &Router{
        strategies: struct {
            specified *SpecifiedStrategy
            hash      *ConsistentHashStrategy
            rr        *RoundRobinStrategy
        }{
            specified: &SpecifiedStrategy{},
            hash:      &ConsistentHashStrategy{ringCache: newRingCache()},
            rr:        &RoundRobinStrategy{},
        },
        configSvc: configSvc,
    }
}
```

- [ ] **Step 2: Refactor Route method**

```go
func (r *Router) Route(group *client.RpcGroup, params RouteParams) *client.RpcClient {
    // 1. SpecifiedClient 最高优先级，硬编码短路
    if params.ClientID != "" {
        return r.strategies.specified.Select(group, params)
    }

    // 2. 按 group 维度读 config key 决定主策略
    switch r.resolveStrategy(params.GroupName) {
    case StrategyConsistentHash:
        if c := r.strategies.hash.Select(group, params); c != nil {
            return c
        }
        // Hash 无可用客户端 → 回退 RR
    }

    return r.strategies.rr.Select(group, params)
}

func (r *Router) resolveStrategy(groupName string) StrategyType {
    if r.configSvc == nil {
        return StrategyRoundRobin
    }

    // 先查分组级配置
    key := "sekiro.routing." + groupName + ".strategy"
    strategy := r.configSvc.GetConfig(key)
    if strategy == "" {
        // 回退全局配置
        strategy = r.configSvc.GetConfig("sekiro.routing.strategy")
    }

    switch StrategyType(strategy) {
    case StrategyConsistentHash:
        return StrategyConsistentHash
    default:
        return StrategyRoundRobin
    }
}
```

- [ ] **Step 3: Update NewRouter call in main.go**

```go
// Before:
s.router = router.NewRouter()

// After:
s.router = router.NewRouter(s.configService)
```

- [ ] **Step 4: Run tests**

Run: `go test -race ./pkg/router/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/router/strategy.go pkg/router/router.go main.go
git commit -m "refactor(router): use Strategy interface chain in Route"
```

---

## B6: Auth/Rate-Limit Observability

### Task 26: Implement noopCollector

**Files:**
- Create: `pkg/metrics/noop_collector.go`
- Test: `pkg/metrics/noop_collector_test.go`

- [ ] **Step 1: Implement noopCollector**

```go
package metrics

// noopCollector 空操作收集器，用于 metrics==nil 时避免空指针
type noopCollector struct{}

func (n *noopCollector) Incr(name string, tags map[string]string, value float64) {}
func (n *noopCollector) Set(name string, tags map[string]string, value float64) {}
func (n *noopCollector) GetMetricsReader() MetricsReader { return &noopReader{} }

type noopReader struct{}

func (n *noopReader) Query(name string, tags map[string]string, from, to int64) ([]MetricPoint, error) {
    return nil, nil
}
```

- [ ] **Step 2: Write test**

```go
func TestNoopCollector_DoesNotPanic(t *testing.T) {
    var c MetricCollector = &noopCollector{}
    assert.NotPanics(t, func() {
        c.Incr("test", nil, 1.0)
        c.Set("test", nil, 1.0)
        c.GetMetricsReader()
    })
}
```

- [ ] **Step 3: Run test**

Run: `go test -run TestNoopCollector ./pkg/metrics/... -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/metrics/noop_collector.go pkg/metrics/noop_collector_test.go
git commit -m "feat(metrics): add noopCollector for nil-safe metric recording"
```

---

### Task 27: Add Metrics to AuthMiddleware

**Files:**
- Modify: `pkg/middleware/auth.go`

- [ ] **Step 1: Add metrics field to AuthMiddleware**

```go
type AuthMiddleware struct {
    userRepo    TokenUserLookup
    groupLookup GroupConfigLookup
    tokenCache  *cache[model.UserInfo]
    groupCache  *cache[model.GroupConfig]
    metrics     MetricCollector  // 可空→用 noop
}
```

- [ ] **Step 2: Initialize metrics in constructor**

```go
func NewAuthMiddleware(userRepo TokenUserLookup, groupLookup GroupConfigLookup, metrics MetricCollector) *AuthMiddleware {
    if metrics == nil {
        metrics = &metrics.noopCollector{}
    }
    return &AuthMiddleware{
        userRepo:    userRepo,
        groupLookup: groupLookup,
        tokenCache:  newCache[model.UserInfo](5 * time.Minute),
        groupCache:  newCache[model.GroupConfig](5 * time.Minute),
        metrics:     metrics,
    }
}
```

- [ ] **Step 3: Add metrics.Incr at deny points**

In `Authenticate` method:

```go
// Line 42: 无 token 拒绝
if token == "" {
    am.metrics.Incr("auth.deny", map[string]string{"reason": "no_token"}, 1)
    c.AbortWithStatusJSON(401, gin.H{"error": "missing token"})
    return
}

// Line 48: token 无效拒绝
user, err := am.FindUserByToken(token)
if err != nil || user == nil {
    am.metrics.Incr("auth.deny", map[string]string{"reason": "invalid_token"}, 1)
    c.AbortWithStatusJSON(401, gin.H{"error": "invalid token"})
    return
}

// Line 264: 非管理员拒绝
if !user.IsAdmin {
    am.metrics.Incr("auth.deny", map[string]string{"reason": "not_admin"}, 1)
    c.AbortWithStatusJSON(403, gin.H{"error": "admin required"})
    return
}
```

- [ ] **Step 4: Run tests**

Run: `go test ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/middleware/auth.go
git commit -m "feat(middleware): add auth.deny metrics to AuthMiddleware"
```

---

### Task 28: Add Metrics to RateLimitMiddleware

**Files:**
- Modify: `pkg/middleware/ratelimit.go`

- [ ] **Step 1: Refactor RateLimitMiddleware to struct**

```go
type RateLimitMiddleware struct {
    limiter   *flow.RateLimiter
    configSvc config.Service
    metrics   MetricCollector
}

func NewRateLimitMiddleware(limiter *flow.RateLimiter, configSvc config.Service, metrics MetricCollector) *RateLimitMiddleware {
    if metrics == nil {
        metrics = &metrics.noopCollector{}
    }
    return &RateLimitMiddleware{
        limiter:   limiter,
        configSvc: configSvc,
        metrics:   metrics,
    }
}
```

- [ ] **Step 2: Add metrics.Incr at reject point**

In `RateLimit` method:

```go
// Line 42: QPS 超限拒绝
if !allowed {
    rlm.metrics.Incr("ratelimit.reject", map[string]string{"type": "user"}, 1)
    c.AbortWithStatusJSON(429, gin.H{"error": "rate limit exceeded"})
    return
}
```

- [ ] **Step 3: Update routes.go**

```go
// Before:
api.Use(middleware.RateLimit(limiter, configSvc))

// After:
rateLimitMW := middleware.NewRateLimitMiddleware(limiter, configSvc, nil)
api.Use(rateLimitMW.RateLimit())
```

- [ ] **Step 4: Run tests**

Run: `go test ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/middleware/ratelimit.go pkg/handler/routes.go
git commit -m "feat(middleware): add ratelimit.reject metrics"
```

---

### Task 29: Add Metrics to AnonymousAccessMiddleware

**Files:**
- Modify: `pkg/middleware/anonymous.go`

- [ ] **Step 1: Add metrics.Incr at deny point**

```go
// AnonymousAccessMiddleware 拒匿名
if !allowAnonymous {
    am.metrics.Incr("auth.deny", map[string]string{"reason": "anonymous_disabled"}, 1)
    c.AbortWithStatusJSON(401, gin.H{"error": "anonymous access disabled"})
    return
}
```

- [ ] **Step 2: Run tests**

Run: `go test ./pkg/middleware/...`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add pkg/middleware/anonymous.go
git commit -m "feat(middleware): add auth.deny metrics for anonymous access"
```

---

### Task 30: Write Metrics Integration Test

**Files:**
- Test: `pkg/middleware/auth_test.go`
- Test: `pkg/middleware/ratelimit_test.go`

- [ ] **Step 1: Write auth metrics test**

```go
func TestAuthMiddleware_Metrics(t *testing.T) {
    mockMetrics := &mockMetricCollector{}
    am := middleware.NewAuthMiddleware(mockRepo, nil, mockMetrics)

    // 无 token
    req := httptest.NewRequest("GET", "/", nil)
    w := httptest.NewRecorder()
    c, _ := gin.CreateTestContext(w)
    c.Request = req

    am.Authenticate()(c)

    assert.Equal(t, 401, w.Code)
    assert.Equal(t, float64(1), mockMetrics.Get("auth.deny", "reason=no_token"))
}
```

- [ ] **Step 2: Write ratelimit metrics test**

```go
func TestRateLimitMiddleware_Metrics(t *testing.T) {
    mockMetrics := &mockMetricCollector{}
    rlm := middleware.NewRateLimitMiddleware(mockLimiter, nil, mockMetrics)

    // QPS 超限
    req := httptest.NewRequest("GET", "/", nil)
    w := httptest.NewRecorder()
    c, _ := gin.CreateTestContext(w)
    c.Request = req

    rlm.RateLimit()(c)

    assert.Equal(t, 429, w.Code)
    assert.Equal(t, float64(1), mockMetrics.Get("ratelimit.reject", "type=user"))
}
```

- [ ] **Step 3: Run tests**

Run: `go test -run TestAuthMiddleware_Metrics ./pkg/middleware/... -v`
Run: `go test -run TestRateLimitMiddleware_Metrics ./pkg/middleware/... -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/middleware/auth_test.go pkg/middleware/ratelimit_test.go
git commit -m "test(middleware): add metrics integration tests"
```

---

## Final Verification

### Task 31: Full Build and Test Suite

- [ ] **Step 1: Run full build**

Run: `go build ./...`
Expected: PASS

- [ ] **Step 2: Run full test suite**

Run: `go test -race ./...`
Expected: PASS

- [ ] **Step 3: Verify B4 success (grep)**

Run: `grep -r "middleware\.\(FindUserByToken\|LookupGroupConfig\|Invalidate\|SetTokenUserRepository\|ShutdownCaches\)" --include="*.go" pkg/ main.go`
Expected: 0 matches in business code (only in tests or comments)

- [ ] **Step 4: Verify B3 success (grep)**

Run: `grep -r "event\.(\*" --include="*.go" main.go pkg/handler/`
Expected: 0 matches (no manual type assertions in subscriptions)

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "chore: full build and test verification"
```

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-28-arch-optimization.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

If Subagent-Driven chosen:
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

If Inline Execution chosen:
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review
