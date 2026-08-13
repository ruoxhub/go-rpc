# go-rpc 可靠性、SDK 与运行诊断演进总纲

日期：2026-08-14
状态：已批准，待按阶段拆分实施 spec

## 1. 背景

对 `grpc-go`、`v2ray-core` 和 `JsRpc` 的源码对比表明，go-rpc 已经具备可复用的路由、传输、熔断、超时、追踪和管理台基础，不需要迁移到另一套协议栈或复制大型插件框架。当前更需要补齐的是调用失败语义、正式 SDK 一致性和连接运行态诊断。

现有实现中有四个直接影响本路线图的事实：

1. 活动服务入口只接入 HTTP/WebSocket；原始 TCP 二进制 detector 没有接入启动链，但 `pkg/client/sdk` 仍使用二进制协议。
2. 调用端在发送后等待响应失败时会继续尝试其他服务端，非幂等 action 可能被重复执行。
3. 服务端超时或调用方断开只清理本地等待记录，执行客户端没有收到取消信号。
4. WebSocket 调用路径当前包含同步 Ping 探测；各语言客户端的重连、状态和协议行为也不一致。

因此，本设计采用向后兼容、按能力纵向切片的演进方式。每项能力必须同时覆盖服务端、适用的正式 SDK、契约测试和文档，不能留下长期不可验证的半成品。

## 2. 目标

- 保持旧客户端注册和普通调用行为不变。
- 明确区分“未执行”“可能已执行”和“已完成”，消除不安全的透明重试。
- 为幂等调用提供受控重试和单进程、有界内存去重。
- 将调用方取消和 deadline 协作式传播到执行端 handler。
- 统一正式执行端 SDK 的连接状态机、重连和销毁语义。
- 将正式 SDK 统一到当前活动的 WebSocket JSON 协议。
- 用缓存健康状态和后台探测替代调用路径上的常态同步 Ping。
- 在现有管理台中提供可授权、可分页、低敏感度的连接诊断视图。
- 通过跨 SDK 黑盒一致性测试定义并证明“同步交付”。

## 3. 非目标

- 不迁移到 gRPC、HTTP/2 或 Protobuf。
- 不重新接通并正式维护原始 TCP 二进制协议。
- 不建设 interceptor 框架、反射式 Feature 注册表或新的传输插件系统。
- 不提供原始 `execjs` 或其他任意代码执行入口。
- 不依赖 PostgreSQL 实现幂等去重，也不承诺跨重启、跨实例 exactly-once。
- 不建设独立 Channelz 式诊断中心或连接历史数据库。
- 不为所有语言同时补齐调用端和执行端两种角色。
- 不在一个大 PR 中实现整份路线图。

## 4. 已确定的设计决策

| 决策点 | 结论 |
|---|---|
| 路线图组织 | 按能力纵向切片，每阶段端到端闭环 |
| 兼容策略 | 新服务端完全兼容旧客户端；新能力只对协商成功的客户端启用 |
| 规范传输 | 正式执行端统一使用 WebSocket JSON |
| 支持矩阵 | Go、TypeScript/Web、Python、Frida、Java/Android/Xposed |
| 发布纪律 | 实验能力默认关闭；全矩阵通过后才能稳定并默认启用 |
| 调用优先级 | 正确性与可靠性优先于诊断和 SDK 易用性 |
| 去重存储 | 单服务进程内的有界内存账本，不依赖数据库 |
| 失败默认 | 未发送可切换；发送后结果未知默认不重试 |
| 取消模型 | 单调用、协作式取消，不断开承载其他调用的连接 |
| 能力协商 | 注册时声明协议版本和能力，服务端返回交集 |
| 健康模型 | 缓存状态、后台探测、路由不等待 Ping |
| 诊断形态 | 复用现有管理台和指标体系 |
| 浏览器能力 | 正式化 TS/Web SDK，不提供 `_execjs` |
| 架构扩展 | 只引入必要的 `InvocationContext`，其他扩展框架继续延后 |
| SDK 分发 | 统一版本和 CI/Release 构建产物；公共仓库发布另行批准 |

## 5. 总体架构与阶段边界

核心调用链保持现有模块边界：

```text
HTTP/SDK 调用入口
  -> 调用上下文规范化
  -> 幂等账本
  -> Router
  -> 转发与等待
  -> WebSocket 执行端
  -> action handler
  -> 响应、日志、指标
```

现有 Router、`transport.Connection` 和 Server 启停流程继续使用。新增职责只有：

- 显式、不可变的 `InvocationContext`
- 连接能力和代际元数据
- 有界幂等账本
- 缓存健康快照与后台探测
- 只读运行诊断快照
- 跨 SDK conformance runner

路线图分为五个顺序阶段：

1. 协议与 SDK 基线
2. 调用正确性
3. 取消与连接生命周期
4. 健康与诊断
5. 稳定化与产品化

每个阶段必须另写实施 spec 和 plan，通过该阶段退出条件后才能开始下一阶段。

## 6. 规范协议与能力协商

### 6.1 规范传输

正式执行端统一使用现有入口：

```text
GET /business/register?group=<group>&clientId=<client-id>
```

Go 执行端 SDK 从原始 TCP 二进制协议迁移到 WebSocket JSON。Go 调用端改用现有 HTTP invoke API。原始二进制协议及依赖它的旧示例保留为 legacy，不承载新能力，也不进入发布门禁。

### 6.2 注册声明与确认

新客户端增加两个可选查询参数：

```text
protocol_version=1
capabilities=invocation_context.v1,cancel.v1
```

服务端规则：

- 未提供 `protocol_version`：按 legacy v1 处理，不发送注册确认或新消息类型。
- 提供受支持版本：鉴权和 WebSocket 升级成功后发送一次 `registered` 消息。
- 注册确认返回服务端当前已启用能力与客户端声明能力的交集。
- 新客户端未收到确认时不得进入 `Ready`。
- 不兼容的协议版本在升级前返回 HTTP 426。
- 未知但格式合法的能力被忽略，不导致注册失败。
- 已发布能力的 `.v1` 语义不可修改；破坏性变化必须使用 `.v2`。
- 实验能力未启用时不进入协商交集。

确认消息至少包含：

```json
{
  "type": "registered",
  "protocol_version": 1,
  "capabilities": ["invocation_context.v1", "cancel.v1"],
  "timestamp": 1786636800000
}
```

能力声明边界：

- 最多 16 项。
- 每项最多 32 个 ASCII 字符。
- 只允许小写字母、数字、点、下划线和连字符。
- 重复项去重。
- 格式非法时在升级前返回 HTTP 400。

能力声明不参与身份认证，也不能提升分组权限。注册确认只能在现有注册鉴权成功后发送。

### 6.3 `InvocationContext`

服务端内部引入显式、不可变的调用上下文，统一承载：

- sequence
- trace ID
- group、action、目标 client ID
- 服务端裁定后的绝对 deadline
- 幂等声明和 idempotency key
- 当前 attempt 编号

Go 的 `context.Context` 只承载取消和 deadline；RPC 业务元数据不散落到 `context.Value`。

协商了 `invocation_context.v1` 的客户端会收到保留对象 `__rpc_context__`。现有 `__sekiro_seq__` 和 `trace_id` 继续保留。未协商该能力时，服务端不发送新上下文字段。

所有正式 SDK 同时提供：

- 保留现有 handler 签名的兼容接口。
- 可读取调用上下文和取消信号的新接口。
- 将旧接口适配到新运行时，但旧 handler 无法感知取消。

sequence、attempt、目标客户端和最终 deadline 以服务端为准。调用方不能覆盖这些字段。幂等键最大 128 字符，非法值在路由前拒绝。

## 7. 执行状态与安全重试

### 7.1 执行状态

每个逻辑调用必须记录以下状态之一：

| 状态 | 含义 | 自动处理 |
|---|---|---|
| `not_started` | 尚未调用底层 `Send`，执行端不可能执行 | 可安全切换服务端或执行客户端 |
| `may_have_run` | 已开始发送，但没有收到可信终态 | 默认不重试 |
| `completed` | 收到成功或业务失败终态 | 默认不重试 |

`Send` 是保守提交边界。一旦调用底层发送，即使返回写错误，也按 `may_have_run` 处理，因为数据可能已经部分或全部到达。

典型映射：

- 参数校验失败、无可用客户端、发送前发现连接已关闭：`not_started`
- 发送后超时、连接中断、响应损坏：`may_have_run`
- 执行端返回成功或业务错误：`completed`
- 调用方取消：按是否越过发送边界选择 `not_started` 或 `may_have_run`

### 7.2 兼容响应

现有 `code/message/data/trace_id` 保持不变，增量增加：

```json
{
  "execution_state": "may_have_run",
  "attempts": 1,
  "idempotency_replayed": false
}
```

现有 `3006 Timeout` 继续使用。新调用端 SDK 将错误码和 `execution_state` 组合成类型化错误，并显式暴露 `MayHaveExecuted`。旧调用方忽略新增字段。

`attempts` 统计实际调用底层 `Send` 的次数；只在发送前选择其他候选节点不增加该计数。

### 7.3 重试规则

- 默认 `max_attempts=1`。
- `not_started` 可对非幂等调用安全故障转移，但不能突破原始 deadline。
- 越过发送边界后，只有同时满足以下条件才能重试：
  - 调用方显式声明 `idempotent=true`
  - 提供非空 `idempotency_key`
  - 显式提供 `RetryPolicy`
  - 目标执行端协商了 `invocation_context.v1`
- `RetryPolicy.max_attempts` 硬上限为 3。
- 不支持并行 hedging。
- 成功、参数错误和普通业务错误不重试。
- 只有连接丢失、结果未知或明确列入 `retryable_codes` 的终态错误可以重试。
- 所有尝试复用 trace ID、idempotency key 和绝对 deadline。
- 每次实际发送生成新 sequence，并递增 attempt。
- 退避使用带 full jitter 的指数退避。
- 剩余 deadline 不足以执行下一次尝试时立即返回当前错误。
- 调用方主动取消后不开始新尝试。

本模型不承诺 exactly-once。`idempotent=true` 是调用方对业务语义的明确承诺，而不是服务端推断。

## 8. 有界内存幂等账本

### 8.1 作用域与请求指纹

服务端在路由前维护一个具体的进程内账本，不为未来数据库实现预建存储接口。

账本键为：

```text
调用者作用域 + group + action + idempotency_key
```

- 已认证请求使用用户或租户作为调用者作用域。
- DB-less 匿名模式退化为 group 作用域。
- 日志和指标只记录幂等键哈希。

首次请求保存请求指纹。指纹覆盖业务参数、指定客户端及路由选择条件，不包含 trace ID、deadline 和重试策略。

- 相同键、相同指纹：同一逻辑调用。
- 相同键、不同指纹：返回 `1002 IdempotencyConflict`，不执行第二次。

### 8.2 状态

`in_flight`：

- 重复请求加入同一结果等待队列，不产生第二次逻辑分派。
- 每个等待者保留自己的等待 deadline。
- 后来的请求不能延长或改变首次请求的执行 deadline 和重试策略。
- 单个等待者取消只移除自己；所有等待者取消后才触发远端取消。

`completed`：

- 保存成功或失败终态响应。
- 重复请求直接重放，不再次执行。
- 重放使用当前 HTTP 请求的 trace ID，并返回原始执行的 `idempotency_origin_trace_id`。

`completed_without_replay`：

- 响应过大或重放字节预算不足时，只保留终态墓碑和摘要。
- 重复请求返回 `3009 IdempotencyResultUnavailable`，不重新执行。

`may_have_run` 也是可缓存终态；TTL 内的同键请求返回相同结果未知状态，不偷偷重新分派。

### 8.3 容量和过期

默认限制：

- 最多 10,000 个未过期逻辑调用。
- 完整响应重放总预算 64 MiB。
- 终态记录从完成时起保留 10 分钟。
- 调用到达正常 deadline 时立即转为 `may_have_run` 终态；deadline 后 30 秒是遗漏终态转换的在途记录的兜底清理期限。

达到条目上限时只清理过期记录，不驱逐未过期终态或在途调用。仍无容量时，新幂等调用返回 `3007 DedupeCapacityExceeded`，不能降级为无去重执行。

兜底清理不能直接删除仍在途的键；它必须先将记录转为 `may_have_run` 的 `completed_without_replay` 墓碑，再按终态 10 分钟 TTL 保留，避免忽略取消的旧 handler 与同键新请求并行执行。

这些限制允许配置。账本关闭时，服务端必须拒绝带自动重试策略的请求，不能静默失去保护。

### 8.4 保证边界

账本只保证同一服务进程、同一作用域和 TTL 内的重复请求不会重复逻辑分派。它不保证：

- 服务重启后的去重
- 多个服务实例之间的全局去重
- 执行端收到请求而服务端丢失结果时的 exactly-once
- 外部业务系统自身的幂等性

## 9. 端到端协作式取消

协商 `cancel.v1` 后，服务端可以向执行端发送：

```json
{
  "type": "cancel",
  "__sekiro_seq__": "sequence-id",
  "reason": "caller_cancelled",
  "timestamp": 1786636800000
}
```

`reason` 只允许：

- `caller_cancelled`
- `deadline_exceeded`
- `server_shutdown`
- `no_waiters`

触发条件：

- HTTP 或调用 SDK 的 context 被取消
- 调用 deadline 到期
- 同一幂等调用的所有等待者均取消
- 服务端优雅关闭超过排空期限

未越过发送边界时不发取消帧。已经发送时最多发送一次，并立即完成服务端本地清理，不等待 ACK。

正式 SDK 保存 `sequence -> handler 取消控制器`：

- Go：`context.Context`
- TS/Web：`AbortSignal`
- Python：异步取消令牌
- Java/Android/Xposed：`RpcCancellationToken`
- Frida：轻量取消令牌；环境支持时适配 `AbortSignal`

handler 未完成时触发令牌，并抑制之后的普通成功响应。handler 已发送响应时忽略迟到取消。handler 不响应取消时可以继续运行，但迟到响应会被服务端丢弃并计入指标。

单次取消不会关闭整条连接。调用方主动取消返回 `3008 Canceled`；deadline 到期继续返回 `3006 Timeout`。两者都携带 `execution_state`。发送后的取消必须标记 `may_have_run`。

首版不增加取消 ACK，也不尝试强杀 handler 线程或进程。

## 10. 统一连接状态机

所有正式执行端 SDK 使用相同语义状态：

```text
Idle -> Connecting -> Ready
          |            |
          v            v
        Failed     Reconnecting -> Connecting
                                      |
                                      v
                                   Shutdown
```

- `Idle`：尚未启动。
- `Connecting`：建连、鉴权和能力协商中。
- `Ready`：收到 `registered`，可以接收调用。
- `Reconnecting`：瞬时失败后的等待或重试过程。
- `Failed`：永久错误，停止自动重试；允许显式重新启动。
- `Shutdown`：`Destroy` 后终态，不能再次启动。

自动重连条件：

- 网络中断或异常关闭
- heartbeat 失效
- HTTP 429、5xx
- 服务端重启或临时不可用

停止自动重连并进入 `Failed`：

- 注册参数非法
- 认证或授权失败
- 协议版本不兼容
- 服务端明确 kick
- 同 client ID 的连接被替换

退避规则：

- 初始 1 秒，乘数 2，封顶 30 秒。
- 使用 full jitter，不限制总重连次数。
- 服务端返回合法 `Retry-After` 时优先遵守。
- `Ready` 连续稳定 30 秒后才重置退避计数。
- 每个 SDK 实例最多一个连接监督任务、一个重连定时器和一个活动 WebSocket。

同一 SDK 实例重连时复用 client ID，并重新声明版本、能力和 actions。连接代际编号隔离旧读循环。连接丢失会取消本地全部在途 handler；SDK 不会在重连后自行重放旧调用。

所有正式 SDK 提供等价能力：

- 幂等 `Start`
- `WaitReady(deadline/context)`
- `State` 和 `LastError`
- 按顺序通知的状态订阅
- 幂等 `Destroy`

现有简化 API 作为适配层保留；新生命周期语义是 conformance 的规范目标。

## 11. 缓存健康状态与后台探测

### 11.1 状态模型

服务端为每个活动客户端分别维护：

- 传输健康：`healthy`、`suspect`、`unreachable`、`offline`
- 业务熔断：沿用 `closed`、`open`、`half_open`

Ping 成功只证明连接存活，不会直接关闭业务失败触发的熔断器。

缓存信号包括：

- 合法应用消息和 heartbeat
- WebSocket Pong 与 RTT
- invoke 成功、业务失败和传输失败
- 连接建立、关闭和替换
- 熔断器状态变化

默认参数：

- 正式 SDK 每 15 秒发送应用层 heartbeat。
- 30 秒没有有效活动进入 `suspect`。
- 后台 Ping 超时 3 秒。
- 60 秒没有有效活动或探测明确失败时关闭并注销连接。
- 探测扫描每 5 秒执行一次并加入抖动。
- 全局最多 32 个并行探测，同一客户端最多一个在途探测。

配置必须满足：

```text
heartbeat interval < suspect threshold < offline timeout
```

### 11.2 后台探测

集中式调度器只探测 `suspect` 或长期空闲客户端：

1. 发送携带探测标识的 WebSocket Ping。
2. Pong handler 记录 RTT 和最后成功时间。
3. 成功后恢复 `healthy`。
4. 超时或写失败后标记 `unreachable`，关闭连接并走正常注销流程。

正常 heartbeat 足够新鲜时不发送额外 Ping。

### 11.3 路由

路由只读取缓存状态：

1. 优先选择 `healthy` 且熔断器允许的客户端。
2. 没有健康客户端时，可选择一个 `suspect` 客户端作为降级候选。
3. `unreachable`、`offline` 或熔断器拒绝的客户端不得参与路由。
4. `half_open` 继续沿用现有单次试探调用语义。

从常态调用路径移除同步 `PingProbe`。若缓存短暂误判，发送失败按 `may_have_run` 和安全重试规则处理。

## 12. 运行诊断

### 12.1 快照

服务端保存活动连接实时快照。连接断开后保留最后快照 15 分钟；最多保留 10,000 个断开客户端快照，容量不足时只淘汰最旧断开快照。

快照包含：

- group、client ID、远端地址
- 连接建立和最后活动时间
- 传输健康、最后探测、Pong RTT
- 熔断状态和连续失败数
- 在途调用数
- 协议版本和已协商能力
- 已注册 actions
- 最近错误类别、脱敏消息和时间
- 最近断开原因

错误消息最多 256 字符，不保存请求载荷、token、堆栈或原始幂等键。

### 12.2 API

新增只读端点：

```text
GET /api/groups/:groupName/clients
GET /api/groups/:groupName/clients/:clientId
```

列表支持 `health`、`connection_state`、`q`、最大 200 的 `limit` 和基于 client ID 的游标分页，并按 client ID 稳定排序。

新字段使用 `snake_case`，时间使用 UTC RFC 3339。接口沿用分组访问控制，对注册分组和当前用户可见匿名分组执行相同授权规则。现有 `/business/clientQueue` 保持兼容，不塞入完整诊断数据。

### 12.3 指标

在现有体系增加：

- 各分组连接状态数量
- 健康状态数量
- 探测 RTT 和失败次数
- 在途调用数量
- 迟到响应和取消后响应数量
- `may_have_run` 调用数量

client ID 不作为指标标签，避免高基数。

### 12.4 管理台

复用 `GroupDetail` 的设备区域：

- 表格增加运行状态、最后活动、RTT、熔断状态和在途数。
- 状态使用图标、文本和语义色，不只依赖颜色。
- 行详情抽屉展示协议能力、actions、最近错误和时间信息。
- 保留现有 kick 操作及危险操作确认。
- 页面可见时每 5 秒刷新，后台暂停，并提供手动刷新。
- 刷新不重置过滤、排序、分页和展开行。

界面保持中性、高密度工作台风格，不增加指标英雄卡、独立导航、渐变工作面或装饰动画。浅色/深色主题、键盘操作和 WCAG 2.1 AA 同时验收。

诊断快照不是审计历史；趋势继续使用现有 metrics 和 traces。

## 13. 正式 SDK 矩阵

| 运行时 | 规范位置 | 正式角色 | 发布产物 |
|---|---|---|---|
| Go | `pkg/client/sdk` | 执行端 + HTTP 调用端 | Go module 源码 |
| TypeScript/Web | `sdk/typescript` | 执行端 | npm 格式 `.tgz`、ESM、浏览器 bundle |
| Python | `sdk/python` | 执行端 + HTTP 调用端 | wheel、sdist |
| Java/Android/Xposed | `sdk/java` | 执行端 | Java 8 JAR、Xposed 示例 APK |
| Frida | `sdk/frida` | 执行端 | 无外部依赖的单文件 JS bundle |

“全部 SDK 同步”按适用角色判断：

- `invocation_context.v1`、`cancel.v1`、状态机和重连覆盖全部正式执行端。
- 幂等请求、类型化结果和 `RetryPolicy` 覆盖 Go、Python 调用端。
- 其他语言可按公开 HTTP 契约调用，但本路线图不新增调用端封装。

唯一实现来源：

- Go 执行端使用 WebSocket JSON，调用端使用 HTTP invoke。
- TS/Web 使用一个协议核心，通过小型 transport adapter 支持浏览器原生 WebSocket 和 Node `ws`。
- Frida 复用 TS 的消息模型、状态机和 fixtures，只实现 Frida WebSocket transport，并输出单文件。
- Python 复用现有 Tornado 依赖实现异步 WebSocket 执行端，保留同步/异步 HTTP 调用能力。
- Java 核心不依赖 Android 或 Xposed API；Xposed 示例消费同一 Java 8 JAR。
- `sample/` 只保留示例，不再承载唯一协议实现。

正式 TS/Web SDK 不注册 `_execjs`。页面能力必须由业务显式注册具名 action。

Legacy 范围：

- 原始 TCP 二进制协议
- 旧 `sample/go`、`sample/java`
- 旧二进制 Python、Frida 实现
- .NET、Objective-C 示例
- Xposed 中已排除编译的旧 Netty SDK 源码

Legacy 不实现新能力、不进入发布门禁，只接受关键安全修复。README 必须标注状态和正式替代路径；删除需要另行发布弃用通知。

## 14. 跨 SDK 一致性测试

### 14.1 结构

```text
conformance/
|- fixtures/       # 版本化 JSON 消息和预期结果
|- scenarios/      # 跨语言共享场景
|- runner/         # 启动服务端、注入故障、收集结果
`- adapters/       # 各 SDK 最小测试入口
```

Go runner 在随机本地端口启动 DB-less 服务端。SDK adapter 只负责启动客户端、注册测试 action、报告状态和销毁，不导入服务端内部包绕过真实协议。Fixtures 作为共享契约，不进行跨语言代码生成。

### 14.2 必测场景

1. 新客户端注册、能力交集和确认
2. legacy 客户端不收到新消息且普通调用不变
3. action bind、普通调用、业务错误和 heartbeat
4. trace、deadline、idempotency key 和 attempt 传播
5. 调用方取消与 deadline 取消抵达 handler
6. 非幂等调用发送后丢响应时不重试
7. 发送前失败安全切换
8. 幂等调用受控重试，trace/key 保持、sequence 更新
9. 同键并发只产生一次逻辑分派
10. 完成重放、同键异参冲突、容量耗尽
11. 异常断线后的状态转换、退避和重新注册
12. kick、鉴权失败、版本不兼容后停止自动重连
13. `Destroy` 后无定时器、连接或 handler 泄漏
14. 取消后的迟到响应被丢弃并计入指标
15. 调用路径不执行同步 Ping

关键验收值：

- 100 个同键并发请求在单进程内只触发一次逻辑分派。
- 取消在本地环回测试中 2 秒内抵达上下文感知 handler。
- `Destroy` 或 kick 后等待两个最大 heartbeat 周期，连接数和重连次数仍为零。
- 所有重试不突破原始 deadline 或 3 次发送上限。

### 14.3 CI 分层

每次 PR：

- Go 全量测试和核心包 `-race`
- 每个 SDK 的单元测试和构建
- 完整协议 fixtures
- 全部正式执行端的基础注册、调用和取消场景
- Go、Python 调用端的重试与幂等场景
- 前端 lint、测试和 build

Nightly：

- 断网、半开连接和响应丢失故障注入
- 重连抖动和并发取消
- 长时间资源泄漏和在途清理
- 多客户端健康探测负载测试

稳定发布：

- 完整跨 SDK 场景矩阵
- legacy 混合版本场景
- Java 核心 JVM 测试和 Xposed APK 构建
- 固定版本 Frida 运行时真实连接烟测
- 所有发布产物及校验文件验证

Android/Xposed 真正注入目标进程的烟测不阻塞普通 PR，但必须为稳定发布留下环境、版本和结果证据。任一正式 SDK 无法完成发布级验证时，对应能力继续保持实验状态。

## 15. 阶段路线图与退出条件

### 阶段 1：协议与 SDK 基线

交付能力协商、注册确认、`InvocationContext`、正式 SDK 目录与构建、基础 conformance 和 legacy 标注。

退出条件：

- 全部正式执行端完成注册、确认、action bind 和普通调用。
- legacy 客户端在新服务端保持原行为。
- 所有 SDK 产物可重复构建。

### 阶段 2：调用正确性

交付执行状态、安全故障转移、内存幂等账本、Go/Python 类型化错误与 `RetryPolicy`。

退出条件：

- 非幂等调用在结果未知后不自动重试。
- 同键并发测试只产生一次逻辑分派。
- 所有尝试遵守 deadline 和三次发送上限。

### 阶段 3：取消与连接生命周期

交付 `cancel.v1`、上下文感知 handler、统一状态机、退避、重连、kick 和连接替换语义。

退出条件：

- 全部正式执行端通过取消与状态迁移测试。
- `Destroy`、kick 后没有重连或资源泄漏。
- 断线后不自动重放旧调用。

### 阶段 4：健康与诊断

交付缓存健康、后台探测、无同步 Ping 路由、聚合指标、诊断 API 和管理台视图。

退出条件：

- 调用路径不等待 Ping。
- 探测并发和频率不突破上限。
- 已知不可达客户端不参与路由。
- 管理台满足主题、响应式和 WCAG 2.1 AA。

### 阶段 5：稳定化与产品化

交付完整 nightly/soak/发布矩阵、安装迁移文档、统一版本产物、默认启用稳定能力和 legacy 政策。

退出条件：

- 发布级矩阵全部通过。
- 全部正式 SDK 有构建产物和 SHA-256。
- 没有未解决的高危安全问题。
- 功能回退演练通过。

## 16. 功能开关与发布纪律

服务端分别维护：

```text
capability_negotiation
safe_retry
cancel_propagation
cached_health
runtime_diagnostics
```

- 实验阶段默认关闭，只在测试或明确配置时启用。
- 只有全部适用 SDK 通过发布矩阵后，才能在后续稳定版本默认开启。
- 服务端只将已启用能力放入协商交集。
- 能力回退时从交集中移除，SDK 退化到基础行为。
- `cached_health` 回退时恢复当前调用前 Ping。
- `runtime_diagnostics` 回退时前端隐藏入口，不影响核心调用。
- 能力协商在阶段 1 稳定后成为基础协议，不再随其他能力关闭。

服务端和正式 SDK 使用同一个仓库 SemVer 标签。稳定发布生成：

- 各 SDK 构建产物
- SHA-256 校验文件
- 协议版本和能力清单
- SDK 支持矩阵
- 迁移说明和变更日志

公共 npm、PyPI、Maven 仓库发布不属于当前门禁。准备好所有权、签名和凭据后分别启用，并要求单独批准。

## 17. 调用所有权与安全

每次实际发送绑定：

```text
sequence + group + client_id + connection_generation
```

只有被分配的连接可以完成调用：

- 同组其他客户端提交相同 sequence 时丢弃并记录安全事件。
- 重连前旧连接提交迟到响应时丢弃并计入指标。
- 每次重试使用新 sequence 和所有权绑定。
- 取消帧只发送到当前绑定连接。
- 执行端发来的 `cancel` 无权取消服务端调用。

其他安全要求：

- 幂等冲突不泄露原请求内容。
- 诊断 API 不返回请求载荷、token、原始幂等键或内部堆栈。
- `ws://` 只用于本地开发；正式 SDK 支持并推荐 `wss://`，不得默认关闭证书验证。
- 探测并发、诊断分页、消息大小和幂等账本必须有硬限制。
- 非法健康阈值、重试上限或容量配置在启动时明确报错。
- 稳定发布前执行 Go、npm、Python 和 Gradle 依赖安全检查。
- 高危或严重依赖问题必须解决，或形成有负责人和期限的风险豁免记录。

## 18. 迁移顺序

兼容保证方向为“新服务端支持旧客户端”。新正式 SDK 依赖注册确认，不静默降级连接到不支持协商的旧服务端。

生产升级顺序固定为：

1. 部署支持能力协商的新服务端。
2. 验证 legacy 客户端继续工作。
3. 发布并逐步替换正式 SDK。
4. 全部适用 SDK 通过矩阵后启用实验能力。
5. 在后续稳定版本中默认启用。

迁移期间允许新旧客户端同时连接。

## 19. 总体验收

路线图完成时必须满足：

- 非幂等调用在发送后结果未知时不自动重试。
- 单进程、同作用域、TTL 内的同键请求不重复逻辑分派。
- 全部正式执行端支持上下文、取消、状态机和重连。
- Go、Python 调用端遵守相同失败和重试语义。
- legacy 客户端继续完成注册和普通调用。
- 常态调用路径不执行同步 Ping。
- 管理台可以区分传输健康、业务熔断和离线状态。
- 所有发布产物可重复构建并带校验文件。
- Frida 无法通过真实 WebSocket 烟测时不得保留“正式支持”标签，必须修订本 spec，不能暗中保留二进制旁路。

设计来源：

- grpc-go：失败语义、取消、连接状态和互操作测试
- v2ray-core：显式调用上下文和后台观测
- JsRpc：浏览器接入体验、action 注册和自动重连

不复制三者的完整协议栈、反射插件系统或远程 `execjs`。

## 20. 后续文档顺序

本总纲批准后，按以下顺序各自完成“子 spec -> 实施 plan -> 实现 -> 验证”闭环：

1. 协议协商与正式 SDK 基线设计
2. 安全调用、幂等账本与重试设计
3. 取消传播与 SDK 生命周期设计
4. 缓存健康、诊断 API 与管理台设计
5. 稳定发布与 legacy 迁移设计

本总纲不直接展开逐文件任务；逐文件改动、测试命令和提交拆分属于各阶段实施 plan。
