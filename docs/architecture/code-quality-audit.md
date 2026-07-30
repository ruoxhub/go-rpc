# go-rpc 代码质量审计报告

> 审计范围：全代码库（350 文件，Go + React 反向 RPC 代理）
> 审计维度：安全 / 并发与性能 / 数据库与资源 / 可维护性与结构
> 严重程度：P0（严重，立即修复）> P1（重要，本迭代修复）> P2（一般，排期优化）
> 说明：行号为审计时定位，可能随版本微调，请以 `file:line` 上下文为准；搜索引擎受环境限制，结论均基于逐文件 `read_file` 确认。

---

## 一、P0 严重问题（立即修复）

### 1.1 CORS 全通配 + WebSocket 无 Origin 校验 + 管理面鉴权缺位（组合越权）
- **位置**：
  - `pkg/handler/websocket.go:64-67`（WS 升级 `CheckOrigin` 恒为 `true`）
  - `internal/config/config.go:153`（`CorsOrigins` 默认 `["*"]`）
  - `pkg/middleware/cors.go:21-23`（`Allow-Credentials:true` 与通配 Origin 配合）
  - `main.go:502-523`（webAdmin 管理面路由需确认是否挂 `RequireAdmin`）
- **问题**：任意跨站源可建立 WebSocket 连接；带凭据的 CORS 反射任意 Origin；管理面若未强制 `RequireAdmin`，匿名用户可操作 group/user/alert/sysconfig。
- **影响**：跨站 WebSocket 劫持、CSRF、越权管理，属高危组合漏洞。
- **修复**：
  1. `CheckOrigin` 改为按可信 host/CORS 白名单校验。
  2. 含凭据时禁止反射任意 Origin，白名单不可含 `"*"`；默认空列表。
  3. 管理面（`/business`、`/v1`、`/api` 之外的所有 webAdmin 路由）强制 `RequireAdmin` 中间件。

### 1.2 SQL 注入（表名 / 列名拼接）
- **位置**：
  - `pkg/database/repository/metric_store.go:100`（`DeleteExpired` 用 `fmt.Sprintf` 拼表名 `DELETE FROM %s`）
  - `pkg/database/repository/metric_store.go:124`（`QueryMetricMinutes` 用 `fmt.Sprintf("%s = ?", column)` 拼列名，列名来自用户/配置可控的 tag 名）
- **问题**：表名与列名直接拼接进原生 SQL，存在注入与误删风险。
- **修复**：表名用白名单校验或 `Table()` 安全 API；列名仅允许 `tag1..tag5` 固定白名单，禁止动态列名拼接。

### 1.3 StreamRecord 并发重复 close 导致 panic
- **位置**：
  - `pkg/forwarder/timeout.go:65-79`（`CloseWithError` 未用 `sync.Once`）
  - `pkg/forwarder/timeout.go:362-378`（`PushStreamChunk` 失败分支 `delete` + `CompleteStream` 与超时关闭竞态）
- **问题**：`Push`（超时关闭）与 `CompleteStream`/`RemoveStream` 并发时可能重复 `close(done)` / `close(ChunkChan)` 触发 panic。
- **修复**：`CloseWithError` 用 `sync.Once` 包裹关闭逻辑；`PushStreamChunk` 失败分支不再重复关闭。

### 1.4 熔断器递归加锁死锁
- **位置**：`pkg/client/circuit_breaker.go:67-92`（`Allow()` 在 `CircuitOpen` 分支 `cb.mu.Lock()` 后递归调用 `cb.Allow()`）
- **问题**：非可重入锁递归加锁，导致死锁。
- **修复**：递归调用前 `cb.mu.Unlock()`，或抽出无锁的内部辅助函数（`allowLocked`）。

### 1.5 大面积重复代码（可维护性 / 一致性风险）
- **位置**：
  - `pkg/handler/chat.go:213-317` 与 `pkg/handler/qwen.go:264-395`（流式 SSE 循环近 100 行逐行重复）
  - `pkg/handler/chat.go:170-211` 与 `pkg/handler/qwen.go:151-495`（unary "Add+Send+Wait+select" 三段式重复 3 处）
  - `pkg/handler/login.go:35-77` 与 `pkg/handler/login.go:360-396`（两套 `HandleLogin` 近乎一致，`loginUserRepo`/`loginGroupRepo` 全局变量与 DI 并存）
  - `pkg/handler/websocket.go:27-56` 与 `main.go:617-641`（两套 register 实现，且 WS 版跳过了 `authorizeRegisterAccess` 鉴权）
- **问题**：同一逻辑多份实现且行为不一致（如 WS register 漏鉴权），后续修复需多处同步，极易遗漏。
- **修复**：抽取公共流式响应驱动函数 + emit 回调；统一 `dispatchInvoke` 辅助；删除重复的 `HandleLogin` 与 register 实现，统一走 `authorizeRegisterAccess`。

### 1.6 分组注册鉴权失效（越权访问）
- **位置**：
  - `main.go:643-667`（`authorizeRegisterAccess` 对 `group==nil` 直接放行；`groupRepo==nil` 时 `return true`）
  - `pkg/handler/invoke.go:618-645`（`authorizeRegisteredGroupAccess` 当 `groupRepo==nil` 直接 `return true`）
  - `pkg/handler/invoke.go:647-682`（`filterAccessibleGroups` DB 异常时保守放行）
- **问题**：repo 缺失或异常时放行而非拒绝，未注册分组可任意注册抢占，故障期可泄露注册分组列表。
- **修复**：repo 缺失/异常应**拒绝**或返回空列表；匿名分组注册加基础鉴权与频控。

---

## 二、P1 重要问题（本迭代修复）

### 2.1 认证与授权
| 位置 | 问题 | 修复 |
|---|---|---|
| `pkg/handler/login.go:290-291,334-335` | token 用 `uuid.New()`，无过期/撤销/审计，可无限 `RefreshToken` 轮换 | 用 `crypto/rand` 长随机令牌 + 过期时间 |
| `pkg/handler/user.go:212-224` | `RefreshToken` 用 UUID 且立即 `InvalidateToken(newToken)` 把未下发的新 token 置无效，逻辑矛盾 | 用 `crypto/rand`，避免预失效 |
| `pkg/handler/user.go:61-116` | `Add` 可设 `IsAdmin=true`，若路由未挂 `RequireAdmin` 任意用户可自建管理员 | 创建管理员必须 `RequireAdmin` |
| `pkg/handler/user.go:33-52` | `List` 返回所有用户（含 `isAdmin`），未鉴权可枚举 | 挂 `RequireAdmin` |
| `pkg/handler/group.go:39-70` | 分组归属鉴权依赖 `authorizeGroupAccess`，需核实拒绝非归属非管理员 | 统一公共 `authorizeGroup` |
| `pkg/handler/trace.go:39-57` | `GetTraceDetail` 仅按 `traceId` 查，未校验用户是否有权查看（含 userName/请求体） | 按用户/分组维度隔离 |
| `pkg/handler/alert.go:160-195,234-272` | WebhookURL 存储后触发时发请求 → SSRF | 协议/内网地址白名单校验 |
| `pkg/middleware/auth.go:104-107` | 允许从 `PostForm("token")` 取 token → CSRF | 仅用 `Authorization`/自定义头 |
| `pkg/handler/login.go:244-306` | 开放注册默认开启（`ConfigKeyAllowRegister` 默认 true） | 生产默认关闭 |

### 2.2 并发与性能
| 位置 | 问题 | 修复 |
|---|---|---|
| `pkg/client/manager.go:94-116` | `Unregister` 读 `ClientCount()==0` 即删组 `Close()`，并发 `Register` 已拿同组写入 → 连接泄漏 | 用 refcount 或 Close 前二次校验 |
| `pkg/client/group.go:332-335` | `ClientCount`/`HasClient` 走异步 commandChan，计数存在窗口，可能误删有 client 的组 | actor 内原子计数 |
| `pkg/client/group.go:114-158` | `allocate()` 切片旋转 `O(n)` 复制，客户端多时成为热点 | 环形索引/链表 |
| `pkg/router/strategy.go:228-246` | `routeByRoundRobin` 每次 `GetAllClients()` + 两次复制，高 QPS 大量分配与 channel 往返 | actor 内分配 / 缓存 snapshot |
| `pkg/router/strategy.go:148-177` | 一致性哈希指纹仅 8 字节易碰撞，ring 缓存未随健康状态失效 | 增大指纹，按 health 二次校验 |
| `pkg/websocket/handler.go:541-546` | `SendInvokeRequest` 每次发 Ping 控制帧（3s deadline），高并发拉低吞吐 | 仅无最近活跃/概率采样时探测 |
| `pkg/handler/invoke.go:487-508` | 每请求起 goroutine 调 `Wait`，超时内阻塞（最长 5min），高并发 goroutine 堆积 | 复用/限制 goroutine |
| `pkg/handler/invoke.go:338` | `GetSequence` 用 `UnixNano()`，同纳秒并发生成相同 sequence → 响应串流 | 加随机后缀/原子计数器 |
| `pkg/flow/ratelimit.go:109` | `Wait(key, qps)` 传 `nil` context，令牌耗尽永久阻塞 | 传带超时 context 或改用 `Allow` |
| `pkg/eventbus/eventbus.go:35-44` | `Publish` 同步派发，慢订阅者阻塞发布者，handler panic 炸发布者 | 派发加 `recover`/异步 |
| `pkg/alert/evaluator.go:162-166` | `Stop()` 直接 `close(e.shutdown)` 无 Once，重复调用 panic | `sync.Once` 包裹 |

### 2.3 数据库与资源
| 位置 | 问题 | 修复 |
|---|---|---|
| `pkg/handler/user.go:33` | `List` 无分页全表扫描，返回 `Password`/`LoginToken`/`ApiToken` 等敏感字段 | 加分页 + `Select` 限定字段 |
| `pkg/handler/user.go:61` / `login.go:266` | `CountByUserName`+`Create` 非原子，并发重复注册竞态 | 唯一索引 + `ON CONFLICT` |
| `pkg/database/repository/group_repo.go:76` | `GetGroupStats` 跨大表 `GROUP BY` 全量聚合无过滤/分页 | 加索引+分页 |
| `pkg/database/repository/trace_repo.go:84` | `GetStats` 串行 6 次 COUNT/AVG/MAX/MIN，且 `Where` 累积污染 | 单条聚合 SQL |
| `pkg/database/repository/trace_repo.go:19` | `FindByQuery` 缺省时间窗退化为全表排序 | 强制默认时间范围 |
| `pkg/database/repository/metric_repo.go:61` | `GetLatencyPercentiles` 用 `LIKE` 且无 `time_key` 范围，扫整表 | 强制 `time_key` 范围 |
| `pkg/handler/sysconfig.go:206` | `GetAppLogs` 的 `total` 用 `len(logs)`（仅当前页），分页总数错误 | 用 `Count` 查真实总数 |
| `pkg/database/database.go:128` | 生产默认每次启动 `AutoMigrate`，隐式改表结构/锁表风险 | 生产用 `RPC_DISABLE_AUTO_MIGRATE=true` + 增量脚本 |
| `pkg/handler/metric.go:54` / `trace.go:88` | 默认 limit=100，缺时间窗扫整表 | 强制时间窗/降低默认 limit |

### 2.4 可维护性
| 位置 | 问题 | 修复 |
|---|---|---|
| `pkg/handler/invoke.go:599-605` | 魔法串 `msg == "Request timeout"` 判断错误码 | 传枚举错误码 |
| `pkg/handler/sysconfig.go:182, login.go:200` | `GetAppLogs` 接收 `level` 却忽略，接口误导 | 实现 level 过滤/脱敏 |
| `pkg/handler/sysconfig.go:206-236` | handler 内手拼原始 SQL、硬编码电平，违反分层且 `total` 错误 | 下沉 repository 层 |
| `pkg/handler/login.go:48/371` | `err != nil || user == nil` 合并判断，DB 错误当"用户名或密码错误" | 区分错误类型 |
| `pkg/websocket/handler.go:431` / `http_server.go:158-178` | `json.Marshal/Unmarshal` 错误被忽略；`sameOriginOrNoOrigin` 定义未接线 | 处理错误/接线死代码 |
| `pkg/client/client.go:40` | `NewCircuitBreaker(3, 15*time.Second)` 硬编码不可配置 | 纳入 config |
| 多处 | 超时 `30*time.Second`、端口 `5612`、配额 `100` 散落硬编码 | 统一常量来源 |

---

## 三、P2 一般问题（排期优化）

### 3.1 安全
- `pkg/middleware/auth.go:110-127`：Subprotocol 隐藏 token 注释"比 query 更隐蔽"，但代理/日志可能记录 `Sec-WebSocket-Protocol`，不宜承载长期凭据。
- `pkg/middleware/trace.go:77-103`：`fastRandFloat64` seed 用 `time.Now().UnixNano()` 可预测，须保持仅采样用途。
- `pkg/handler/login.go:106-121`：`HandleSystemInfo` 匿名返回内部配置（cors/mode/port/host），收敛或鉴权。
- `pkg/handler/websocket.go:39,51` / `chat.go:135` / `qwen.go:102`：Debug 日志记录 group/clientId/userName 高频连接信息泄露，生产降级。
- `pkg/middleware/ratelimit.go:37-45`：匿名限流 key 用 `ClientIP()`，攻击者伪造 `X-Forwarded-For` 绕过，应从受信代理取真实 IP。

### 3.2 并发与性能
- `pkg/metrics/collector.go:163-220`：histogram `Observations` 无限增长、每次 flush 全量排序、upsert 写放大；改用固定分桶/HdrHistogram。
- `pkg/config/service.go:175-187`：`Refresh` 持锁期间 `Publish` 同步派发，且整体替换 `sync.Map` 有短暂空窗口；先释放锁再 Publish，增量 Store。
- `pkg/alert/notifier.go:95`：`SendWebhook` 用 `context.Background()` 无超时，设 `client.Timeout`。
- `pkg/client/group.go:103,211-213`：`go client.Close()` 未限流，瞬时大量断连爆发 goroutine；用 worker pool/信号量。
- `pkg/transport/ws_conn.go:24`：`Send` 写 deadline 固定 10s，慢客户端阻塞并发 Send；加 context。
- `pkg/router/hash.go:21-31`：一致性哈希虚拟节点仅 5 个，分布不均；可调 vnode 数。

### 3.3 数据库与资源
- `pkg/database/database.go:16`：全局 `*gorm.DB` 单例仍被旧路径依赖，持续替换为 DI。
- `pkg/config/service.go:159`：`Refresh` 每次 `FindAll()` 全表读，加刷新间隔/懒加载。
- `deploy/postgres/migration.sql:8`：初始化脚本开头 `DROP TABLE ... CASCADE`，误连生产清空数据，加环境校验。
- `deploy/postgres/migration.sql:137,223`：补 `(name, time_key)`、`(group, start_time)`、`(api, start_time)` 复合索引。
- `pkg/database/repository/metric_store.go:41`：`RollupHours/Days` 用 `time_key LIKE` 依赖字符串前缀顺序，改确定性 `BETWEEN`。
- `pkg/alert/notifier.go:131`：邮件头 `To/Subject/Body` 拼接，CRLF 注入；做 CRLF 清洗。
- `pkg/database/repository/sysconfig_repo.go:35`：`Upsert` 仅 `Update`，key 不存在静默无插入，改 `ON CONFLICT DO UPDATE`。
- `pkg/handler/group.go:334`：`AddAction` 先查后插非事务，并发唯一约束冲突，用 `OnConflict DO NOTHING`。

### 3.4 可维护性
- `pkg/handler/http_server.go:54-60` 与 `websocket.go:64-66`：两处各建允许任意 Origin 的 Upgrader，复用并收紧。
- `pkg/handler/alert.go:145,249,279`：三次 `fmt.Sscanf(id, "%d", &ruleID)`，抽 `parseIDParam`。
- `pkg/handler/sysconfig.go:54-68`：`labelMap` 14 个 key→标签与 `config/service.go` 常量重复，标签随常量走。
- `main.go:87` 与 `http_server.go:29` 与 `DefaultConfig():88`：端口 5612 三处重复。
- `pkg/handler/trace.go:145`：`json.Unmarshal(ExtraData,...)` 错误忽略。
- `internal/config/config.go` 与 `config_v2.go` 各自定义 `Config`，命名混乱，加包注释区分。
- `pkg/handler/invoke.go:80`：`NewAPIHandler` 8 参数过长，`router` 内部新建应注入。
- `pkg/handler/authz.go` + `invoke.go:618` + `main.go:643`：三套分组鉴权未抽公共。
- `internal/toolcall` 单包 19 文件、部分 15KB+；`internal/promptcompat` 与 `internal/prompt` 功能重叠，待拆分。
- `pkg/utils` 与 `internal/utils` 双 utils 目录，跨层 import 易混淆，澄清分层边界。

---

## 四、修复路线建议（按优先级）

1. **第 1 批（安全止血）**：1.1（CORS/WS Origin/管理面鉴权）、1.2（SQL 注入）、1.6（分组注册鉴权）、2.1 中未挂 `RequireAdmin` 的路由、SSRF webhook 白名单。
2. **第 2 批（稳定性）**：1.3（StreamRecord panic）、1.4（熔断器死锁）、2.2 中 goroutine 堆积/`GetSequence` 串流/ratelimit nil context、`Stop()` Once。
3. **第 3 批（性能与数据库）**：2.3 分页/聚合/索引/AutoMigrate 开关、2.2 路由分配热点、metrics flush。
4. **第 4 批（可维护性）**：1.5 重复代码抽取、2.4 魔法串/分层、3.4 常量与死代码清理。

> 每项均可独立提交 PR；建议从 P0 起逐条修复并补充对应单测（重点覆盖鉴权分支、SQL 注入白名单、并发 close/锁路径）。
