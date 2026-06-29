# 架构优化实施设计（project-analysis.md 第 4 章 + 裂缝修复）

> 基准代码：`main` 分支 commit `45a0e16`（2026-06-28）  
> 模块路径：`github.com/mrh30000/go-rpc`  
> 关联文档：`docs/project-analysis.md` 第 4 章「二次开发与架构优化建议」  
> 本设计覆盖第 4 章全部 5 条建议 + 2 处代码/文档裂缝修复

---

## 1. 目标与约束

### 1.1 目标
完成 `project-analysis.md` 第 4 章五条架构优化建议，并修复评审发现的 2 处代码/文档裂缝：

1. **裂缝修复**：`eventbus.go:46` 误导注释（写"异步"实为同步）；`RoutingStrategy` 死枚举（定义了但 `Route()` 不引用）。
2. **4.1 DI 改造**：消除 `defaultTokenCache`/`defaultGroupCache`/`tokenUserRepoPtr`/`database.DB` 包级全局，下沉 `AuthMiddleware`，`handler.Deps` 嵌入 `AppDependencies`。
3. **4.2 EventBus 类型安全**：`EventHandler` 改泛型，消除订阅侧手工类型断言，**保持同步派发**。
4. **4.3 路由策略链**：`Strategy` 接口 + 三实现，`Route()` if-else 重构，开闭原则。
5. **4.4 鉴权限流可观测**：鉴权/限流命中拒绝打点 metrics；`AuthChain` 责任链延后。
6. **4.5 配置热更新下沉 EventBus**：`config.Refresh` 走 `SysConfigRepository`；`Update` 后 `Publish(EventConfigChanged)`。

### 1.2 约束（用户确认）

| 约束 | 决定 |
|---|---|
| 实施范围 | 全部 5 条建议 + 2 处裂缝 |
| 破坏性变更 | **部分可破坏**：裂缝/4.1/4.5 可破坏（删包级全局、删死枚举）；4.2 保持同步派发语义（仅加类型安全）；4.3 保持 `SpecifiedClient > Hash > RR` 优先级 |
| DB schema | **不碰**：不加表、不加列；4.3 策略配置走 `sys_config` 现有 key-value 结构的约定 key |
| PR 切分 | **按批次多分支**：6 个独立分支，按依赖顺序合入 |

### 1.3 非目标（YAGNI）
- 一致性 Hash 权重感知（`fingerprint` 仅按 ID 的局限）——留后续。
- `EventBus.Publish` 异步化（worker/缓冲 channel）——保持同步语义，仅做类型安全。
- `AuthChain` 显式责任链——B6.2 延后，B6.1 打点先行。
- `Unsubscribe`/退订 token 方案——删死代码，需要时再引入。
- 前端 `SystemPanel.jsx` 新增路由策略配置项——留 key 约定，前端非本次必做。

---

## 2. 批次切分与依赖

6 个批次，各自独立分支，按依赖顺序：

| 批次 | 范围 | 破坏性 | 依赖 |
|---|---|---|---|
| **B1 裂缝修复** | `eventbus.go:46` 注释；删 `RoutingStrategy` 死枚举 | 零 | 无 |
| **B2 配置热更新** | `Refresh` 走 repository；`EventConfigChanged`；订阅失效 | 低 | B1 |
| **B3 EventBus 类型安全** | `EventHandler`→泛型 `Subscribe[T]`/`Publish[T]`，同步派发 | 中 | B2 |
| **B4 DI 改造** | 删包级全局，下沉 `AuthMiddleware`，`Deps` 嵌入 | 高 | B3 |
| **B5 路由策略链** | `Strategy` 接口 + 三实现，config key 驱动 | 中 | 无（建议 B4 后） |
| **B6 鉴权限流可观测** | auth/ratelimit 打点 + noopCollector；责任链延后 | 中 | B4 |

**依赖链**：B1→B2→B3→B4 为硬依赖（裂缝→事件基础设施→类型安全→DI 落地）；B5 相对独立但建议排 B4 后避免合并冲突；B6 依赖 B4（DI 就位后注入 metrics）。

每批结束都能独立编译、独立测试、独立合入，任一批可回滚不影响前序批次。

---

## 3. B1 裂缝修复（零风险）

### 3.1 修 EventBus 误导注释
`pkg/eventbus/eventbus.go:46` 当前注释写"异步，不阻塞调用方"，实际实现（53-55 行）是同步 `for _, handler := range handlers { handler(event) }`。

改为如实注释：
```go
// Publish 向所有注册的处理器发布事件。
// 当前为同步派发：在调用方 goroutine 内顺序调用所有 handler，
// 慢订阅者会阻塞发布者。如需异步语义，由订阅方自行启动 goroutine。
```
> B3 仍保持同步派发（不改发布语义），注释在 B1 先改对。

### 3.2 删 RoutingStrategy 死枚举
`pkg/router/strategy.go:16-26` 的 `RoutingStrategy`/`RoundRobin`/`SpecifiedClient`/`ConsistentHash` 全仓无引用（仅定义、注释、文档出现，无变量/参数/字段使用）。删除。B5 落地策略链时以 `Strategy` 接口重新引入，不恢复 int 枚举。

### 3.3 验证
`go build ./...` + `go test ./pkg/eventbus/... ./pkg/router/...`。

---

## 4. B2 配置热更新下沉 EventBus

### 4.1 问题回顾
- `config/service.go:143` `Refresh(db *gorm.DB)` 直连 `db.Find(&configs)`，绕过 `SysConfigRepository`。
- `sysconfig.go:113`、`main.go:237` 直连 DB 刷新。
- 无事件通知：其他路径改 `sys_config` 表时，消费方（tokenCache/groupCache）不自动失效。

### 4.2 修正：真实消费方分析
核对代码后修正文档 4.5 的设想：
- **限流器无需订阅**：`flow.RateLimiter.Allow(key, qps)` 每次调用从 `configService` 取阈值传入，阈值变化天然即时生效。
- **IP 白名单无需订阅**：`main.go:535` 每次 `configService.GetConfig(ConfigKeyAllowedIPs)` 直读内存 `sync.Map`，`service.Refresh()` 已原子替换 `sync.Map`，即时生效。
- **tokenCache/groupCache 才是缺口**：当前只在改密/删用户等显式点 `InvalidateToken`/`InvalidateGroup`，配置侧 user/group 相关 key 变更走不到失效路径。

故 B2 真正改动只有两件：Refresh 走 repository；新增事件 + tokenCache/groupCache 订阅。

### 4.3 Refresh 改走 SysConfigRepository
- `SysConfigRepository.FindAll()` 已存在（`interfaces.go:98`），无需新增接口方法。
- `service` 结构体新增 `repo repository.SysConfigRepository` 字段（构造注入）。
- `Refresh(db *gorm.DB) error` → `Refresh() error`，内部 `repo.FindAll()` 替代 `db.Find`。
- `repo==nil` 时跳过（DB-less 模式），保留原"db==nil 跳过"语义。
- 调用点 `sysconfig.go:113`、`main.go:237` 去掉 `db` 参数。
- **`NewSysConfigHandler` 签名变更**：当前 `NewSysConfigHandler(deps.SysConfigRepo, deps.ServerNodeRepo, deps.SysLogRepo, cfgSvc, deps.DB)`（`routes.go:37`），B2 后 `SysConfigHandler` 不再需 `db`（`Refresh()` 无参、走 repo），去掉末尾 `db *gorm.DB` 参数；`SysConfigHandler` 结构体的 `db` 字段（`sysconfig.go:19`）一并移除。

### 4.4 新增 EventConfigChanged + 变更 key 集合
- `pkg/eventbus/events.go` 新增 `EventConfigChanged = "config.changed"` + `ConfigChangedEvent{ Keys []string }`。
- `service.Refresh()` 内：整体 FNV hash 仍作"是否变化"快判（保留 `lastConfigsHash`）；变化时逐 key diff 产出 `changedKeys`，`eb.Publish(EventConfigChanged, ConfigChangedEvent{Keys: changedKeys})`。
- 事件 payload 携带**变更 key 集合**而非整体配置，消费方按关心 key 过滤，不关心的静默跳过。
- `service` 持有 `*eventbus.EventBus`（构造注入）。
- B3 后 `Publish` 改为 `Publish[ConfigChangedEvent]`。

### 4.5 消费方订阅（仅 tokenCache/groupCache）
- tokenCache/groupCache：订阅 `EventConfigChanged`，命中 user/group 相关 key 时调 `InvalidateToken`/`InvalidateGroup`。
- B2 阶段缓存仍是包级全局（B4 才下沉），订阅回调调包级 `InvalidateToken`/`InvalidateGroup`；B4 下沉后随实例迁移为方法调用。

### 4.6 验证
`go test ./pkg/config/... ./pkg/eventbus/...`；补 `Refresh` 产出 `changedKeys` 单测；补订阅 `EventConfigChanged` 触发 `InvalidateToken` 的集成测试。

---

## 5. B3 EventBus 泛型类型安全（保持同步派发）

### 5.1 目标
消除订阅侧手工类型断言（当前两种分裂：`main.go:259-273` 直接断言无 `ok` 短路、断言失败 panic；`invoke.go:93-99` `if ok` 安全断言、断言失败静默跳过），用泛型在编译期绑定事件类型 T。**发布语义不变**（同步派发）。

### 5.2 新 API
```go
func Subscribe[T any](eb *EventBus, eventType string, handler func(T))
func Publish[T any](eb *EventBus, eventType string, event T)
```
调用方改造示例（`main.go:259`）：
```go
// 改造前
s.eventBus.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
    e := event.(*eventbus.ClientConnectEvent)   // 无 ok，panic 风险
    ...
})
// 改造后
eventbus.Subscribe(s.eventBus, eventbus.EventClientConnect, func(e eventbus.ClientConnectEvent) {
    ...   // 无断言，T 已绑定
})
```

### 5.3 约定：事件 T 为值类型
所有事件 T 为**值类型**（`ClientConnectEvent` 等），发布传值、订阅收值。当前发 `&Event{}` 指针的习惯统一改为传值（事件结构体都 <100 字节，值拷贝无性能问题），消除"发指针/断言值"分裂。

### 5.4 内部存储与派发
- `EventBus.handlers` 仍存 `map[string][]EventHandler`，`EventHandler` 保留 `func(interface{})` 作为内部擦除类型。
- `Subscribe[T]` 入口把 `func(T)` 包装成 `func(interface{})`，内部做一次类型断言 `e := ev.(T)`——断言集中在库内一处，由编译期 T 约束保证成立；运行时失败（仅库 bug 或反射绕过）**panic**（契约违反，不静默）。
- `Publish[T]` 把 `event T` 装入 `interface{}` 投递，同步 `for` 调用，派发语义与 B1 标注一致。

### 5.5 死代码清理
- `Unsubscribe`/`funcEqual`（`helper.go`）全仓无调用，B3 删除。避免泛型包装导致 `funcEqual` 按 reflect 指针比对失效（每次 `Subscribe[T]` 产生新闭包，指针不同）。

### 5.6 迁移点
| 文件 | 改造 |
|---|---|
| `main.go:259-273` | 3 个订阅改 `Subscribe[T]`，去手工断言（消除 panic 风险） |
| `pkg/handler/invoke.go:93-99` | 2 个订阅改 `Subscribe[T]`，去 `if ok` 静默跳过 |
| `pkg/client/manager.go:155` | `Publish` 改 `Publish[T]`，传值 |
| `pkg/websocket/handler.go:152,160` | 2 个 `Publish` 改 `Publish[T]` |
| `pkg/handler/invoke.go:170,189` | 2 个 `Publish` 改 `Publish[T]` |
| `pkg/client/manager_test.go`、`pkg/eventbus/eventbus_test.go` | 测试改 `Subscribe[T]`/`Publish[T]` |
| `pkg/eventbus/helper.go` | 删 `funcEqual` |
| `pkg/eventbus/eventbus.go` | 删 `Unsubscribe`，加泛型 `Subscribe[T]`/`Publish[T]`，保留同步派发 |

### 5.7 验证
`go test -race ./pkg/eventbus/... ./pkg/client/... ./pkg/handler/... ./pkg/websocket/...`；补 `Subscribe[T]` 类型不匹配时 panic 的测试（用 `recover` 断言），固化"库内统一 panic"契约。

---

## 6. B4 DI 改造（删包级全局，下沉 AuthMiddleware）

### 6.1 目标
消除 `defaultTokenCache`/`defaultGroupCache`/`tokenUserRepoPtr`/`database.DB` 四个包级全局；`handler.Deps` 嵌入 `deps.AppDependencies`；包级 `FindUserByToken`/`LookupGroupConfig`/`InvalidateToken`/`InvalidateGroup`/`SetTokenUserRepository`/`ShutdownCaches` 全部退役，由 `AuthMiddleware` 方法承载。**不保留 wrapper**，一次性迁移（"部分可破坏"授权）。

### 6.2 AuthMiddleware 扩展为完整鉴权服务
当前 `AuthMiddleware`（`auth.go:277`）已持有 `userRepo/tokenCache/groupCache`，仅缺 `FindUserByToken`/`LookupGroupConfig`/`Invalidate*`。补齐：
```go
type AuthMiddleware struct {
    userRepo    TokenUserLookup
    groupLookup GroupConfigLookup   // 注入：典型为 groupRepo.FindGroupByName
    tokenCache  *cache[model.UserInfo]
    groupCache  *cache[model.GroupConfig]
    metrics     metrics.MetricCollector  // B6 注入，可空→用 noop
}
func (am *AuthMiddleware) FindUserByToken(token string) (*model.UserInfo, error)
func (am *AuthMiddleware) LookupGroupConfig(name string) (*model.GroupConfig, error)
func (am *AuthMiddleware) InvalidateToken(token string)
func (am *AuthMiddleware) InvalidateGroup(name string)
func (am *AuthMiddleware) Shutdown()   // 替代包级 ShutdownCaches
```
`cache[T]` 实例从包级 `var` 变为字段（构造时 `newCache`，含 GC 协程），`main.go` 构造唯一实例注入。B2 的 `EventConfigChanged` 订阅回调改为 `am.InvalidateToken/InvalidateGroup`（B4 后天然就位）。

### 6.3 调用点迁移清单
| 文件:行 | 当前 | 改后 |
|---|---|---|
| `main.go:224` | `SetTokenUserRepository(appDeps.UserRepo)` | 构造 `authMW := NewAuthMiddleware(...)` 注入，`authMW` 成 `Server` 字段 |
| `main.go:259-273` | 包级 `Subscribe`+断言 | B3 已改泛型；回调内调 `s.authMW` |
| `main.go:546` | `middleware.LookupGroupConfig(name, s.groupRepo.FindGroupByName)` | `s.authMW.LookupGroupConfig(name)` |
| `main.go:570` | `middleware.FindUserByToken(token)` | `s.authMW.FindUserByToken(token)` |
| `main.go:623` | `middleware.ShutdownCaches()` | `s.authMW.Shutdown()` |
| `handler/invoke.go:626,658,667` | 包级 `LookupGroupConfig`/`FindUserByToken` | `h.authMW.*`（`APIHandler` 增 `authMW` 字段） |
| `handler/login.go:87` | `middleware.FindUserByToken` | `h.authMW.FindUserByToken`（`LoginHandler` 增字段） |
| `handler/user.go:142,160,219,220` | `middleware.InvalidateToken` | `h.authMW.InvalidateToken`（`UserHandler` 增字段） |
| `handler/group.go:122,172,236` | `middleware.InvalidateGroup` | `h.authMW.InvalidateGroup`（`GroupHandler` 增字段） |
| `handler/anonymous.go:325` | `middleware.InvalidateGroup` | `h.authMW.InvalidateGroup`（`AnonymousHandler` 增字段） |
| `routes.go:51` | `middleware.Authenticate()` 包级 | `authMW.Authenticate()` 方法版 |
| `routes.go:37` | `NewSysConfigHandler(..., deps.DB)` | B2 后 `Refresh()` 不吃 DB，去掉 `deps.DB` 参数；`SysConfigHandler` 的 `db` 字段移除（见 4.3） |

> `routes.go:46-50` 往 context 塞 `configService`/`groupRepo` 的中间件是另一处隐式全局，本次**不改**（避免回归扩面），作为 legacy 兼容保留。

### 6.4 handler.Deps 嵌入 AppDependencies
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
消除 `UserRepo`/`GroupRepo`/`DB` 三字段重复声明。

### 6.5 database.DB 处置（务实偏离）
- **不删 `database.DB` 变量**：`database.go:79` `ConfigurePool` 内部仍引用 `DB.DB()`，且 `login_test.go:21` 测试靠改写 `database.DB` 隔离。删变量牵连连接池配置与测试隔离。
- **改为进程内单例 + 业务代码不直读**：`database.DB` 仅由 `database` 包内部（`InitFromConfig`/`ConfigurePool`/`GetDB`）维护，业务代码全部走 `deps.AppDependencies.DB` 或 repository。grep 确认当前业务代码已无 `database.DB` 直读（仅 test 和 database 包内部），B4 强化 `AGENTS.md`/`db_helper.go` 注释"禁止业务代码引用"。
- **偏离说明**：这偏离文档 4.1"移除 `database.DB` 全局"的字面方案，但符合其精神（业务代码不再依赖全局）。删变量收益小、回归大，务实保留。

### 6.6 测试改造
- `auth_token_test.go`/`auth_cache_test.go`/`auth_test.go`：从包级 `defaultTokenCache`/`FindUserByToken` 改为构造 `AuthMiddleware` 实例调方法。`auth_cache_test.go:102-175`"备份-替换包级 `defaultGroupCache`"写法消失——每测试构造独立实例，天然隔离。
- `ratelimit_test.go:21` 的 `Refresh(db *gorm.DB)` mock 签名随 B2 改 `Refresh()`。
- `login_test.go:21` 的 `database.DB` 隔离写法保留（B4.5 不删变量）。

### 6.7 验证
`go build ./...` + `go test -race ./pkg/middleware/... ./pkg/handler/... ./cmd/... ./.`；GitNexus impact 评估 `FindUserByToken`/`LookupGroupConfig`/`InvalidateToken`/`InvalidateGroup`/`Authenticate`（跨包公共 API，预期 HIGH，改前向用户报告）。

---

## 7. B5 路由策略链（Strategy 接口 + config key 驱动）

### 7.1 目标
`Route()` 的 if-else 链（`strategy.go:79-109`）重构为 `Strategy` 接口 + 三实现，开闭原则；策略选择由 `config.Service` 运行期 key 驱动，**不碰 DB schema**；`SpecifiedClient` 保持最高优先级硬编码短路。

### 7.2 Strategy 接口
```go
type Strategy interface {
    Select(group *client.RpcGroup, params RouteParams) *client.RpcClient
}
```
三实现（独立文件）：
- `strategy_specified.go`：`SpecifiedStrategy`（含 `Fuzzy` 分支）
- `strategy_hash.go`：`ConsistentHashStrategy`（封装现有 `routeByConsistentHash` + ringCache）
- `strategy_roundrobin.go`：`RoundRobinStrategy`（封装现有 `routeByRoundRobin` + counter + `filterEligibleClients`）

### 7.3 不引入显式责任链
文档 4.3 提"策略链 Chain of Responsibility"——**不引入**。理由：当前优先级是固定硬语义（`SpecifiedClient` 永远最高、`ConsistentHash` 失败回退 RR），用"短路 + 回退"的 Router 编排比责任链更直白。责任链的可重排性是当前用不到的灵活性（YAGNI）。策略拆为独立 `Strategy` 实现已可独立单测，可测性目标达成。

### 7.4 Router 重构
```go
type Router struct {
    strategies struct {
        specified *SpecifiedStrategy
        hash      *ConsistentHashStrategy
        rr        *RoundRobinStrategy
    }
    configSvc config.Service   // 读 routing key（可空，空则默认 RR）
}

func (r *Router) Route(group *client.RpcGroup, params RouteParams) *client.RpcClient {
    // 1. SpecifiedClient 最高优先级，硬编码短路（不读 config）
    if params.ClientID != "" {
        return r.strategies.specified.Select(group, params)
    }
    // 2. 按 group 维度读 config key 决定主策略
    switch r.resolveStrategy(params.GroupName) {
    case StrategyConsistentHash:
        if c := r.strategies.hash.Select(group, params); c != nil {
            return c
        }
        // 3. 一致性 Hash 无可用客户端 → 回退 RR
    }
    return r.strategies.rr.Select(group, params)
}
```
- `resolveStrategy(groupName)` 读 `config.Service` key，缺省/解析失败 → RoundRobin。
- `ConstantInvoke`/`HashKey` 仍驱动一致性 Hash（保留 `shouldUseConsistentHash`/`buildConsistentHashKey`）：主策略是 Hash 时，若 `params` 无 hashKey 且 ConstantInvoke 未启用，Hash 策略内部返回 nil → 回退 RR。保留现有隐式触发逻辑。

### 7.5 config key 设计（不碰 DB）
复用 `sys_config` 现有 key-value 结构，新增**约定 key**（非 schema 变更）：
- `sekiro.routing.strategy`：全局默认策略，值 `round_robin`/`consistent_hash`。
- `sekiro.routing.<group>.strategy`：分组级覆盖（可选，缺省回退全局）。
`config.Service` 已支持 `GetConfig(key)`，无需新接口。前端配置项非本次必做（留 key 约定）。

### 7.6 偏离文档说明
- 文档 4.3 原方案"`group_config` 加 `routing_strategy` 字段"→ 改走 `sys_config` key 约定（用户选"不碰 DB schema"）。
- 文档 4.3"一致性 Hash 支持虚拟节点权重"→ 本次不做（YAGNI，需改 `ConsistentHashRing.Add` 签名 + 权重数据源，留后续）。

### 7.7 调用点
唯一调用点 `handler/invoke.go:280` `h.router.Route(group, params)` **不变**——`RouteParams` 字段不变、`Route` 签名不变，B5 是 `pkg/router` 内部重构，对 handler 透明。`Router` 构造从 `NewRouter()` 改 `NewRouter(configSvc)`，`main.go` 调用处加参数。

### 7.8 测试
- `strategy_specified_test.go`/`strategy_hash_test.go`/`strategy_roundrobin_test.go`：三策略独立单测（现有 `strategy_test.go` 拆分重组）。
- `Route` 集成测试：`SpecifiedClient` 短路优先级、Hash 失败回退 RR、config key 切换主策略、缺省 RR。
- `resolveStrategy` 单测。

### 7.9 验证
`go test -race ./pkg/router/...`；GitNexus impact 评估 `Route`/`Router`（HIGH，跨包公共，改前报告）。

---

## 8. B6 鉴权限流可观测 + 责任链（可选）

### 8.1 拆分
文档 4.4 把"打点"和"责任链"绑定，本设计**拆分**：
- B6.1 metrics 打点（本次必做）：低风险、即时可观测。
- B6.2 `AuthChain` 责任链（延后）：风险高、性价比低，B6.1 稳定后再评估。

### 8.2 B6.1 metrics 打点
`MetricCollector.Incr(name, tags, value)` 已有（`collector.go:118`）。在拒绝点补打点：

| 位置 | metric name | tags |
|---|---|---|
| `auth.go:42` 无 token 拒绝 | `auth.deny` | `{reason:"no_token"}` |
| `auth.go:48` token 无效拒绝 | `auth.deny` | `{reason:"invalid_token"}` |
| `ratelimit.go:42` QPS 超限拒 | `ratelimit.reject` | `{type:"user"\|"anonymous"}` |
| `auth.go:264` 非管理员拒 | `auth.deny` | `{reason:"not_admin"}` |
| `AnonymousAccessMiddleware` 拒匿名 | `auth.deny` | `{reason:"anonymous_disabled"}` |

**注入**：`AuthMiddleware` 增 `metrics metrics.MetricCollector` 字段（B4 已埋点）。`RateLimitMiddleware` 改接收 `metrics` 参数或构造为结构体方法。

**Null Object**（呼应文档 2.11）：`pkg/metrics` 加 `noopCollector{}` 实现 `MetricCollector`，`metrics==nil` 时用 noop，避免每打点处 `if metrics != nil` 散判。

**告警接入**：`alert.Evaluator` 已周期评估 `AlertRule` 对比 `MetricRepository`。`auth.deny`/`ratelimit.reject` 落库后（三级聚合），用户配 `AlertRule`（`metric_name="ratelimit.reject"`，`operator=">"`，`threshold=N`，`window=5`）告警。**不改 alert 引擎**，复用现有规则评估链路。

### 8.3 B6.2 AuthChain 责任链（延后）
定义 `AuthStep interface { Check(c *gin.Context) *AuthResult }`，`AuthChain` 持有 `[]AuthStep` 顺序执行，`AuthResult{Allow bool, DenyReason string}` 短路。`routes.go:45-54` 中间件链改由 `AuthChain` 装配。

**延后理由**：当前中间件链已是 Gin 装饰器（本质责任链），`AuthChain` 主要是把"装饰器顺序"改"显式链节点结构"，可测性收益有限（B6.1 打点已达成可观测）；风险高（需保证不破坏匿名分组放行、回环 IP 放行、`SpecifiedClient` 短路）。建议 B6.1 落地稳定后再评估。

### 8.4 验证
`go test -race ./pkg/middleware/... ./pkg/metrics/...`；补打点单测（mock collector 断言 `Incr` 调用）；补 `noopCollector` 不 panic 测试。GitNexus impact 评估 `Authenticate`/`RateLimitMiddleware`（B4 已评 `Authenticate`，B6 复用）。

---

## 9. 风险与回滚

### 9.1 高风险批次
- **B4**：删包级全局触面广（12 处调用点 + 6 个 handler 增字段），跨包公共 API `FindUserByToken` 等 impact 预期 HIGH。**改前必须 GitNexus impact 报告 + 补单测兜底**。回滚：单分支可整体回退，不影响 B1-B3 已合入。
- **B5**：`Route`/`Router` 跨包公共，impact HIGH。但触面集中在 `pkg/router` 内部、对 handler 透明，回归风险实际低于 B4。

### 9.2 中低风险批次
- B1：零风险（删未引用类型、改注释）。
- B2：低（接口已就绪、触面小）。
- B3：中（订阅 API 变形，但同步语义不变，迁移点明确）。
- B6：B6.1 低（加打点 + noop），B6.2 延后。

### 9.3 回滚策略
每批独立分支，任一批可整体回退不影响前序。B4 若影响面评估超预期，可降级为方案 B（保留包级 wrapper 内部转调），但本次设计默认方案 A（一次性迁移）。

---

## 10. 文档同步

合入后更新 `docs/project-analysis.md`：
- 1.3.4 注明 `RoutingStrategy` 枚举已删（B1），路由走 `Strategy` 接口（B5）。
- 1.3.12 / 2.4 注明 EventBus `Subscribe[T]`/`Publish[T]` 泛型化、同步派发（B3），`Unsubscribe` 已删。
- 2.4 缺陷栏更新"类型断言"为"库内统一 panic 契约"。
- 1.4 技术债表更新：包级全局已消除（B4）、`database.DB` 业务代码隔离（B4.5）、`handler.Deps` 嵌入 `AppDependencies`（B4.4）。
- 4.1-4.5 各节标注"已实施于本设计，见 docs/superpowers/specs/2026-06-28-arch-optimization-design.md"。
- 附录"DI"行更新为"手动 Constructor Injection + AppDependencies（包级全局已消除）"。

---

> 本设计基于 `main` 分支 commit `45a0e16`（2026-06-28）。实施时各批次改前必须先跑 GitNexus `impact` 评估并报告 HIGH/CRITICAL 风险，改后跑 `detect_changes` 验证影响面。
