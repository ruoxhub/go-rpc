# AGENTS.md — Rpc-Go

## Quick Start

```bash
# Build everything
go build ./...

# Build specific binaries
go build -o rpc-server ./main.go


# Run tests (all packages)
go test ./...

# Run single package tests
go test ./pkg/protocol/...
go test ./pkg/compress/...
go test ./pkg/server/client/...

# Run a single test
go test -run TestRpcPacket ./pkg/protocol/...
go test -run TestGzipCompress ./pkg/compress/...

# Start server (requires PostgreSQL)
go run cmd/server/main.go -c config.yaml

# Frontend dev
cd web && npm install && npm run dev   # port 3000, proxies /business|/api|/rpc-api → localhost:5613

# Frontend production build (embedded into Go binary via //go:embed)
cd web && npm run build                # outputs to web/dist/
```

## Architecture

**Module path**: `github.com/mrh30000/go-rpc`

**Three binaries** share `pkg/` but have separate entrypoints:
- `cmd/server/main.go` — HTTP + WebSocket server (Gin + gorilla/websocket)
- `cmd/client/main.go` — SDK client that connects via WebSocket
- `cmd/invoker/main.go` — SDK invoker that sends RPC calls

**Request flow**: Invoker → HTTP POST `/business/invoke` → `APIHandler.HandleInvoke` → `forwarder.TimeoutManager` tracks request → `router.Router` picks client (round-robin / specified / consistent-hash) → `websocket.Handler` sends to client → client response arrives back on channel → APIHandler returns to invoker.

**Bootstrap sequence** (`pkg/server/bootstrap.go`): YAML config → logger init → PostgreSQL connect + AutoMigrate → config service → WebSocket handler → metrics collector → alert evaluator → Gin engine → route registration → `net.Listen` → serve.

**Frontend embedding**: `web/embed.go` uses `//go:embed dist` to bundle the React SPA into the binary. No separate static file server needed. `npm run build` in `web/` must produce `web/dist/` before `go build`.

## Package Boundaries

```
cmd/           → Entrypoints only, no business logic
internal/      → Private packages (config, utils/logger) — not importable by external code
pkg/client/    → RpcClient + RpcInvoker SDK (used by cmd/client, cmd/invoker)
pkg/protocol/  → Binary packet codec — shared between server and client
pkg/compress/  → Gzip/Snappy/None compression — used by protocol layer
pkg/database/  → Global *gorm.DB singleton + AutoMigrate
pkg/model/     → GORM models (UserInfo, GroupConfig, AlertRule, TraceRecord, etc.)
pkg/eventbus/  → Simple pub/sub event bus
pkg/server/    → Server core, split into sub-packages:
  ├── api/          → Gin HTTP handlers + WebSocket upgrade
  ├── client/       → ClientManager + RpcGroup (actor-model via goroutine channels)
  ├── config/       → Runtime config service (reads from DB sys_config table)
  ├── detector/     → Protocol detection (Rpc binary vs HTTP) on raw connections
  ├── flow/          → Rate limiter + backoff for empty queues
  ├── forwarder/    → TimeoutManager: tracks in-flight RPC calls with channels
  ├── handlers/     → Web management API handlers (user, group, metric, trace, alert, sysconfig)
  ├── metrics/      → MetricCollector: aggregates invoke counts/latency into minute/hour/day tables
  ├── middleware/    → Gin middleware: auth, CORS, logging, rate-limit, trace
  ├── router/       → Routing strategies: RoundRobin, SpecifiedClient, ConsistentHash
  ├── alert/        → Alert evaluation engine (periodic rule checking + SMTP/webhook notification)
  └── websocket/    → WebSocket message handler (client registration, heartbeat, invoke dispatch)
```

**Key constraint**: `pkg/server/client/group.go` uses an actor model — all group mutations go through `groupCommand` channel, NOT direct method calls. The `RpcGroup` goroutine serializes all operations.

## Conventions

- **Error wrapping**: `fmt.Errorf("...: %w", err)` — no `errors.Wrap` or `pkg/errors`, just stdlib `%w`.
- **Logging**: `internal/utils/logger` wraps `zap.SugaredLogger`. Use `logger.Infof/Errorf/Warningf/Debugf` — NOT `fmt.Println` or `log.Println` in production code.
- **JSON tags**: `snake_case` (e.g., `json:"user_name"`, `json:"api_token"`).
- **GORM tags**: `gorm:"column_name"` — always explicit column names.
- **Gin context keys**: `middleware.ContextUserKey = "current_user"` stores `*model.UserInfo`.
- **Auth flow**: Bearer token in `Authorization` header → DB lookup on `api_token` field → `*model.UserInfo` set in context.
- **Default admin**: Auto-created on first migration — username `admin`, password `admin123`.
- **Config**: YAML file (`config.yaml`) merged with defaults. CLI flags override YAML. Missing file is non-fatal (uses defaults).
- **Tests**: Table-driven tests with `testing` + `testify/assert`. Tests live alongside code (`*_test.go`).

## Database

- **Engine**: PostgreSQL only (GORM + `gorm.io/driver/postgres`).
- **Migration**: `database.AutoMigrate()` runs on every server start — creates/updates tables, creates default admin user and system configs.
- **SQL scripts**: `deploy/postgres/migration.sql` for manual setup, `deploy/postgres/migration/` for incremental migrations.
- **Global DB**: `database.DB` is a package-level `*gorm.DB` singleton. Access via `database.GetDB()`.
- **No transactions wrapper**: Most handlers use direct GORM calls on `database.GetDB()`.

## Frontend Dev Proxy

`web/vite.config.js` proxies API calls to `localhost:5613` (not 5612). If running the server on the default port 5612, either change the proxy target or run the server on 5613.

## Gotchas

- **Port mismatch**: Vite dev proxy targets `:5613` but default server port is `:5612`. Either change `web/vite.config.js` or start server with `-port 5613`.
- **`sample/demo-go/` has its own `go.mod`**: Module path `iinti.cn/sekiro` (not the main module). It's a standalone demo, not part of the main build.
- **Protocol detector**: The server can accept both raw Rpc binary protocol and HTTP/WebSocket on the same port. `pkg/server/detector/` peeks at the first bytes to decide.
- **Health check defaults to 3 consecutive failures**: `RpcClient` marks unhealthy after 3 fails. Route strategies skip unhealthy clients.
- **`web/dist/` must exist for `go build`**: The `//go:embed dist` directive will fail if `web/dist/` doesn't exist. Run `cd web && npm run build` first.
- **No `.golangci.yml`**: No linter config in repo. If adding one, note the project uses `fmt.Errorf` with `%w` (not `errors.Wrap`).
- **No CI workflows**: No `.github/workflows/`. Tests are run locally.
- **Config service is DB-backed**: `pkg/server/config/service.go` caches sys_config values from DB. Some runtime config changes need a manual `Refresh()` call (triggered via API).
- **Alert evaluator runs on a 1-minute interval**: Rules are loaded from DB at start and refreshed periodically. SMTP config comes from `config.yaml`.
- **QPS rate limiting**: `middleware/ratelimit.go` uses `flow.RateLimiter` with per-user and per-IP keys. Anonymous users get lower limits configured via `sys_config` table.

## Testing Notes

- Tests do NOT require a running PostgreSQL instance — most unit tests mock or avoid DB calls.
- `pkg/server/api/handlers_test.go` and `pkg/server/api/http_server_test.go` set `gin.SetMode(gin.TestMode)`.
- `web/embed_test.go` tests the embedded frontend without a real server.
- Integration tests that need DB should use the `deploy/postgres/` scripts to set up a test database.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **go-rpc** (7838 symbols, 19402 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/go-rpc/context` | Codebase overview, check index freshness |
| `gitnexus://repo/go-rpc/clusters` | All functional areas |
| `gitnexus://repo/go-rpc/processes` | All execution flows |
| `gitnexus://repo/go-rpc/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
