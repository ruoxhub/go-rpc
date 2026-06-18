# AGENTS.md — Rpc-Go

## Quick Start

```bash
# Build everything
go build ./...

# Build server binary
go build -o rpc-server ./main.go

# Run tests (all packages)
go test ./...

# Run single package tests
go test ./pkg/protocol/...
go test ./pkg/compress/...
go test ./pkg/client/...
go test ./pkg/handler/...

# Run a single test
go test -run TestRpcPacket ./pkg/protocol/...
go test -run TestGzipCompress ./pkg/compress/...

# Start server (requires PostgreSQL)
go run main.go -c config.yaml

# Frontend dev
cd web && npm install && npm run dev   # port 3000, proxies /business|/api|/rpc-api → localhost:5613

# Frontend production build (embedded into Go binary via //go:embed)
cd web && npm run build                # outputs to web/dist/
```

## Architecture

**Module path**: `github.com/mrh30000/go-rpc`

**Single entry point**: `main.go` is the server composition root. It wires all `pkg/` packages together via `NewServer()` and `Start()`. The SDK lives at `pkg/client/sdk/` for external consumers.

**Request flow**: Invoker → HTTP POST `/business/invoke` → `handler.APIHandler.HandleInvoke` → `forwarder.TimeoutManager` tracks request → `router.Router` picks client (round-robin / specified / consistent-hash) → `websocket.Handler` sends to client → client response arrives back on channel → APIHandler returns to invoker.

**Bootstrap sequence** (`main.go`): YAML config → logger init → PostgreSQL connect + AutoMigrate → config service → WebSocket handler → metrics collector → alert evaluator → Gin engine → route registration → `net.Listen` → serve.

**Frontend embedding**: `web/embed.go` uses `//go:embed dist` to bundle the React SPA into the binary. No separate static file server needed. `npm run build` in `web/` must produce `web/dist/` before `go build`.

## Package Boundaries

```
main.go        → Server composition root (Config, Server, NewServer, Start, Shutdown)
main_test.go   → Integration tests for route registration and HTTP config
internal/      → Private packages (config, utils/logger) — not importable by external code
pkg/client/    → Server-side client management: RpcClient, RpcGroup, ClientManager
pkg/client/sdk/→ SDK for external consumers: RpcClient + RpcInvoker (used by sample code)
pkg/protocol/  → Binary packet codec — shared between server and client
pkg/compress/  → Gzip/Snappy/None compression — used by protocol layer
pkg/transport/ → Connection abstraction (TCP + WebSocket) — leaf package, no pkg/ imports
pkg/database/  → Global *gorm.DB singleton + AutoMigrate
  └── repository/ → Repository interfaces and implementations
pkg/model/     → GORM models (UserInfo, GroupConfig, AlertRule, TraceRecord, DefaultGroupActions)
pkg/eventbus/  → Simple pub/sub event bus
pkg/handler/   → Unified HTTP handlers: APIHandler (invoke/chat/qwen) + Web management (user, group, metric, trace, alert, sysconfig) + response types (ApiResponse, RpcResponse, RpcExtraResponse) + HTTPServer wrapper
pkg/config/    → Runtime config service (reads from DB sys_config table)
pkg/flow/      → Rate limiter + backoff for empty queues
pkg/forwarder/ → TimeoutManager: tracks in-flight RPC calls with channels + stream frame handling
pkg/middleware/ → Gin middleware: auth, CORS, logging, rate-limit, trace
pkg/router/    → Routing strategies: RoundRobin, SpecifiedClient, ConsistentHash
pkg/alert/     → Alert evaluation engine (periodic rule checking + SMTP/webhook notification)
pkg/metrics/   → MetricCollector: aggregates invoke counts/latency into minute/hour/day tables
pkg/websocket/ → WebSocket message handler (client registration, heartbeat, invoke dispatch)
pkg/utils/     → Utility functions (code helpers, file ops)
  ├── password/  → Password hashing
  └── traceid/   → Trace ID generation
web/           → React SPA frontend (embedded via //go:embed dist)
```

**Key constraint**: `pkg/client/group.go` uses an actor model — all group mutations go through `groupCommand` channel, NOT direct method calls. The `RpcGroup` goroutine serializes all operations.

**Dependency layers** (bottom to top):
- Leaf: `pkg/transport`, `pkg/protocol`, `pkg/compress`, `pkg/eventbus`, `pkg/model`
- Mid: `pkg/client`, `pkg/config`, `pkg/flow`, `pkg/forwarder`, `pkg/middleware`, `pkg/router`, `pkg/alert`, `pkg/metrics`, `pkg/websocket`
- Top: `pkg/handler` (depends on most mid-layer packages)
- Root: `main.go` (wires everything together)

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
- **SDK package name**: `pkg/client/sdk` uses Go package name `client` (not `sdk`), so SDK example code still uses `client.NewRpcClient` when importing `github.com/mrh30000/go-rpc/pkg/client/sdk`.
- **Health check defaults to 3 consecutive failures**: `RpcClient` marks unhealthy after 3 fails. Route strategies skip unhealthy clients.
- **`web/dist/` must exist for `go build`**: The `//go:embed dist` directive will fail if `web/dist/` doesn't exist. Run `cd web && npm run build` first.
- **No `.golangci.yml`**: No linter config in repo. If adding one, note the project uses `fmt.Errorf` with `%w` (not `errors.Wrap`).
- **No CI workflows**: No `.github/workflows/`. Tests are run locally.
- **Config service is DB-backed**: `pkg/config/service.go` caches sys_config values from DB. Some runtime config changes need a manual `Refresh()` call (triggered via API).
- **Alert evaluator runs on a 1-minute interval**: Rules are loaded from DB at start and refreshed periodically. SMTP config comes from `config.yaml`.
- **QPS rate limiting**: `pkg/middleware/ratelimit.go` uses `flow.RateLimiter` with per-user and per-IP keys. Anonymous users get lower limits configured via `sys_config` table.
- **Response type split**: `pkg/handler/response.go` defines three response types — `ApiResponse` (admin `/api/*`), `RpcResponse` (external `/rpc-api/*` and `/business/*`), `RpcExtraResponse` (with routing metadata). Frontend `Login.jsx` depends on `status === 0` for success.

## Testing Notes

- Tests do NOT require a running PostgreSQL instance — most unit tests mock or avoid DB calls.
- `pkg/handler/invoke_test.go` and `pkg/handler/http_server_test.go` set `gin.SetMode(gin.TestMode)`.
- `main_test.go` tests route registration and HTTP config directly on the `Server` struct.
- `web/embed_test.go` tests the embedded frontend without a real server.
- Integration tests that need DB should use the `deploy/postgres/` scripts to set up a test database.
- Some Qwen-related tests require fixture files (`qwenai_completions_response.txt`, `completions_request_body.json`) in the repo root.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **go-rpc** (8280 symbols, 20839 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

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

<!-- CODEGRAPH_START -->
## CodeGraph

This project has a CodeGraph MCP server (`codegraph_*` tools) configured. CodeGraph is a tree-sitter-parsed knowledge graph of every symbol, edge, and file. Reads are sub-millisecond and return structural information grep cannot.

### When to prefer codegraph over native search

Use codegraph for **structural** questions — what calls what, what would break, where is X defined, what is X's signature. Use native grep/read only for **literal text** queries (string contents, comments, log messages) or after you already have a specific file open.

| Question | Tool |
|---|---|
| "Where is X defined?" / "Find symbol named X" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "What does Y call?" | `codegraph_callees` |
| "How does X reach/become Y? / trace the flow from X to Y" | `codegraph_trace` (one call = the whole path, incl. callback/React/JSX dynamic hops) |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Show me Y's signature / source / docstring" | `codegraph_node` |
| "Give me focused context for a task/area" | `codegraph_context` |
| "See several related symbols' source at once" | `codegraph_explore` |
| "What files exist under path/" | `codegraph_files` |
| "Is the index healthy?" | `codegraph_status` |

### Rules of thumb

- **Answer directly — don't delegate exploration.** For "how does X work" / architecture questions, answer with 2-3 codegraph calls: `codegraph_context` first, then ONE `codegraph_explore` for the source of the symbols it surfaces. For a specific **flow** ("how does X reach Y") start with `codegraph_trace` from→to — one call returns the whole path with dynamic hops bridged — then ONE `codegraph_explore` for the bodies; don't rebuild the path with `codegraph_search` + `codegraph_callers`. Codegraph IS the pre-built index, so spawning a separate file-reading sub-task/agent — or running a grep + read loop — repeats work codegraph already did and costs more for the same answer.
- **Trust codegraph results.** They come from a full AST parse. Do NOT re-verify them with grep — that's slower, less accurate, and wastes context.
- **Don't grep first** when looking up a symbol by name. `codegraph_search` is faster and returns kind + location + signature in one call.
- **Don't chain `codegraph_search` + `codegraph_node`** when you just want context — `codegraph_context` is one call.
- **Don't loop `codegraph_node` over many symbols** — one `codegraph_explore` call returns several symbols' source grouped in a single capped call, while each separate node/Read call re-reads the whole context and costs far more.
- **Index lag — check the staleness banner, don't guess a wait.** When a codegraph response starts with "⚠️ Some files referenced below were edited since the last index sync…", the listed files are pending re-index — Read those specific files for accurate content. Files NOT in that banner are fresh and codegraph is authoritative for them. `codegraph_status` also lists pending files under "Pending sync".

### If `.codegraph/` doesn't exist

The MCP server returns "not initialized." Ask the user: *"I notice this project doesn't have CodeGraph initialized. Want me to run `codegraph init -i` to build the index?"*
<!-- CODEGRAPH_END -->
