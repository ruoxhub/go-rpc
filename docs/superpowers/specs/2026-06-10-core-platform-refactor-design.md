# Core / Platform Refactor Design

## Goal

Split the project into two runtime shapes without breaking the current platform entrypoint:

- `go run ./main.go` remains the full platform server.
- `go run ./cmd/rpc-core` starts a lightweight RPC core with no database, web admin, metrics, alerting, or AI gateway dependencies.

The refactor should preserve the existing client protocol while making the minimal RPC path easy to understand, test, and deploy.

## Background

The repository currently combines several responsibilities in the main server path:

- RPC client registration and invocation forwarding
- WebSocket message handling
- request timeout tracking
- routing strategies
- user and token authorization
- PostgreSQL-backed group, user, device, metric, trace, and alert models
- React web admin
- metrics, trace, and alert services
- OpenAI/Qwen-compatible HTTP adapters
- prompt and tool-call parsing utilities

This makes the project feel much larger than JsRpc, whose core behavior is only HTTP-to-WebSocket RPC dispatch. The desired direction is a dual-version route: keep the platform, but extract a clean core that can run independently.

## Chosen Approach

Use a "core package + platform wrapper" architecture.

`pkg/core` owns the minimal RPC runtime. Platform code imports and extends core. Core must not import platform packages.

Alternative approaches were rejected:

- Runtime-only feature flags keep one tangled code path and do not reduce cognitive complexity.
- A separate rewritten minimal project creates two implementations that will drift.

## Entry Points

```text
main.go
  Full platform entrypoint. Existing user behavior remains: go run ./main.go

cmd/rpc-core/main.go
  New lightweight entrypoint. Starts only the core RPC server.
```

`main.go` should become a thin platform bootstrap over time. It may still call existing server code during migration, but the target shape is:

```go
func main() {
    cfg := platform.LoadConfig(...)
    srv := platform.NewServer(cfg)
    srv.Start()
}
```

## Target Package Layout

```text
pkg/
  core/
    server/          # Core startup orchestration
    registry/        # Group/client registration and lookup
    forwarder/       # Invoke records, timeout, response completion
    router/          # Specified client and round-robin routing
    websocket/       # WebSocket protocol handling
    httpapi/         # Core HTTP API handlers and JsRpc aliases
    types/           # Core request/response DTOs
  platform/
    admin/           # Management API wrapper around current handlers
    auth/            # User, token, and group authorization
    observability/   # Metrics, trace, alert integration
    aigateway/       # OpenAI/Qwen-compatible adapters
```

The first implementation phase does not need to move every existing package into this final layout. It should first create a working core boundary and only move the code needed for the minimal runtime.

## Core Responsibilities

Core must support:

- WebSocket client registration by `group` and `clientId`
- HTTP invocation by `group`, optional `clientId`, `action`, `params`, and timeout
- group listing
- client queue listing
- request timeout handling
- response completion by sequence ID
- client health state and failure count
- specified-client routing
- round-robin routing
- JsRpc-compatible aliases when enabled

Core must run fully in memory and must not require PostgreSQL.

## Core HTTP Surface

Core should expose:

```text
GET  /health
GET  /business/groupList
GET  /business/clientQueue
ANY  /business/invoke
GET  /business/register
ANY  /business/execjs
GET  /business/cookie
GET  /business/html
```

When alias routing is enabled, core should also expose:

```text
/ws       -> /business/register
/go       -> /business/invoke
/execjs   -> /business/execjs
/list     -> /business/groupList
/page/cookie
/page/html
```

The aliases are compatibility endpoints, not the primary internal API.

## Core Components

### Server

`core.Server` starts the lightweight runtime and registers core routes.

```go
type Config struct {
    Host         string
    Port         int
    Timeout      time.Duration
    EnableCORS   bool
    RouteAliases bool
}
```

### Registry

The registry owns group and client state:

```text
Register(group, clientID, conn)
Unregister(group, clientID)
Get(group, clientID)
ListGroups()
ListClients(group)
```

It should be independent of database persistence. Platform may observe registry events through hooks.

### Router

The first phase requires:

- specified client routing when `clientId` is provided
- round-robin routing when no `clientId` is provided

Consistent hash routing can remain in the platform path initially or be moved after the minimal core is stable.

### Forwarder

The forwarder tracks in-flight invocations:

```text
Add(sequence, group, clientID, payload, timeout)
Complete(sequence, response)
Wait(sequence)
Remove(sequence)
```

Existing timeout manager behavior is a strong candidate for reuse.

### WebSocket Handler

The WebSocket handler owns protocol-level work only:

- accept client connection
- read heartbeat, invoke response, and optional stream chunk messages
- send invoke request
- complete forwarder records
- remove clients on disconnect

It must not create device records, check registered groups in the database, or mutate platform models. Those effects belong in platform hooks.

### HTTP Handler

The HTTP handler parses core requests, selects a target client, dispatches WebSocket messages, waits for the response, and renders a business response.

It should not contain token lookup, database-backed group ownership checks, metrics writes, trace writes, or alert logic.

## Platform Integration

Platform uses core and attaches optional behavior through hooks.

```go
type HookSet struct {
    OnClientConnected    func(ClientInfo)
    OnClientDisconnected func(ClientInfo)
    OnInvokeStarted      func(InvokeInfo)
    OnInvokeFinished     func(InvokeResult)
    AuthorizeRegister    func(ctx context.Context, group string) error
    AuthorizeInvoke      func(ctx context.Context, group string) error
}
```

Default core hooks are no-ops or allow-all.

Platform hook implementations provide:

- group ownership and token authorization
- group device persistence
- default action creation for registered groups
- metrics updates
- trace records
- health degradation events
- alert inputs

This keeps the dependency direction one-way: platform depends on core; core does not depend on platform.

## Dependencies Forbidden In Core

`pkg/core` must not import:

```text
github.com/mrh30000/go-rpc/pkg/database
github.com/mrh30000/go-rpc/pkg/model
github.com/mrh30000/go-rpc/pkg/server/handlers
github.com/mrh30000/go-rpc/pkg/server/metrics
github.com/mrh30000/go-rpc/pkg/server/alert
github.com/mrh30000/go-rpc/web
github.com/mrh30000/go-rpc/internal/prompt
github.com/mrh30000/go-rpc/internal/promptcompat
github.com/mrh30000/go-rpc/internal/toolcall
```

A dependency-boundary test should enforce this.

## Migration Plan

### Phase 1: Minimal Core Runtime

Create `pkg/core` and `cmd/rpc-core`. Move or wrap only the code needed for:

```text
HTTP invoke -> route client -> WS send -> timeout wait -> HTTP response
WS register -> registry add -> read response -> complete request
```

The phase is complete when `go run ./cmd/rpc-core` starts without PostgreSQL and can complete a browser/client RPC invocation.

### Phase 2: Platform Reuses Core

Keep `go run ./main.go` as the full platform entrypoint. Change platform startup to construct and extend the core runtime instead of owning RPC internals directly.

Platform registers:

- auth hooks
- metrics hooks
- trace hooks
- alert hooks
- admin routes
- React web routes
- OpenAI/Qwen routes

### Phase 3: Isolate Non-RPC Modules

Move or clearly namespace non-core RPC features under platform-oriented packages:

```text
internal/prompt*
internal/toolcall
pkg/model/openai.go
pkg/server/api/chat_completions.go
pkg/server/api/qwen.go
```

These modules belong to the AI gateway surface, not the core RPC runtime.

### Phase 4: Documentation And Compatibility

Add focused docs:

```text
README-core.md
README-platform.md
```

The docs should state:

- core is in-memory and database-free
- platform is the full managed server
- both share the client protocol
- `main.go` remains the platform entrypoint
- `cmd/rpc-core` is the minimal runtime

## Testing Strategy

### Core Tests

Add tests for:

- client registration and unregister cleanup
- duplicate client behavior
- group listing
- client queue listing
- specified-client routing
- round-robin routing
- invoke timeout cleanup
- WebSocket response completion by sequence
- GET and POST `/business/invoke`
- JsRpc aliases `/ws`, `/go`, `/execjs`, `/list`

### Platform Regression Tests

Add or preserve tests for:

- `go run ./main.go` platform bootstrap behavior
- `DisableDatabase=true`
- `DisableWebAdmin=true`
- auth hook behavior
- metrics hook behavior
- trace hook behavior

### Dependency Boundary Test

Add a test or script that fails if `pkg/core` imports forbidden platform packages.

### Verification Commands

First-phase required checks:

```bash
go test ./pkg/core/...
go test ./pkg/server/...
go test ./pkg/client/...
go run ./cmd/rpc-core
go run ./main.go
```

Full regression target:

```bash
go test ./...
```

If full regression fails due to existing unrelated issues, record the failures and distinguish them from refactor-introduced regressions.

## Risks And Mitigations

### Protocol Compatibility

Risk: moving WebSocket handling can break existing clients.

Mitigation: add end-to-end WebSocket tests before changing platform startup.

### Authorization Regression

Risk: group ownership checks may be skipped when moving logic out of handlers.

Mitigation: platform authorization must be represented as explicit core hooks and covered by tests.

### Observability Gaps

Risk: metrics and trace writes may be lost when invoke logic moves.

Mitigation: use `OnInvokeStarted` and `OnInvokeFinished` hooks as the only platform observability insertion points.

### Overlarge First Phase

Risk: moving all packages at once creates a hard-to-review diff.

Mitigation: phase 1 only extracts the minimal invocation loop and does not move admin, database, alert, metrics, or AI gateway code.

## Success Criteria

- `go run ./main.go` remains the full platform entrypoint.
- `go run ./cmd/rpc-core` starts a database-free lightweight RPC server.
- Core can register a WebSocket client and complete an HTTP invocation.
- Core package imports no platform-only dependencies.
- Platform behavior remains compatible after it starts reusing core.
- JsRpc-style compatibility endpoints work in core mode when aliases are enabled.
