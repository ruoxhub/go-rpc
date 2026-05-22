# WebSocket 读循环异步化设计

- Date: 2026-05-22
- Scope: `pkg/server/websocket`, `pkg/server/forwarder`, `pkg/server/client`, `internal/config`
- Status: Approved (pending implementation plan)

## 背景

线上观察到的两类问题，根因都在 `Handler.HandleConnection` 的读循环（`pkg/server/websocket/handler.go:221`）做了不该在读循环里做的事：

1. **`StreamRecord.Push` 5 秒阻塞窗口**（`pkg/server/forwarder/timeout.go:95-112`）
   - 客户端流式响应被慢消费者堵住时，`Push` 持锁等 `ChunkChan` 写入，最长阻塞 5 秒。
   - 同一连接此期间无法读取心跳，超过 `heartbeatTimeout/2` 的 `SetReadDeadline` 后整条连接被判死、断连。
   - 一个慢消费者足以拖垮该连接上的所有其他业务。

2. **`handleHeartbeat` 同步 DB UPDATE**（`pkg/server/websocket/handler.go:328-335`）
   - 每条心跳同步执行 `UPDATE group_device SET last_active_time`，DB 抖动直接传导到读循环。
   - 写入频率与设备数线性相关，没有合并。

## 目标

让 WebSocket 读循环里的两类高频消息（`invoke_stream`、`heartbeat`）退化为纯内存操作：

- Stream chunk 投递：读循环路径 O(微秒)，慢消费者只影响自己的 stream。
- 心跳 last_active_time：读循环不再触 DB，写入频率与设备数解耦。

非目标：

- 不改 `processMessage` 的整体并发模型（保持单读循环 + 顺序解析）。响应/流块依赖 sequence 顺序，全局并行化引入复杂度收益不成正比。
- 不引入 worker pool 或外部队列组件。当前 < 1k 在线连接规模不需要。
- 不动调用端（`SendInvokeRequest`）方向，那条路径不在读循环里。

## 候选方案对比

### Stream chunk 投递

| 方案 | 做法 | 评估 |
|---|---|---|
| **A1 Per-stream forwarder（采用）** | 每个 stream 启一个小 goroutine 持有 inbox 缓冲区，读循环只入 inbox | 读循环零阻塞；故障隔离到单 stream；语义保留 |
| A2 全局 worker pool | N 个 worker 消费全局队列 | 同 sequence 的顺序保证需额外排序逻辑；当前规模不值得 |
| A3 仅扩大 ChunkChan 缓冲 | 不改 push 路径，扩到 256 | 治标不治本，慢消费者打满后仍阻塞读循环 |

### 心跳 DB 写入

| 方案 | 做法 | 评估 |
|---|---|---|
| **B1 in-memory map + 定时 flush（采用）** | `Touch` 写 map，flusher 每 N 秒批量 UPDATE | DB 写入频率与设备数解耦；同设备多次心跳合并；一条 SQL 完成一批 |
| B2 异步 channel + worker | 心跳推 channel，worker 串行 UPDATE | 不去重，DB 写入频率仍 = 心跳频率 |
| B3 立即 goroutine 化 | `go db.Update(...)` | 高频心跳 → goroutine 风暴 + DB 连接占用 |

## 设计

### 整体架构

引入两个组件，由 `websocket.Handler` 持有：

- `forwarder.StreamForwarder` — per-stream 后台 goroutine。`TimeoutManager.RegisterStream` 时创建并启动；stream 完成或超时时销毁。承接读循环送来的 chunk，自己负责往 `ChunkChan` 投递（含可配置背压超时）。
- `client.HeartbeatBatcher` — 单例后台组件。维护 `map[devKey]time.Time`，定时 flush 到 `group_device.last_active_time`。`handleHeartbeat` 调 `Touch(group, deviceID)`，不再走 DB。

> 选择 `pkg/server/client` 而非新建 `devicestate` 包：设备在线状态与 `ClientManager` 同域，避免新增包边界。

### 数据流

```
读循环 ─ invoke_stream ──► StreamForwarder.Submit（非阻塞写 inbox）
                              │
                              ▼ (per-stream goroutine)
                          ChunkChan ──► 调用方 consumer

读循环 ─ heartbeat   ──► HeartbeatBatcher.Touch（仅 map 写）
                                                │
                                                ▼ (flusher goroutine, 每 N 秒)
                                          批量 UPDATE group_device
```

### 组件细节

#### `forwarder.StreamForwarder`

新文件 `pkg/server/forwarder/stream.go`：

```go
type StreamForwarder struct {
    inbox       chan *StreamChunk  // 容量 64
    record      *StreamRecord       // 共享 ChunkChan（外部消费方）
    pushTimeout time.Duration       // 来自 config，默认 5s
    stop        chan struct{}
    done        chan struct{}
}
```

职责：

- `Submit(chunk) bool` — 读循环调用。**非阻塞**写 `inbox`；inbox 满返回 false（调用方据此关流）。
- `run()` — 从 `inbox` 取 chunk，按 `pushTimeout` 投到 `record.ChunkChan`；超时则关流退出。
- `Stop()` — 由 `TimeoutManager` 在 `CompleteStream` / `cleanupExpired` 时调用。

生命周期接线（修改 `pkg/server/forwarder/timeout.go`）：

- `RegisterStream` 末尾启 `go forwarder.run()`；`StreamRecord` 持有 forwarder 引用。
- `cleanupExpired` 与 `CompleteStream` 调用 `forwarder.Stop()`。
- `PushStreamChunk` 改为调用 `forwarder.Submit`，原 `StreamRecord.Push` 删除（其语义被 forwarder 接管）。

#### `client.HeartbeatBatcher`

新文件 `pkg/server/client/heartbeat_batcher.go`：

```go
type devKey struct{ group, deviceID string }

type HeartbeatBatcher struct {
    pending  map[devKey]time.Time
    mu       sync.Mutex
    interval time.Duration         // 来自 config，默认 5s
    db       *gorm.DB              // nil → no-op（DB-less 模式）
    stop     chan struct{}
    wg       sync.WaitGroup
}
```

职责：

- `Touch(group, deviceID)` — `O(1)` map 写入，覆盖旧值（同设备多次心跳合并）。
- `flushLoop()` — `time.Ticker` 触发；swap `pending` 为新空 map，对快照做批量 UPDATE。
- `Shutdown()` — stop signal + 最后一次 flush（带 5s 超时）。

批量 UPDATE 策略（< 1k 设备）：

```sql
UPDATE group_device SET last_active_time = CASE
  WHEN group_name=$1 AND device_id=$2 THEN $3
  WHEN group_name=$4 AND device_id=$5 THEN $6
  ...
END
WHERE (group_name, device_id) IN ((...))
```

GORM 实现：`db.Exec(rawSQL, args...)`，args 由 batcher 拼装。pending > 256 时分批，每批一条 SQL。

#### 接线变更

- `bootstrap.go` 在创建 `Handler` 前实例化 `HeartbeatBatcher`，传入 `HandlerConfig`。
- `HandlerConfig` 新增 `HeartbeatBatcher *client.HeartbeatBatcher` 字段。
- `handleHeartbeat`（`handler.go:321`）DB UPDATE 块替换为 `h.batcher.Touch(msg.Group, msg.ClientID)`。
- `Handler.Shutdown` 调用 `batcher.Shutdown()`。

### 配置

`config.yaml` 新增：

```yaml
WebSocket:
  StreamBackpressureTimeout: 5s   # 单 chunk 入 ChunkChan 的最长等待
  HeartbeatFlushInterval: 5s      # last_active_time 批量写入间隔
```

`internal/config/config.go` 增加 `WebSocketConfig` 结构与默认值。两项均缺省默认 5s，与现状语义一致。

## 错误处理与降级

### Stream forwarder

| 场景 | 行为 |
|---|---|
| inbox 满（消费方持续慢） | `Submit` 返回 false；`PushStreamChunk` 调 `CompleteStream` 关流；记 metric `stream.inbox.full` |
| ChunkChan 投递超时 | forwarder 内部关流，`closeErr = "stream backpressure timeout"`（保留原语义） |
| stream 正常 Done | forwarder 投递 `Done==true` chunk 后退出；`CompleteStream` 兜底 `Stop()` |
| stream 超时（cleanupExpired） | `Stop()` 关 `inbox`；run 循环看到 channel close 后退出 |
| panic | `defer recover()` 兜底，记 error log，关流 |

### Heartbeat batcher

| 场景 | 行为 |
|---|---|
| DB 暂时不可用 | flush 失败 → 记 warn log；将 swap 出的 snapshot **merge 回 pending**（取较新时间），下次重试。不丢心跳 |
| `db == nil`（DB-less 模式） | `Touch` no-op；`flushLoop` 不启动 |
| 进程退出 | `Shutdown` 触发最后一次 flush，带 5s `context.WithTimeout`；超时仍不可写则放弃 |
| pending 异常膨胀 | 单批上限 256，多批顺序提交，避免单条 SQL 过大 |

### 兼容性

- 新 config 项缺省 → 默认 5s，与现状一致。
- 旧测试调 `NewHandler(manager, timeoutMgr, nil, nil)` 仍可用：`HandlerConfig` 缺省构造一个 `db==nil` 的 batcher（no-op）。
- forwarder 对 `PushStreamChunk` 调用方透明：返回值与原 `StreamRecord.Push` 一致。

## 可观测性

新增 metric（接入现有 `pkg/server/metrics.MetricCollector`，沿用项目点号命名风格如 `client.online`）：

- `stream.inbox.full` — `Incr`，tags `{group, action}`，inbox 满计数
- `stream.backpressure.timeout` — `Incr`，tags `{group, action}`，pushTimeout 触发计数
- `heartbeat.batcher.pending` — `Set`（gauge），当前 pending 大小
- `heartbeat.batcher.flush` — `RecordLatency`，单次 flush 耗时
- `heartbeat.batcher.flush.error` — `Incr`，flush 失败计数

`MetricCollector` 由 `bootstrap.go` 注入到两个组件（`StreamForwarder` 经 `TimeoutManager` 间接传入，`HeartbeatBatcher` 直接传入）。`disableMetrics=true` 时传 nil，组件内做 nil 检查跳过。

日志：

- forwarder 关流必带 group/clientID/sequence/原因。
- batcher flush 失败带 pending size 与错误。

## 测试策略

| 层 | 用例 |
|---|---|
| `forwarder/stream_forwarder_test.go`（新增） | 1) 正常 chunk 投递顺序 2) inbox 满返回 false 3) 慢消费触发 pushTimeout 关流 4) Done chunk 后 forwarder 退出 5) Stop 后 Submit 返回 false 6) 并发 Submit + 单消费者 + `-race` |
| `forwarder/timeout_test.go`（增量） | RegisterStream 启 forwarder、CompleteStream 停 forwarder（用 stop chan 探测） |
| `client/heartbeat_batcher_test.go`（新增） | 1) Touch 合并：同 device 多次 Touch 仅一次 UPDATE 且时间为最后一次 2) 多 device 一次 batch UPDATE 3) Shutdown 触发 final flush 4) DB 错误时 pending 回滚保留 5) `db==nil` no-op |
| `websocket/handler_test.go`（改动） | `handleHeartbeat` 改断言 batcher mock 收到 Touch；移除原直接读 GORM 的断言 |
| `websocket/stream_test.go`（增量） | 现有 `TestHandleInvokeStreamRoutesChunkAndFinal` 保留（forwarder 透明）；新增 stress 用例：100 stream + 1 慢消费者，断言其他 stream 路径延迟 < 100ms |

所有新增测试用 `go test -race` 跑。

## 风险与回滚

- **风险 1**：forwarder goroutine 泄漏。缓解：`Stop()` 在 `TimeoutManager` 所有出口调用；测试用 `runtime.NumGoroutine` 探测。
- **风险 2**：batcher flush 的"merge 回 pending"在 DB 长时间不可用时让 pending 无限增长。缓解：< 1k 设备规模上限可控；如需要可后续加 pending size 上限熔断（本次不做）。
- **风险 3**：心跳 flush 间隔默认 5s，使在线判定 `last_active_time > now - 5min` 出现 5s 偏差。可接受（远小于 5min 阈值）。
- **回滚**：两个组件独立可关；将 `StreamBackpressureTimeout` 设为 0 时退化为同步 push（如保留 fallback 路径），或直接 revert commit。本设计不强制保留 fallback。

## 不在本次范围

- `processMessage` 改为 worker pool / 全局并发模型。
- `SendInvokeRequest`（服务器→客户端方向）的异步化。
- 心跳 in-memory 状态分离到独立服务（横向扩容）。
