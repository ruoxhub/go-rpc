# Stage 1 Protocol and SDK Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持 legacy 客户端行为不变的前提下，交付可开关的注册能力协商、`invocation_context.v1`、四套正式 WebSocket JSON 执行端 SDK、Go/Python HTTP 调用端和阶段 1 跨语言一致性门禁。

**Architecture:** 活动入口仍为 `GET /business/register`，新协议只通过可选查询参数和一次 `registered` 确认增量扩展。Go 服务端在现有 `SendInvokeRequest` 共同发送点构造不可变 `InvocationContext`，只向协商成功的连接注入 `__rpc_context__`；各语言 SDK 各自实现同一份公开 wire contract，不进行跨语言代码生成。阶段 1 不实现取消、自动重试、去重账本或完整重连状态机。

**Tech Stack:** Go 1.25、Gin、gorilla/websocket、TypeScript/ESM、浏览器原生 WebSocket、Node `ws`、Python 3.10+、Tornado、httpx、Java 8、OkHttp 3、Gradle、JSON fixtures、PowerShell 验证脚本。

## Global Constraints

- 设计来源为 `docs/superpowers/specs/2026-08-14-go-rpc-reliability-evolution-roadmap-design.md`；与其冲突时停止实现并修订 spec。
- 正式执行端传输统一为 WebSocket JSON；活动注册地址保持 `GET /business/register?group=<group>&clientId=<client-id>`。
- 正式支持矩阵仅为 Go、TypeScript/Web、Python、Java/Android/Xposed。
- Frida 保持 experimental/legacy，不创建 `sdk/frida`，不进入普通 PR、nightly 或稳定发布门禁。
- `RPC_CAPABILITY_NEGOTIATION` 初始默认 `false`；关闭时完全走 legacy 路径，不解析版本、不发送 `registered`。
- 阶段 1 服务端只启用 `invocation_context.v1`；`cancel.v1` 留给阶段 3。
- 未提供 `protocol_version` 的连接按 legacy v1 处理，不发送确认和 `__rpc_context__`。
- 能力声明最多 16 项，每项 1–32 个 ASCII 字符，只允许 `[a-z0-9._-]`，重复项去重，未知合法项忽略。
- `protocol_version` 非 `1` 时在升级前返回 HTTP 426；能力格式非法时在升级前返回 HTTP 400。
- 注册鉴权必须先于 WebSocket 升级；`registered` 必须在连接进入 Online/Ready 和 action bind 之前成功写出。
- 浏览器 SDK 的 token 使用现有单一子协议 `sekiro-auth.<token>`；其他 SDK 使用 `Authorization: Bearer <token>`，token 不进入 URL query。
- 保留 `__sekiro_seq__` 和 `trace_id`；只有协商了 `invocation_context.v1` 才增加 `__rpc_context__`。
- `__rpc_context__` 的 deadline 使用服务端裁定的 Unix 毫秒绝对时间；阶段 1 固定 `attempt=1`、`idempotent=false`、`idempotency_key=""`。
- 正式 TS/Web SDK 不注册或暴露 `_execjs` 或其他任意代码执行入口。
- WebSocket 单帧继续限制为 10 MiB；正式 SDK 支持 `wss://` 且不得关闭证书验证。
- 不新增协议插件框架、代码生成器、数据库表或第三方发布动作。
- 新服务端必须继续接受 legacy 客户端；新正式 SDK 不静默降级连接到缺少注册确认的旧服务端。
- 每个任务先写失败测试，再做最小实现；每个提交都必须独立构建和可回滚。
- 修改 `main.handleRegister`、`websocket.HandleConnection` 或 `websocket.SendInvokeRequest` 前必须记录 GitNexus 影响分析；当前代码图已将这些路径标为 CRITICAL。

## File Structure

### Shared Go contract and server

- Create `pkg/protocol/wsjson.go` — WebSocket JSON 消息、能力名、注册协商和 wire context。
- Create `pkg/protocol/wsjson_test.go` — 协商边界、去重、未知能力和 JSON 兼容性测试。
- Create `pkg/invocation/context.go` — 服务端内部值类型 `InvocationContext` 及 wire 转换。
- Create `pkg/invocation/context_test.go` — deadline 与 wire 字段测试。
- Modify `internal/config/config.go` — `RPC_CAPABILITY_NEGOTIATION` 配置。
- Modify `internal/config/server_config_test.go` — 默认关闭和环境变量读取测试。
- Modify `.env.example` — 实验开关说明。
- Modify `main.go` — 鉴权后的预升级协商和 versioned connection 分派。
- Modify `main_test.go` — 400/426、legacy 无确认、新客户端确认集成测试。
- Modify `pkg/client/client.go` — 每条服务端连接保存只读协议版本和能力集合。
- Create `pkg/client/client_test.go` — 能力快照和并发读取测试。
- Modify `pkg/websocket/handler.go` — 注册确认、协议别名和条件式 context 注入。
- Modify `pkg/websocket/handler_test.go` — 确认顺序、legacy 兼容和 context 注入回归测试。

### Formal SDKs

- Rewrite `pkg/client/sdk/client.go` — Go WebSocket JSON 执行端。
- Rewrite `pkg/client/sdk/client_test.go` — Go 执行端黑盒协议测试。
- Rewrite `pkg/client/sdk/invoker.go` — Go HTTP 调用端。
- Rewrite `pkg/client/sdk/invoker_test.go` — HTTP 契约和单次发送测试。
- Create `sdk/typescript/` — TypeScript 核心、browser/node transport、测试与 npm pack 配置。
- Create `sdk/python/` — Tornado 执行端、同步/异步 httpx 调用端、测试与 wheel/sdist 配置。
- Create `sdk/java/` — 保持现有 `cn.iinti.sekiro3.business.api` 公共包名的 Java 8 核心 JAR、测试和独立 Gradle 工程。
- Modify `sample/xposed/settings.gradle` — 通过 composite build 引入正式 Java SDK。
- Modify `sample/xposed/app/build.gradle` — 消费正式 JAR module。
- Delete the exact duplicate modern Java sources listed in Task 9 only after the app consumes `sdk/java`; demo imports remain source-compatible.

### Conformance, release artifacts, and docs

- Create `conformance/fixtures/registration-v1.json` — 注册协商输入与期望。
- Create `conformance/fixtures/invoke-context-v1.json` — versioned/legacy invoke wire 期望。
- Create `conformance/adapters/go/main.go` — Go 黑盒 adapter。
- Create `conformance/adapters/typescript.mjs` — TypeScript 黑盒 adapter。
- Create `conformance/adapters/python.py` — Python 黑盒 adapter。
- Create `conformance/runner/main.go` — 启动 DB-less 服务端并运行正式 SDK adapters。
- Create `scripts/build-sdk-artifacts.ps1` — 本地构建 `.tgz`、wheel、sdist、JAR、APK 和 SHA-256。
- Modify `scripts/verify.ps1` — 加入 SDK unit/build 与阶段 1 conformance。
- Modify `README.md` and relevant sample README files — 正式矩阵、迁移和 legacy 标签。

## Execution Order

任务 1–6 必须顺序执行。任务 7–9 在任务 6 通过后可以并行实现，但每个任务仍需独立评审。任务 10 依赖全部四套正式执行端；任务 11–12 最后执行。

---

### Task 1: Freeze the WebSocket JSON Contract

**Files:**
- Create: `pkg/protocol/wsjson.go`
- Create: `pkg/protocol/wsjson_test.go`
- Create: `conformance/fixtures/registration-v1.json`
- Create: `conformance/fixtures/invoke-context-v1.json`

**Interfaces:**
- Produces: `protocol.NegotiateRegistration(versionRaw, capabilitiesRaw string, enabled []string) (protocol.Registration, error)`
- Produces: `protocol.LegacyRegistration() protocol.Registration`
- Produces: `Registration.Supports(string) bool`
- Produces: `protocol.WSMessage`, `protocol.WireInvocationContext`
- Produces constants: `CurrentProtocolVersion`, `CapabilityInvocationContextV1`, and all current WebSocket message types.

- [ ] **Step 1: Write failing negotiation tests**

```go
func TestNegotiateRegistration(t *testing.T) {
	enabled := []string{CapabilityInvocationContextV1}
	tests := []struct {
		name, version, capabilities string
		wantLegacy                 bool
		wantCaps                   []string
		wantErr                    error
	}{
		{name: "legacy", wantLegacy: true},
		{name: "supported", version: "1", capabilities: "unknown.v1,invocation_context.v1,invocation_context.v1", wantCaps: []string{CapabilityInvocationContextV1}},
		{name: "unsupported version", version: "2", wantErr: ErrUnsupportedProtocolVersion},
		{name: "invalid uppercase", version: "1", capabilities: "Cancel.v1", wantErr: ErrInvalidCapabilities},
		{name: "invalid empty item", version: "1", capabilities: "a.v1,,b.v1", wantErr: ErrInvalidCapabilities},
		{name: "too many raw items", version: "1", capabilities: "a,a,a,a,a,a,a,a,a,a,a,a,a,a,a,a,a", wantErr: ErrInvalidCapabilities},
		{name: "item too long", version: "1", capabilities: strings.Repeat("a", 33), wantErr: ErrInvalidCapabilities},
		{name: "non ascii", version: "1", capabilities: "能力.v1", wantErr: ErrInvalidCapabilities},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := NegotiateRegistration(tt.version, tt.capabilities, enabled)
			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("error = %v, want %v", err, tt.wantErr)
			}
			if got.Legacy != tt.wantLegacy || !slices.Equal(got.Capabilities, tt.wantCaps) {
				t.Fatalf("registration = %#v", got)
			}
		})
	}
}
```

- [ ] **Step 2: Run the tests and verify the missing contract fails**

Run: `go test ./pkg/protocol -run 'TestNegotiateRegistration|TestWSMessageJSON' -count=1`

Expected: FAIL because the negotiation types and constants do not exist.

- [ ] **Step 3: Implement the exact contract**

```go
const (
	CurrentProtocolVersion        = 1
	CapabilityInvocationContextV1 = "invocation_context.v1"
	MessageTypeRegistered         = WSMessageType("registered")
	MessageTypeHeartbeat          = WSMessageType("heartbeat")
	MessageTypeInvoke             = WSMessageType("invoke")
	MessageTypeInvokeResponse     = WSMessageType("invoke_response")
	MessageTypeInvokeStream       = WSMessageType("invoke_stream")
	MessageTypeBind               = WSMessageType("bind")
)

var (
	ErrUnsupportedProtocolVersion = errors.New("unsupported protocol version")
	ErrInvalidCapabilities        = errors.New("invalid capabilities")
)

type Registration struct {
	Legacy          bool
	ProtocolVersion int
	Capabilities    []string
}

type WSMessageType string

func LegacyRegistration() Registration {
	return Registration{Legacy: true, ProtocolVersion: CurrentProtocolVersion}
}

func (r Registration) Supports(capability string) bool {
	for _, current := range r.Capabilities {
		if current == capability {
			return true
		}
	}
	return false
}

type WireInvocationContext struct {
	Sequence       string `json:"sequence"`
	TraceID        string `json:"trace_id"`
	Group          string `json:"group"`
	Action         string `json:"action"`
	ClientID       string `json:"client_id"`
	DeadlineUnixMS int64  `json:"deadline_unix_ms"`
	Idempotent     bool   `json:"idempotent"`
	IdempotencyKey string `json:"idempotency_key"`
	Attempt        int    `json:"attempt"`
}

type WSMessage struct {
	Type            WSMessageType          `json:"type"`
	Sequence        string                 `json:"sequence,omitempty"`
	RpcSeq          string                 `json:"__sekiro_seq__,omitempty"`
	Group           string                 `json:"group,omitempty"`
	ClientID        string                 `json:"clientId,omitempty"`
	Actions         []string               `json:"actions,omitempty"`
	Data            json.RawMessage        `json:"data,omitempty"`
	Error           string                 `json:"error,omitempty"`
	Status          int                    `json:"status,omitempty"`
	Done            bool                   `json:"done,omitempty"`
	Timestamp        int64                  `json:"timestamp,omitempty"`
	TraceID          string                 `json:"trace_id,omitempty"`
	ProtocolVersion int                    `json:"protocol_version,omitempty"`
	Capabilities    []string               `json:"capabilities,omitempty"`
	RPCContext      *WireInvocationContext `json:"__rpc_context__,omitempty"`
}

func (m WSMessage) GetSequence() string {
	if m.RpcSeq != "" {
		return m.RpcSeq
	}
	return m.Sequence
}
```

Implement `NegotiateRegistration` with these exact rules:

```go
func NegotiateRegistration(versionRaw, capabilitiesRaw string, enabled []string) (Registration, error) {
	if versionRaw == "" {
		return LegacyRegistration(), nil
	}
	if versionRaw != strconv.Itoa(CurrentProtocolVersion) {
		return Registration{}, ErrUnsupportedProtocolVersion
	}
	declared, err := parseCapabilities(capabilitiesRaw)
	if err != nil {
		return Registration{}, err
	}
	declaredSet := make(map[string]struct{}, len(declared))
	for _, capability := range declared {
		declaredSet[capability] = struct{}{}
	}
	intersection := make([]string, 0, len(enabled))
	for _, capability := range enabled {
		if _, ok := declaredSet[capability]; ok {
			intersection = append(intersection, capability)
		}
	}
	return Registration{ProtocolVersion: CurrentProtocolVersion, Capabilities: intersection}, nil
}
```

`parseCapabilities` must check the raw item count before deduplication, reject empty items, scan bytes against `[a-z0-9._-]`, and preserve first occurrence order.

- [ ] **Step 4: Add stable JSON fixtures**

`conformance/fixtures/registration-v1.json`:

```json
{
  "protocol_version": 1,
  "declared_capabilities": ["unknown.v1", "invocation_context.v1"],
  "enabled_capabilities": ["invocation_context.v1"],
  "registered": {
    "type": "registered",
    "protocol_version": 1,
    "capabilities": ["invocation_context.v1"]
  }
}
```

`conformance/fixtures/invoke-context-v1.json`:

```json
{
  "versioned_required_fields": [
    "type",
    "action",
    "__sekiro_seq__",
    "trace_id",
    "__rpc_context__"
  ],
  "rpc_context_required_fields": [
    "sequence",
    "trace_id",
    "group",
    "action",
    "client_id",
    "deadline_unix_ms",
    "idempotent",
    "idempotency_key",
    "attempt"
  ],
  "legacy_forbidden_fields": ["__rpc_context__"]
}
```

- [ ] **Step 5: Run protocol tests and commit**

Run: `gofmt -w pkg/protocol/wsjson.go pkg/protocol/wsjson_test.go`

Run: `go test ./pkg/protocol -count=1`

Expected: PASS.

```bash
git add pkg/protocol/wsjson.go pkg/protocol/wsjson_test.go conformance/fixtures
git commit -m "feat(protocol): define websocket capability contract"
```

---

### Task 2: Add the Experimental Capability Gate

**Files:**
- Modify: `internal/config/config.go`
- Modify: `internal/config/server_config_test.go`
- Modify: `.env.example`
- Modify: `main.go`
- Modify: `main_test.go`

**Interfaces:**
- Produces: `ServerConfig.CapabilityNegotiation bool`
- Produces: `Server.negotiateRegistration(*gin.Context) (protocol.Registration, bool)`
- Consumes: Task 1 protocol errors and `NegotiateRegistration`.

- [ ] **Step 1: Add failing config tests**

```go
func TestCapabilityNegotiationDefaultsOff(t *testing.T) {
	t.Setenv("RPC_CAPABILITY_NEGOTIATION", "")
	if DefaultServerConfig().CapabilityNegotiation {
		t.Fatal("CapabilityNegotiation must default to false")
	}
}

func TestCapabilityNegotiationReadsEnv(t *testing.T) {
	t.Setenv("RPC_CAPABILITY_NEGOTIATION", "true")
	if !LoadServerConfigFromEnv().CapabilityNegotiation {
		t.Fatal("CapabilityNegotiation was not loaded")
	}
}
```

- [ ] **Step 2: Verify the config tests fail**

Run: `go test ./internal/config -run CapabilityNegotiation -count=1`

Expected: FAIL because the field is absent.

- [ ] **Step 3: Add the field, default, loader, and documented env value**

```go
type ServerConfig struct {
	CapabilityNegotiation bool `env:"RPC_CAPABILITY_NEGOTIATION"`
}
```

Merge the field into the existing struct, set it to `false` in `DefaultServerConfig`, and load it with:

```go
CapabilityNegotiation: envBool("RPC_CAPABILITY_NEGOTIATION", d.CapabilityNegotiation),
```

Append to `.env.example`:

```dotenv
# Experimental stage-1 handshake. Legacy behavior remains the default.
RPC_CAPABILITY_NEGOTIATION=false
```

- [ ] **Step 4: Write failing negotiation helper tests**

Add a table test in `main_test.go` with a DB-less test server and the flag enabled. Build a Gin test context for each query, call `s.negotiateRegistration(c)` directly, and assert `ok`, status, and JSON error:

```go
tests := []struct {
	query      string
	wantStatus int
}{
	{query: "protocol_version=2", wantStatus: http.StatusUpgradeRequired},
	{query: "protocol_version=1&capabilities=Cancel.v1", wantStatus: http.StatusBadRequest},
	{query: "protocol_version=1&capabilities=a.v1,,b.v1", wantStatus: http.StatusBadRequest},
}
```

These focused tests intentionally stop before the active route; Task 3 wires the helper and adds the pre-upgrade route assertions.

- [ ] **Step 5: Implement negotiation after authorization and before upgrade**

```go
func (s *Server) negotiateRegistration(c *gin.Context) (protocol.Registration, bool) {
	if s.serverConfig == nil || !s.serverConfig.CapabilityNegotiation {
		return protocol.LegacyRegistration(), true
	}
	registration, err := protocol.NegotiateRegistration(
		c.Query("protocol_version"),
		c.Query("capabilities"),
		[]string{protocol.CapabilityInvocationContextV1},
	)
	switch {
	case errors.Is(err, protocol.ErrUnsupportedProtocolVersion):
		c.JSON(http.StatusUpgradeRequired, gin.H{"error": err.Error()})
		return protocol.Registration{}, false
	case err != nil:
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return protocol.Registration{}, false
	default:
		return registration, true
	}
}
```

Do not call this helper from `handleRegister` in this task. Task 3 introduces the version-aware connection method and wires both changes in one independently compiling commit.

- [ ] **Step 6: Run focused tests and commit**

Run: `gofmt -w internal/config/config.go internal/config/server_config_test.go main.go main_test.go`

Run: `go test ./internal/config . -run 'CapabilityNegotiation|BusinessRegister' -count=1`

Expected: config and focused negotiation helper tests PASS.

```bash
git add internal/config/config.go internal/config/server_config_test.go .env.example main.go main_test.go
git commit -m "feat(server): gate websocket capability negotiation"
```

---

### Task 3: Send Registration Confirmation Before Ready

**Files:**
- Modify: `pkg/client/client.go`
- Create: `pkg/client/client_test.go`
- Modify: `pkg/websocket/handler.go`
- Modify: `pkg/websocket/handler_test.go`
- Modify: `main.go`
- Modify: `main_test.go`

**Interfaces:**
- Produces: `RpcClient.SetProtocol(version int, capabilities []string)`
- Produces: `RpcClient.ProtocolVersion() int`, `RpcClient.Capabilities() []string`, `RpcClient.SupportsCapability(string) bool`
- Produces: `Handler.HandleConnectionWithRegistration(context.Context, *websocket.Conn, string, string, protocol.Registration)`
- Preserves: existing `HandleConnection(ctx, conn, group, clientID)` as a legacy delegate.

- [ ] **Step 1: Write failing client metadata tests**

```go
type protocolMetadataConnection struct{}

func (protocolMetadataConnection) Send([]byte) error      { return nil }
func (protocolMetadataConnection) Receive() ([]byte, error) { return nil, io.EOF }
func (protocolMetadataConnection) Close() error           { return nil }
func (protocolMetadataConnection) RemoteAddr() string     { return "test" }

func TestRpcClientProtocolMetadataIsCopied(t *testing.T) {
	c := NewRpcClient("g", "c", protocolMetadataConnection{})
	input := []string{protocol.CapabilityInvocationContextV1}
	c.SetProtocol(1, input)
	input[0] = "mutated"
	got := c.Capabilities()
	got[0] = "mutated-again"
	if !c.SupportsCapability(protocol.CapabilityInvocationContextV1) {
		t.Fatal("capability snapshot was mutable")
	}
	if c.ProtocolVersion() != 1 {
		t.Fatalf("version = %d", c.ProtocolVersion())
	}
}
```

- [ ] **Step 2: Verify the metadata test fails**

Run: `go test ./pkg/client -run ProtocolMetadata -count=1`

Expected: FAIL because the methods do not exist.

- [ ] **Step 3: Store metadata under the existing RpcClient mutex**

Add private `protocolVersion int` and `capabilities map[string]struct{}` fields. `SetProtocol` replaces the map from a copied slice. `Capabilities` returns a sorted new slice. All getters use `RLock`.

- [ ] **Step 4: Write versioned and legacy WebSocket integration tests**

Extend `TestBusinessRegisterRoute_DBlessValidationAndUpgrade`:

```go
versionedURL := baseWSURL + "&protocol_version=1&capabilities=unknown.v1%2Cinvocation_context.v1"
conn, _, err := gorillawebsocket.DefaultDialer.Dial(versionedURL, nil)
if err != nil {
	t.Fatal(err)
}
defer conn.Close()
_, payload, err := conn.ReadMessage()
if err != nil {
	t.Fatal(err)
}
var registered protocol.WSMessage
if err := json.Unmarshal(payload, &registered); err != nil {
	t.Fatal(err)
}
if registered.Type != protocol.MessageTypeRegistered ||
	registered.ProtocolVersion != 1 ||
	!slices.Equal(registered.Capabilities, []string{protocol.CapabilityInvocationContextV1}) {
	t.Fatalf("registered = %#v", registered)
}
```

For a flag-disabled server, set a 100 ms read deadline and assert no `registered` data arrives while the upgrade still returns 101.

- [ ] **Step 5: Implement the version-aware handler**

Keep source compatibility:

```go
func (h *Handler) HandleConnection(ctx context.Context, conn *websocket.Conn, group, clientID string) {
	h.HandleConnectionWithRegistration(ctx, conn, group, clientID, protocol.LegacyRegistration())
}
```

At the start of `HandleConnectionWithRegistration`:

```go
sekiroClient := client.NewRpcClient(group, clientID, wsTransport)
sekiroClient.SetProtocol(registration.ProtocolVersion, registration.Capabilities)

if !registration.Legacy {
	registered := &RpcMessage{
		Type:            MessageTypeRegistered,
		ProtocolVersion: registration.ProtocolVersion,
		Capabilities:    registration.Capabilities,
		Timestamp:       time.Now().UnixMilli(),
	}
	if err := h.sendMessage(sekiroClient, registered); err != nil {
		logger.Warnf("Registration confirmation failed: group=%s, clientId=%s, err=%v", group, clientID, err)
		return
	}
}

sekiroClient.SetStatus(client.StatusOnline)
h.clientManager.Register(sekiroClient)
```

Move Online and manager registration after the successful confirmation. Change `sendMessage` to return marshal/send errors; heartbeat and ordinary error callers explicitly ignore or log the returned error.

Alias the existing server names to Task 1 types so package consumers keep compiling:

```go
type MessageType = protocol.WSMessageType
type RpcMessage = protocol.WSMessage

const (
	MessageTypeRegistered     = protocol.MessageTypeRegistered
	MessageTypeHeartbeat      = protocol.MessageTypeHeartbeat
	MessageTypeInvoke         = protocol.MessageTypeInvoke
	MessageTypeInvokeResponse = protocol.MessageTypeInvokeResponse
	MessageTypeInvokeStream   = protocol.MessageTypeInvokeStream
	MessageTypeBind           = protocol.MessageTypeBind
)
```

- [ ] **Step 6: Wire the active route, add pre-upgrade tests, and verify ordering**

In `handleRegister`, after successful authorization and before `Upgrade`, add:

```go
registration, ok := s.negotiateRegistration(c)
if !ok {
	return
}
```

Then replace only the active call:

```go
go s.wsHandler.HandleConnectionWithRegistration(s.wsCtx, wsConn, group, clientID, registration)
```

Leave `pkg/handler/websocket.go` on the legacy delegate because it is not the active route and has no feature configuration.

Add route-level cases proving invalid version returns 426 and malformed capabilities return 400 without WebSocket upgrade. These are the same query cases exercised against the helper in Task 2.

Using the existing registered-group authorization stubs, also send an unauthorized request with `protocol_version=2` and assert the authorization response wins; the route must not disclose negotiation results before access control.

Run: `go test . ./pkg/client ./pkg/websocket ./pkg/handler -count=1`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add main.go main_test.go pkg/client/client.go pkg/client/client_test.go pkg/websocket/handler.go pkg/websocket/handler_test.go
git commit -m "feat(websocket): confirm negotiated registration"
```

---

### Task 4: Inject InvocationContext at the Shared Send Boundary

**Files:**
- Create: `pkg/invocation/context.go`
- Create: `pkg/invocation/context_test.go`
- Modify: `pkg/websocket/handler.go`
- Modify: `pkg/websocket/handler_test.go`

**Interfaces:**
- Produces: `invocation.New(sequence, traceID, group, action, clientID string, deadline time.Time) invocation.Context`
- Produces: `Context.Wire() protocol.WireInvocationContext`
- Consumes: `RpcClient.SupportsCapability`
- Preserves: `Handler.SendInvokeRequest` public signature and every existing caller.

- [ ] **Step 1: Write the failing value-object test**

```go
func TestContextWire(t *testing.T) {
	deadline := time.UnixMilli(1786636800000)
	ctx := New("seq-1", "trace-1", "g", "echo", "c", deadline)
	got := ctx.Wire()
	if got.Sequence != "seq-1" || got.DeadlineUnixMS != deadline.UnixMilli() ||
		got.Attempt != 1 || got.Idempotent || got.IdempotencyKey != "" {
		t.Fatalf("wire context = %#v", got)
	}
}
```

- [ ] **Step 2: Verify the package is missing**

Run: `go test ./pkg/invocation -count=1`

Expected: FAIL because the package does not exist.

- [ ] **Step 3: Implement the immutable-by-convention value**

```go
type Context struct {
	sequence       string
	traceID        string
	group          string
	action         string
	clientID       string
	deadline       time.Time
	idempotent     bool
	idempotencyKey string
	attempt        int
}

func New(sequence, traceID, group, action, clientID string, deadline time.Time) Context {
	return Context{
		sequence: sequence, traceID: traceID, group: group, action: action,
		clientID: clientID, deadline: deadline, attempt: 1,
	}
}

func (c Context) Wire() protocol.WireInvocationContext {
	return protocol.WireInvocationContext{
		Sequence: c.sequence, TraceID: c.traceID, Group: c.group,
		Action: c.action, ClientID: c.clientID,
		DeadlineUnixMS: c.deadline.UnixMilli(),
		Idempotent: c.idempotent, IdempotencyKey: c.idempotencyKey,
		Attempt: c.attempt,
	}
}
```

Do not add setters or `context.Value` keys.

- [ ] **Step 4: Write failing conditional-injection tests**

Use the existing mock transport and timeout manager:

```go
record := timeoutMgr.Add("seq-1", "g", "c", []byte(`{"action":"echo"}`))
record.Timeout = 3 * time.Second
target.SetProtocol(1, []string{protocol.CapabilityInvocationContextV1})

if err := handler.SendInvokeRequest(target, "seq-1", "g", "c", []byte(`{"action":"echo","value":1}`), "trace-1"); err != nil {
	t.Fatal(err)
}
```

Decode the sent JSON and assert:

- versioned connection: `__rpc_context__` exists and its deadline equals `record.CreatedAt.Add(record.Timeout).UnixMilli()`;
- legacy connection: `__rpc_context__` is absent;
- versioned connection without an invoke/stream timeout record: send fails before writing;
- outer `__sekiro_seq__` and `trace_id` remain unchanged.

- [ ] **Step 5: Implement context construction once in SendInvokeRequest**

Add:

```go
func (h *Handler) invocationDeadline(sequence string) (time.Time, bool) {
	if record := h.timeoutManager.Get(sequence); record != nil {
		return record.CreatedAt.Add(record.Timeout), true
	}
	if record := h.timeoutManager.GetStream(sequence); record != nil {
		return record.CreatedAt.Add(record.Timeout), true
	}
	return time.Time{}, false
}
```

After parsing `reqData`, but before JSON marshal:

```go
if sekiroClient.SupportsCapability(protocol.CapabilityInvocationContextV1) {
	action, ok := reqData["action"].(string)
	if !ok || action == "" {
		return errors.New("invoke action missing for invocation context")
	}
	deadline, ok := h.invocationDeadline(sequence)
	if !ok {
		return errors.New("invoke deadline not registered")
	}
	rpcContext := invocation.New(sequence, traceID, group, action, clientID, deadline)
	fullMsg["__rpc_context__"] = rpcContext.Wire()
}
```

Do not change the five CRITICAL callers; the existing timeout records already cover unary, stream, Chat and Qwen paths.

- [ ] **Step 6: Run focused, race, and caller-sweep checks**

Run: `gofmt -w pkg/invocation pkg/websocket/handler.go pkg/websocket/handler_test.go`

Run: `go test ./pkg/invocation ./pkg/websocket ./pkg/handler -count=1`

Run: `go test -race ./pkg/client/... ./pkg/handler/... ./pkg/websocket/...`

Run: `rg -n "SendInvokeRequest\\(" pkg/handler pkg/websocket`

Expected: all production calls still target the single shared method; tests PASS.

- [ ] **Step 7: Commit**

```bash
git add pkg/invocation pkg/websocket/handler.go pkg/websocket/handler_test.go
git commit -m "feat(invoke): propagate negotiated invocation context"
```

---

### Task 5: Migrate the Go Caller to the Existing HTTP API

**Files:**
- Rewrite: `pkg/client/sdk/invoker.go`
- Rewrite: `pkg/client/sdk/invoker_test.go`

**Interfaces:**
- Preserves: `NewRpcInvoker([]string)`, `NewRpcInvokerWithToken(string, []string)`, `Invoke(*InvokeRequest)`, `Destroy()`
- Adds: `InvokeContext(context.Context, *InvokeRequest) (*InvokeResponse, error)`
- Changes transport: one HTTP POST to `/business/invoke`; no TCP packet and no transparent retry.

- [ ] **Step 1: Replace constructor-only tests with HTTP contract tests**

Use two `httptest.Server` instances. The first records method, path, bearer token and JSON body; the second increments an atomic counter.

```go
resp, err := invoker.InvokeContext(context.Background(), &InvokeRequest{
	Group: "g", Api: "echo", Params: map[string]interface{}{"value": 1},
	Timeout: 2 * time.Second,
})
if err != nil {
	t.Fatal(err)
}
if resp.Code != 0 || resp.Data.(map[string]interface{})["value"] != float64(1) {
	t.Fatalf("response = %#v", resp)
}
```

Add a separate case where server one returns HTTP 500 and assert server two receives zero requests.

- [ ] **Step 2: Verify old TCP behavior fails the HTTP tests**

Run: `go test ./pkg/client/sdk -run 'InvokerHTTP|InvokerDoesNotRetry' -count=1`

Expected: FAIL because the current constructor dials TCP and `Invoke` sends binary packets.

- [ ] **Step 3: Implement endpoint normalization and one-attempt selection**

```go
type RpcInvoker struct {
	apiToken   string
	serverURLs []*url.URL
	httpClient *http.Client
	next       atomic.Uint64
}

func normalizeServer(raw string) (*url.URL, error) {
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return nil, fmt.Errorf("invalid server address %q", raw)
	}
	u.Path = strings.TrimRight(u.Path, "/")
	return u, nil
}
```

Constructors must not open a network connection. They normalize valid endpoints and retain an `http.Transport`; `Destroy` calls `CloseIdleConnections`.

- [ ] **Step 4: Implement InvokeContext with a hard response limit**

The request body is:

```go
payload := map[string]interface{}{
	"group": req.Group,
	"action": req.Api,
	"params": req.Params,
}
if req.Timeout > 0 {
	payload["timeout"] = int(math.Ceil(req.Timeout.Seconds()))
}
```

Select exactly one endpoint, build `POST <base>/business/invoke`, set `Content-Type: application/json` and optional `Authorization: Bearer <token>`, and bind the HTTP request to the smaller of caller context and `req.Timeout`. Read at most `10 MiB + 1 byte`; reject a larger response. Return an error on non-2xx status without selecting another endpoint.

Decode the existing flattened response:

```go
type InvokeResponse struct {
	Code     int                    `json:"code"`
	Message  string                 `json:"message"`
	Data     interface{}            `json:"data"`
	Group    string                 `json:"group"`
	ClientID string                 `json:"clientId"`
	TraceID  string                 `json:"trace_id"`
	Raw      map[string]interface{} `json:"-"`
}
```

When `data` is absent, set `Data` to a copy of `Raw` without `code`, `message`, `group`, `clientId`, and `trace_id`.

- [ ] **Step 5: Run and commit**

Run: `gofmt -w pkg/client/sdk/invoker.go pkg/client/sdk/invoker_test.go`

Run: `go test ./pkg/client/sdk -run Invoker -count=1`

Expected: PASS and the no-retry assertion remains zero for server two.

```bash
git add pkg/client/sdk/invoker.go pkg/client/sdk/invoker_test.go
git commit -m "refactor(sdk): use HTTP for Go invocation"
```

---

### Task 6: Migrate the Go Executor to WebSocket JSON

**Files:**
- Rewrite: `pkg/client/sdk/client.go`
- Rewrite: `pkg/client/sdk/client_test.go`

**Interfaces:**
- Preserves: `NewRpcClient(group, clientID, serverHost string, serverPort int)`, `Start() error`, `Destroy(int64)`, `Register(RegisterHandler)`
- Adds: `NewRpcClientURL(group, clientID, serverURL string) (*RpcClient, error)`
- Adds: `SetToken(string) *RpcClient`
- Adds: `RegisterAction(string, ActionHandler) error`
- Adds: `RegisterActionContext(string, ContextActionHandler) error`
- Requires: `registered` within 5 seconds and negotiated `invocation_context.v1`.

- [ ] **Step 1: Write an in-process WebSocket SDK test**

Create an `httptest.Server` whose handler upgrades WebSocket, validates:

```text
protocol_version=1
capabilities=invocation_context.v1
group=g
clientId=c
```

It sends `registered`, reads one `bind`, sends an invoke containing the fixture context, then reads `invoke_response`. The context handler must assert the sequence, action, group and deadline and return `{"echo": 1}`.

- [ ] **Step 2: Verify the current binary client fails**

Run: `go test ./pkg/client/sdk -run RpcClientWebSocket -count=1`

Expected: FAIL because `Start` dials raw TCP.

- [ ] **Step 3: Define the compatibility and context-aware handlers**

```go
type RegisterHandler func(request []byte) ([]byte, error)
type ActionHandler func(request map[string]interface{}) (interface{}, error)
type ContextActionHandler func(context.Context, protocol.WireInvocationContext, map[string]interface{}) (interface{}, error)

type registeredAction struct {
	plain   ActionHandler
	context ContextActionHandler
}
```

`Register` stores one fallback raw handler. Named registration rejects empty action names and nil handlers. Handler maps are protected by the client mutex.

- [ ] **Step 4: Implement Start as a confirmed one-shot connection**

Build the URL with `net/url`, choose `ws` or `wss` from `NewRpcClientURL`, URL-encode all query values, and add an Authorization header when a token is configured.

The exact order is:

1. return `io.ErrClosedPipe` when destroyed;
2. return nil when the same instance is already started;
3. dial WebSocket;
4. set a 5-second read deadline;
5. read and validate `registered` version 1 and `invocation_context.v1`;
6. clear the read deadline;
7. publish the connection on the struct;
8. send one `bind` containing the sorted named actions;
9. start one read goroutine and one 25-second heartbeat ticker.

If confirmation is missing, wrong, or does not include the requested capability, close the socket and return a typed error. Do not fall back to legacy mode and do not reconnect in stage 1.

- [ ] **Step 5: Implement invoke dispatch and response encoding**

For each `invoke`:

- require non-empty `action` and sequence;
- decode the entire JSON object as the request map;
- require and decode `__rpc_context__`;
- if the wire deadline is positive, derive a Go context with that deadline;
- invoke the context handler, plain handler, or legacy fallback in that order;
- validate legacy fallback bytes as one JSON value and send them as `json.RawMessage` so they are not base64-encoded;
- send exactly one `invoke_response`;
- success uses `status: 0` and `data`;
- failure uses `status: -1` and `error`;
- always echo `__sekiro_seq__`, group, clientId, and trace ID.

Serialize all socket writes through one `writeMu`. Enforce the same 10 MiB read limit. `Destroy` stops the ticker, closes the socket once, clears handlers, and waits up to the supplied seconds for the read goroutine.

- [ ] **Step 6: Remove binary-only client internals and update compatibility tests**

Delete `clientConnection`, compressor handling, packet registration and TCP read loop from `client.go`. Task 5 has already removed the invoker's dependency on those types.

Retain tests proving:

- `Register` compiles and receives raw JSON;
- repeated `Start` does not create a second connection;
- repeated `Destroy` is harmless;
- `Start` after `Destroy` returns `io.ErrClosedPipe`;
- no action bind occurs before `registered`.

- [ ] **Step 7: Run, race-test, and commit**

Run: `gofmt -w pkg/client/sdk/client.go pkg/client/sdk/client_test.go`

Run: `go test ./pkg/client/sdk -count=1`

Run: `go test -race ./pkg/client/sdk`

Expected: PASS.

```bash
git add pkg/client/sdk/client.go pkg/client/sdk/client_test.go
git commit -m "feat(sdk): migrate Go executor to websocket JSON"
```

---

### Task 7: Build the Formal TypeScript/Web SDK

**Files:**
- Create: `sdk/typescript/package.json`
- Create: `sdk/typescript/package-lock.json`
- Create: `sdk/typescript/tsconfig.json`
- Create: `sdk/typescript/build.mjs`
- Create: `sdk/typescript/src/protocol.ts`
- Create: `sdk/typescript/src/client.ts`
- Create: `sdk/typescript/src/browser.ts`
- Create: `sdk/typescript/src/node.ts`
- Create: `sdk/typescript/test/client.test.ts`

**Interfaces:**
- Produces: `RpcClient`, `RpcClientOptions`, `InvocationContext`, `RpcHandler`, `ContextRpcHandler`
- Produces: browser native-WebSocket entry and Node `ws` entry from the same protocol core.
- Produces: ESM files, declarations, `dist/browser/go-rpc.js`, and an npm `.tgz`.

- [ ] **Step 1: Add package metadata and deterministic scripts**

`package.json` must use:

```json
{
  "name": "@mrh30000/go-rpc-sdk",
  "version": "0.1.0-experimental.1",
  "type": "module",
  "files": ["dist", "README.md"],
  "exports": {
    ".": {"types": "./dist/src/browser.d.ts", "import": "./dist/src/browser.js"},
    "./node": {"types": "./dist/src/node.d.ts", "import": "./dist/src/node.js"}
  },
  "scripts": {
    "build": "tsc -p tsconfig.json && node build.mjs",
    "test": "npm run build && node --test dist/test/*.test.js",
    "pack": "npm pack --pack-destination dist"
  },
  "dependencies": {"ws": "^8.18.0"},
  "devDependencies": {
    "@types/node": "^22.10.0",
    "@types/ws": "^8.5.13",
    "esbuild": "^0.24.0",
    "typescript": "^5.6.3"
  }
}
```

`tsconfig.json` must compile both source and tests without a second configuration:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "rootDir": ".",
    "outDir": "dist",
    "declaration": true,
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "lib": ["ES2020", "DOM"]
  },
  "include": ["src", "test"]
}
```

Generate and commit `package-lock.json` with `npm --prefix sdk/typescript install`.

- [ ] **Step 2: Write fake-WebSocket tests before the client**

The fake must expose `open`, `message`, `close`, `send`, and `readyState`. Test this sequence:

1. `start()` opens a URL with version and capability queries;
2. no bind is sent on `open`;
3. a `registered` message resolves `start()`;
4. sorted actions are bound;
5. an invoke reaches the context handler;
6. one response echoes sequence and trace;
7. `destroy()` closes the socket;
8. missing confirmation rejects after an injectable short timeout.

- [ ] **Step 3: Define the public types**

```ts
export interface InvocationContext {
  sequence: string;
  trace_id: string;
  group: string;
  action: string;
  client_id: string;
  deadline_unix_ms: number;
  idempotent: boolean;
  idempotency_key: string;
  attempt: number;
}

export type RpcHandler = (request: Record<string, unknown>) => unknown | Promise<unknown>;
export type ContextRpcHandler = (
  context: InvocationContext,
  request: Record<string, unknown>,
  signal: AbortSignal,
) => unknown | Promise<unknown>;
```

Define a small `WebSocketLike` and `WebSocketFactory` interface in `protocol.ts`; the core must not import DOM globals or `ws`:

```ts
export interface WebSocketAuth {
  headers?: Record<string, string>;
  protocols?: string[];
}

export type WebSocketFactory =
  (url: string, auth: WebSocketAuth) => WebSocketLike;
```

When `RpcClientOptions.token` is present, the core supplies both `Authorization: Bearer <token>` and the single protocol `sekiro-auth.<token>` to the adapter. It never appends the token to the URL.

- [ ] **Step 4: Implement one core and two transport entries**

`RpcClient.start()` uses the same confirmed order as Task 6. Store handlers before start, require `registered`, bind after confirmation, treat heartbeat/error as control messages, and send one response per invoke.

Before JSON parse, reject a text message whose UTF-8 byte length exceeds 10 MiB and close with WebSocket code 1009.

`browser.ts` supplies:

```ts
export const browserWebSocketFactory: WebSocketFactory =
  (url, auth) => new WebSocket(url, auth.protocols);
```

`node.ts` supplies:

```ts
import WebSocket from "ws";
export const nodeWebSocketFactory: WebSocketFactory =
  (url, auth) => new WebSocket(
    url,
    auth.protocols ?? [],
    {headers: auth.headers},
  );
```

The stage-1 `destroy()` aborts active handlers and closes the socket, but the client does not schedule reconnects.

- [ ] **Step 5: Build the browser bundle without protocol forks**

`build.mjs` calls esbuild once:

```js
await build({
  entryPoints: ["src/browser.ts"],
  bundle: true,
  format: "iife",
  globalName: "GoRpc",
  outfile: "dist/browser/go-rpc.js",
  platform: "browser",
  target: ["es2020"],
  sourcemap: true,
});
```

- [ ] **Step 6: Verify tests, package contents, and forbidden API absence**

Run: `npm --prefix sdk/typescript test`

Run: `npm --prefix sdk/typescript run pack`

Run: `rg -n "_execjs|eval\\(|new Function" sdk/typescript`

Expected: tests PASS, `.tgz` exists under `sdk/typescript/dist`, and the forbidden search returns no matches.

- [ ] **Step 7: Commit**

```bash
git add sdk/typescript
git commit -m "feat(sdk): add TypeScript websocket client"
```

---

### Task 8: Build the Formal Python SDK

**Files:**
- Create: `sdk/python/pyproject.toml`
- Create: `sdk/python/src/go_rpc/__init__.py`
- Create: `sdk/python/src/go_rpc/protocol.py`
- Create: `sdk/python/src/go_rpc/executor.py`
- Create: `sdk/python/src/go_rpc/caller.py`
- Create: `sdk/python/tests/test_executor.py`
- Create: `sdk/python/tests/test_caller.py`

**Interfaces:**
- Produces: `ExecutorClient`, `RpcHTTPClient`, `AsyncRpcHTTPClient`, `InvocationContext`
- Produces: `register(action, handler)` and `register_context(action, handler)`
- Produces: wheel and sdist.

- [ ] **Step 1: Create packaging metadata**

Use a `src/` layout and:

```toml
[project]
name = "go-rpc-sdk"
version = "0.1.0.dev1"
requires-python = ">=3.10"
dependencies = [
  "tornado>=6.2,<7",
  "httpx>=0.24,<1"
]

[project.optional-dependencies]
dev = ["build>=1,<2"]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"
```

Do not include `tenacity`; stage 1 callers send once.

- [ ] **Step 2: Write async executor tests with a local Tornado WebSocket server**

The test server records the registration query, sends the fixture confirmation, verifies bind ordering, sends one invoke, and asserts one response. Add missing-confirmation and legacy-confirmation rejection cases.

The context handler assertion is:

```python
async def echo(context: InvocationContext, request: dict, cancel_event: asyncio.Event):
    assert context.sequence == "seq-1"
    assert context.action == "echo"
    assert not cancel_event.is_set()
    return {"echo": request["value"]}
```

- [ ] **Step 3: Define protocol dataclasses and validation**

```python
@dataclass(frozen=True)
class InvocationContext:
    sequence: str
    trace_id: str
    group: str
    action: str
    client_id: str
    deadline_unix_ms: int
    idempotent: bool
    idempotency_key: str
    attempt: int
```

`from_message` must require every fixture field and reject booleans or strings where integers are required.

- [ ] **Step 4: Implement the confirmed Tornado executor**

`ExecutorClient.start()`:

- constructs the URL with `urllib.parse.urlencode`;
- requests only `invocation_context.v1`;
- passes an Authorization header when configured;
- awaits `tornado.websocket.websocket_connect`;
- awaits one message under a 5-second `asyncio.wait_for`;
- validates `registered`;
- sends sorted action bind;
- starts one reader task and one `PeriodicCallback` heartbeat.

The reader rejects text or binary payloads over 10 MiB before JSON decode and closes the socket.

`destroy()` is idempotent, stops the heartbeat, cancels active handler tasks, closes the socket, and awaits the reader. It does not reconnect in stage 1.

- [ ] **Step 5: Implement sync and async HTTP callers with no retry**

Both callers POST the same body as Task 5, set bearer auth, enforce their configured timeout and parse flattened success responses. A transport exception, timeout, non-2xx response, or invalid JSON is returned as a typed `RpcTransportError`; a negative business code is `RpcAPIError`. Neither caller performs a second send.

- [ ] **Step 6: Run unit tests and build artifacts**

Run: `python -m pip install -e "sdk/python[dev]"`

Run: `python -m unittest discover -s sdk/python/tests -v`

Run: `python -m build sdk/python`

Expected: tests PASS; one wheel and one sdist exist in `sdk/python/dist`.

- [ ] **Step 7: Commit**

```bash
git add sdk/python
git commit -m "feat(sdk): add Python websocket and HTTP clients"
```

---

### Task 9: Extract the Java 8 Core and Make Xposed Consume It

**Files:**
- Create: `sdk/java/settings.gradle`
- Create: `sdk/java/build.gradle`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/RpcClient.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/Action.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/ActionHandler.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/AutoBind.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/ContextActionHandler.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/HandlerRegistry.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/InvocationContext.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RequestHandler.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcCancellationToken.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcRequest.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcRequestInitializer.java`
- Create: `sdk/java/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcResponse.java`
- Create: `sdk/java/src/test/java/cn/iinti/sekiro3/business/api/RpcClientTest.java`
- Modify: `sample/xposed/settings.gradle`
- Modify: `sample/xposed/app/build.gradle`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/RpcClient.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/Action.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/ActionHandler.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/AutoBind.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/HandlerRegistry.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RequestHandler.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcRequest.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcRequestInitializer.java`
- Delete: `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/interfaze/RpcResponse.java`

**Interfaces:**
- Produces: Java 8 `go-rpc-sdk` JAR with no Android/Xposed imports.
- Preserves: existing `RpcClient`, `setupRpcRequestInitializer`, `HandlerRegistry`, `ActionHandler`, `RpcRequest`, and `RpcResponse` APIs.
- Adds: `awaitReady(long, TimeUnit)`, `ContextActionHandler`, immutable `InvocationContext`, and a stage-1 local `RpcCancellationToken` without changing demo imports.
- Consumes: OkHttp and the existing JSON library; Xposed app consumes the same Gradle module through composite build.

- [ ] **Step 1: Create the standalone Java library build**

```groovy
plugins {
    id 'java-library'
}

group = 'io.github.mrh30000'
version = '0.1.0-experimental.1'

java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

dependencies {
    api 'com.squareup.okhttp3:okhttp:3.12.13'
    implementation 'com.alibaba:fastjson:1.2.83'
    testImplementation 'junit:junit:4.13.2'
}
```

`settings.gradle` sets `rootProject.name = 'go-rpc-sdk'`.

- [ ] **Step 2: Write MockWebServer registration tests**

Add `testImplementation 'com.squareup.okhttp3:mockwebserver:3.12.13'`. The test must inspect the query, perform a WebSocket upgrade, send `registered`, assert bind follows, send a context invoke, and verify one response.

Add a second test where the socket opens without confirmation and assert the client never reports ready or sends bind.

- [ ] **Step 3: Define Java 8 handler interfaces**

```java
public interface ContextActionHandler extends ActionHandler {
    void handleRequest(
        InvocationContext context,
        RpcCancellationToken cancellationToken,
        RpcRequest request,
        RpcResponse response
    );

    @Override
    default void handleRequest(RpcRequest request, RpcResponse response) {
        handleRequest(
            request.getInvocationContext(),
            request.getCancellationToken(),
            request,
            response
        );
    }
}
```

`InvocationContext` is a final class with final fields, constructor validation, and getters matching the nine wire fields. `RpcCancellationToken` wraps an `AtomicBoolean`; only package code can trigger it, while handlers can call `isCancelled()`. `RpcRequest` gains final context/token fields plus getters; the existing constructor delegates with values parsed and created by `RpcClient`. In stage 1 the token is triggered only by local deadline, disconnect, or destroy—no `cancel.v1` frame is advertised. Existing `ActionHandler` and `RequestHandler` signatures remain unchanged. Do not import Android packages.

- [ ] **Step 4: Extract and tighten RpcClient**

Start from the existing Xposed WebSocket implementation, then make these stage-1 changes:

- URL adds protocol version and `invocation_context.v1`;
- optional token is sent as `Authorization: Bearer <token>` and never as a query value;
- `onOpen` does not set ready, start heartbeat, or bind;
- only a valid `registered` message sets ready and reports sorted actions;
- confirmation counts down the latch used by `awaitReady`; timeout or close returns `false`;
- invoke requires `__rpc_context__`; `ContextActionHandler` receives it through the Java 8 default-method adapter while existing handlers keep their two-argument call;
- writes remain serialized by OkHttp WebSocket;
- incoming UTF-8 payloads over 10 MiB close the socket before JSON parsing;
- `destroy` closes socket and executors once;
- automatic reconnect scheduling is removed from the formal core until stage 3;
- `ws` and `wss` are constructor options; TLS verification remains OkHttp default.

- [ ] **Step 5: Make Xposed consume the formal module**

In `sample/xposed/settings.gradle`:

```groovy
include ':app'
includeBuild('../../sdk/java')
```

In the app:

```groovy
implementation 'io.github.mrh30000:go-rpc-sdk:0.1.0-experimental.1'
```

The formal module retains the current `cn.iinti.sekiro3.business.api` and `.interfaze` packages, so `XposedMain`, `MainActivity`, and `ClientTimeHandler` keep their imports and handler code. After `:app:compileDebugJavaWithJavac` succeeds against the composite dependency, delete exactly the nine duplicate files listed in this task. Keep the explicitly excluded Netty legacy tree and its other reference-only interfaces untouched.

- [ ] **Step 6: Run JVM and Android builds**

Run: `.\sample\xposed\gradlew.bat -p sdk/java clean test jar`

Run: `.\sample\xposed\gradlew.bat -p sample/xposed :app:testDebugUnitTest :app:assembleDebug`

Expected: JVM tests PASS, Java 8 JAR exists, Xposed APK builds against the formal module.

- [ ] **Step 7: Commit**

```bash
git add sdk/java sample/xposed
git commit -m "feat(sdk): extract Java websocket core"
```

---

### Task 10: Add Stage-1 Cross-SDK Black-Box Conformance

**Files:**
- Create: `conformance/adapters/go/main.go`
- Create: `conformance/adapters/typescript.mjs`
- Create: `conformance/adapters/python.py`
- Create: `conformance/runner/main.go`
- Create: `conformance/README.md`

**Interfaces:**
- Runner input: repository root and commands on PATH.
- Adapter input: `RPC_TEST_BASE_URL`.
- Adapter result: exit 0 only after confirmed registration, bind, HTTP invoke, context assertion, response assertion, and destroy.

- [ ] **Step 1: Write a runner test for command failure propagation**

Factor:

```go
func runAdapter(ctx context.Context, root, name string, command ...string) error
```

Test a process that exits 7 and assert the returned error includes adapter name, exit code, stdout, and stderr.

- [ ] **Step 2: Implement server lifecycle in the Go runner**

The runner:

1. reserves a random loopback port;
2. starts `go run .` in the repository root;
3. sets `RPC_HOST=127.0.0.1`, chosen `RPC_PORT`, all four disable flags, and `RPC_CAPABILITY_NEGOTIATION=true`;
4. waits up to 20 seconds for `/health`;
5. runs adapters sequentially with a 60-second timeout each;
6. always terminates and waits for the server process;
7. prints the server log on failure.

Do not import package `main` or any server-internal protocol package into non-Go adapters.

- [ ] **Step 3: Implement each adapter as a real-wire echo**

Each adapter must:

- load `conformance/fixtures/invoke-context-v1.json`;
- create its formal execution client;
- register `conformance.echo` with a context handler;
- start and wait for registration confirmation;
- issue `POST /business/invoke` through its public HTTP caller or standard HTTP library;
- validate returned `echo`, group, client ID, trace ID presence and context fields;
- destroy the client;
- exit nonzero on any mismatch.

Java uses its existing `RpcClientTest` as the adapter target with `-Drpc.test.baseUrl`; it does not need a fifth adapter file.

- [ ] **Step 4: Add legacy compatibility coverage**

The Go runner opens a raw WebSocket without `protocol_version`, sets a 100 ms read deadline to prove no `registered` message arrives, sends a legacy bind and then completes a normal invoke without `__rpc_context__`.

- [ ] **Step 5: Run all adapters**

Run: `go run ./conformance/runner`

Expected output includes PASS for Go, TypeScript/Web, Python, Java and legacy; Frida is not enumerated.

- [ ] **Step 6: Commit**

```bash
git add conformance
git commit -m "test(conformance): cover stage-one SDK matrix"
```

---

### Task 11: Build Reproducible Local Artifacts and Document Migration

**Files:**
- Create: `scripts/build-sdk-artifacts.ps1`
- Modify: `scripts/verify.ps1`
- Modify: `README.md`
- Modify: `sample/frida/README.md`
- Modify: `sample/python/README.md`
- Modify: `sample/xposed/README.md`
- Create: `sdk/typescript/README.md`
- Create: `sdk/python/README.md`
- Create: `sdk/java/README.md`

**Interfaces:**
- Produces local artifacts only; no registry upload or GitHub release.
- Produces SHA-256 manifest under `artifacts/sdk/SHA256SUMS`.

- [ ] **Step 1: Write the artifact script with a clean scoped output**

The script accepts `-OutputDirectory` defaulting to `artifacts/sdk`. It resolves that directory under the repository root, creates it, runs:

```powershell
$env:SOURCE_DATE_EPOCH = "1786636800"
npm --prefix sdk/typescript ci
npm --prefix sdk/typescript test
npm --prefix sdk/typescript run pack
python -m pip install -e "sdk/python[dev]"
python -m unittest discover -s sdk/python/tests -v
python -m build sdk/python
& .\sample\xposed\gradlew.bat -p sdk/java clean test jar
& .\sample\xposed\gradlew.bat -p sample/xposed :app:assembleDebug
```

Copy only the `.tgz`, `.whl`, `.tar.gz`, `.jar`, and debug `.apk` outputs. Generate one deterministic, path-sorted `SHA256SUMS` using `Get-FileHash -Algorithm SHA256`; manifest entries contain artifact leaf names rather than the caller-selected output directory.

- [ ] **Step 2: Extend the repository verification gate**

After existing Go/frontend checks, add:

```powershell
Invoke-Check "TypeScript SDK install" { npm --prefix sdk/typescript ci }
Invoke-Check "TypeScript SDK test" { npm --prefix sdk/typescript test }
Invoke-Check "Python SDK" { python -m unittest discover -s sdk/python/tests -v }
Invoke-Check "Java SDK" { & .\sample\xposed\gradlew.bat -p sdk/java test jar }
Invoke-Check "Stage 1 conformance" { go run ./conformance/runner }
```

Keep `ImpactAnalysisEvidence` mandatory.

- [ ] **Step 3: Document the formal matrix and migration**

README content must state:

- enable `RPC_CAPABILITY_NEGOTIATION=true` only after deploying the new server;
- new SDKs require `registered` and do not downgrade;
- Go executor is WebSocket JSON and Go caller is HTTP;
- installation from local `.tgz`, wheel/sdist and JAR;
- public npm/PyPI/Maven publishing is not enabled;
- Frida and raw TCP samples are experimental/legacy;
- Frida does not carry new capabilities or block stable release;
- `_execjs` is not part of the formal TS/Web SDK.

- [ ] **Step 4: Build twice and compare manifests**

Run:

```powershell
powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-first
powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-second
Compare-Object (Get-Content artifacts/sdk-first/SHA256SUMS) (Get-Content artifacts/sdk-second/SHA256SUMS)
```

Expected: no differences. If APK embeds a build timestamp, remove the timestamp-based output filename in `sample/xposed/app/build.gradle` before accepting this check.

- [ ] **Step 5: Run the full verification gate and commit**

Save the Task 12 impact output to `artifacts/stage1-impact-evidence.txt`, then run:

```powershell
$impactEvidence = Get-Content artifacts/stage1-impact-evidence.txt -Raw
powershell -File scripts/verify.ps1 -ImpactAnalysisEvidence $impactEvidence
```

Expected: PASS.

```bash
git add scripts README.md sample/frida/README.md sample/python/README.md sample/xposed/README.md sdk/typescript/README.md sdk/python/README.md sdk/java/README.md
git commit -m "docs(sdk): add stage-one build and migration guide"
```

---

### Task 12: Final Stage-1 Exit Gate

**Files:**
- Modify only files required by failures found in this gate.

**Interfaces:**
- Produces: review evidence for the phase exit; no remote push, release, or registry publication.

- [ ] **Step 1: Run GitNexus change detection**

Run impact analysis for:

- `main.handleRegister`
- `pkg/websocket.Handler.HandleConnectionWithRegistration`
- `pkg/websocket.Handler.SendInvokeRequest`
- `pkg/client.RpcClient`
- `pkg/client/sdk.RpcClient`
- `pkg/client/sdk.RpcInvoker`

Record all HIGH/CRITICAL callers and confirm every production caller is represented by focused or conformance tests.

- [ ] **Step 2: Run protocol and compatibility checks**

Run:

```powershell
go test ./...
go test -race ./pkg/client/... ./pkg/handler/... ./pkg/websocket/...
go run ./conformance/runner
rg -n "_execjs|eval\(|new Function" sdk/typescript
rg -n "sdk/frida|Frida.*正式|Frida.*stable" sdk conformance scripts README.md
```

Expected:

- all tests PASS;
- forbidden TS search has no matches;
- formal SDK/conformance paths contain no Frida target;
- legacy registration and ordinary invocation pass.

- [ ] **Step 3: Validate artifact inventory**

Run: `powershell -File scripts/build-sdk-artifacts.ps1`

Expected inventory:

```text
TypeScript npm .tgz
Python wheel
Python sdist
Java 8 JAR
Xposed debug APK
SHA256SUMS
```

- [ ] **Step 4: Review the complete diff**

Run: `git diff --check 8dad2f1..HEAD`

Run: `git diff --check -- pkg internal main.go main_test.go sdk conformance scripts README.md sample/frida/README.md sample/python/README.md sample/xposed`

Run: `git status --short`

Run: `git diff --stat 8dad2f1..HEAD`

Review specifically:

- no credentials, generated dependency directories, private registry actions or unrelated refactors;
- capability flag still defaults off;
- new SDK never becomes ready before confirmation;
- legacy clients never receive `registered` or `__rpc_context__`;
- `cancel.v1`, retry, dedupe and reconnect semantics were not pulled into stage 1;
- Frida remains experimental/legacy.

- [ ] **Step 5: Create the final verification commit only if the gate required fixes**

```bash
git add -- pkg/protocol pkg/invocation pkg/client pkg/websocket internal/config/config.go internal/config/server_config_test.go .env.example main.go main_test.go sdk conformance scripts README.md sample/frida/README.md sample/python/README.md sample/xposed
git commit -m "fix(stage1): satisfy protocol baseline exit gate"
```

If no files changed, do not create an empty commit.

## Stage-1 Acceptance Mapping

| Approved requirement | Implemented by |
|---|---|
| Version and capability query validation | Tasks 1–2 |
| Auth before upgrade and confirmation | Tasks 2–3 |
| Legacy receives no new messages | Tasks 2–3, 10 |
| `InvocationContext` only after negotiation | Task 4 |
| All CRITICAL send paths covered once | Task 4 |
| Go executor uses WebSocket JSON | Task 6 |
| Go caller uses HTTP | Task 5 |
| Formal TS/Web without `_execjs` | Task 7 |
| Formal Python executor and caller | Task 8 |
| Java 8 core shared by Xposed | Task 9 |
| Frida excluded from formal matrix | Global constraints, Tasks 10–12 |
| Shared black-box fixtures and real protocol | Tasks 1, 10 |
| Reproducible local artifacts and hashes | Task 11 |
| No remote publishing | Tasks 11–12 |

Stage 1 is complete only when every row above has executable evidence and the master spec's stage-1 exit conditions all pass.
