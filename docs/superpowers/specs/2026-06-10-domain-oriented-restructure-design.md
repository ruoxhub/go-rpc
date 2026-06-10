# Domain-Oriented Project Restructure Design

## Goal

Restructure the repository around business domains instead of broad technical buckets, while preserving all existing user-facing commands and deployment entrypoints.

The restructure is design-first and phased. It should not start with a large file move. The first deliverable is a target structure, dependency rules, and migration plan that keep the current platform working throughout the transition.

## Constraints

- Preserve `go run ./main.go` as the full platform server entrypoint.
- Preserve `go test ./...`.
- Preserve `cd web && npm run dev`.
- Preserve the current Docker build path.
- Treat the whole repository as in scope: Go backend, web frontend, samples, deployments, and docs.
- Prefer phased migration with compatibility facades over a single large directory move.

## Chosen Approach

Use a domain-oriented structure with a clean `pkg/core` runtime kernel.

This differs from a pure `pkg/rpc` naming scheme because the extracted package is not just a collection of RPC helpers. It is the minimal runtime core that platform, observability, and optional gateways build on top of.

## Target Structure

```text
cmd/
  server/
  client/
  invoker/
  rpc-core/

internal/
  config/
  utils/
  compat/

pkg/
  core/
    registry/
    router/
    forwarder/
    websocket/
    transport/
    httpapi/
  platform/
    auth/
    admin/
    users/
    groups/
    sysconfig/
  observability/
    metrics/
    trace/
    alert/
  aigateway/
    api/
    prompt/
    toolcall/
  sdk/
    client/
    invoker/
  shared/
    protocol/
    compress/
    eventbus/
    password/
    traceid/
  database/
  model/

web/
samples/
deploy/
docs/
```

## Domain Responsibilities

### `pkg/core`

Owns the minimal runtime kernel:

- WebSocket and TCP connections
- client registration
- group registry
- specified-client routing
- round-robin routing
- request forwarding
- timeout waiting and cleanup
- core HTTP API

`pkg/core` must be able to run without PostgreSQL, the web admin UI, metrics, tracing, alerting, or AI gateway code.

### `pkg/platform`

Owns the managed platform layer:

- user authentication
- token handling
- authorization
- group administration
- system configuration
- management API handlers
- database-backed platform rules

Platform code may call `core`. Core code must not call platform code.

### `pkg/observability`

Owns operational visibility:

- metrics collection
- trace records
- alert evaluation
- alert delivery integrations

This domain should attach to core and platform behavior through hooks, events, or explicit service interfaces. It should not be embedded directly inside the core request forwarding path.

### `pkg/aigateway`

Owns AI compatibility surfaces:

- OpenAI-compatible APIs
- Qwen-compatible APIs
- prompt compatibility
- tool-call parsing and formatting

This keeps AI gateway behavior separate from the RPC runtime and platform administration code.

### `pkg/sdk`

Owns reusable Go client code:

- RPC client SDK
- invoker SDK

SDK packages may depend on shared protocol and compression packages. They must not depend on server-only platform packages.

### `pkg/shared`

Owns stable cross-domain primitives:

- protocol codec
- compression implementations
- event bus
- password helpers
- trace ID helpers

A package should only move into `shared` if at least two business domains actually depend on it and it does not contain domain policy.

### `web`

Remains a standalone Vite frontend application. It should not be moved into Go package layout.

### `samples`

Unifies current sample material and the `JsRpc` example surface over time. Existing sample paths can be preserved through transitional docs or compatibility wrappers until references are updated.

### `deploy`

Owns deployment assets:

- Docker files
- compose files
- SQL scripts
- migration scripts
- environment examples

## Dependency Rules

Allowed high-level dependency direction:

```text
cmd
  -> platform / core / sdk

platform
  -> core
  -> observability
  -> database / model
  -> shared

observability
  -> core contracts or events
  -> database / model
  -> shared

aigateway
  -> shared
  -> optional platform auth

core
  -> shared

sdk
  -> shared

shared
  -> standard library / small third-party libraries only
```

## Forbidden Dependencies

`pkg/core` must not import:

```text
github.com/mrh30000/go-rpc/pkg/database
github.com/mrh30000/go-rpc/pkg/model
github.com/mrh30000/go-rpc/pkg/platform
github.com/mrh30000/go-rpc/pkg/observability
github.com/mrh30000/go-rpc/pkg/aigateway
github.com/mrh30000/go-rpc/pkg/server/handlers
github.com/mrh30000/go-rpc/web
github.com/mrh30000/go-rpc/internal/prompt
github.com/mrh30000/go-rpc/internal/promptcompat
github.com/mrh30000/go-rpc/internal/toolcall
```

`pkg/shared` must not import:

```text
github.com/mrh30000/go-rpc/pkg/core
github.com/mrh30000/go-rpc/pkg/platform
github.com/mrh30000/go-rpc/pkg/observability
github.com/mrh30000/go-rpc/pkg/aigateway
github.com/mrh30000/go-rpc/pkg/database
github.com/mrh30000/go-rpc/pkg/model
```

## Migration Plan

### Phase 0: Structure Map

Create and maintain a migration map from old paths to target paths. This phase produces documentation only.

Example:

```text
pkg/server/client      -> pkg/core/registry
pkg/server/router      -> pkg/core/router
pkg/server/forwarder   -> pkg/core/forwarder
pkg/server/websocket   -> pkg/core/websocket
pkg/server/metrics     -> pkg/observability/metrics
pkg/server/alert       -> pkg/observability/alert
pkg/client             -> pkg/sdk
pkg/protocol           -> pkg/shared/protocol
pkg/compress           -> pkg/shared/compress
pkg/eventbus           -> pkg/shared/eventbus
```

### Phase 1: Shared And SDK

Move low-risk cross-domain packages first:

- protocol
- compression
- event bus
- password helpers
- trace ID helpers
- Go client and invoker SDK

Keep compatibility facades at old import paths until internal imports are migrated.

### Phase 2: Core Runtime

Introduce `pkg/core` and move only the minimal runtime path:

```text
HTTP invoke -> route client -> WebSocket send -> timeout wait -> HTTP response
WebSocket register -> registry add -> read response -> complete request
```

The old `pkg/server` packages can temporarily forward to `pkg/core` to avoid a large breaking diff.

### Phase 3: Platform, Observability, And AI Gateway

Split non-core behavior into domain packages:

- platform auth, users, groups, system config, and admin APIs
- observability metrics, trace, and alerting
- AI gateway API, prompt compatibility, and tool-call parsing

Platform behavior should attach to core behavior through explicit hooks, events, or service interfaces.

### Phase 4: Repository Surface

Clean up repository-level structure:

- keep `web/` as the frontend app
- migrate `sample/` and `JsRpc/` toward `samples/`
- keep deployment assets under `deploy/`
- update README and architecture docs

### Phase 5: Remove Transitional Facades

After internal imports and docs are updated:

- delete old compatibility facades
- remove stale package names
- enforce import boundaries in tests
- verify all preserved entrypoints still work

## Testing Strategy

### Boundary Tests

Add an import boundary test or script that fails when forbidden dependencies are introduced into `pkg/core` or `pkg/shared`.

### Core Behavior Tests

Cover:

- client registration
- unregister cleanup
- duplicate client handling
- group listing
- client queue listing
- specified-client routing
- round-robin routing
- invoke timeout cleanup
- WebSocket response completion by sequence
- GET and POST invoke compatibility

### Platform Regression Tests

Preserve coverage for:

- full platform startup behavior
- authentication
- authorization
- management APIs
- metrics integration
- trace integration
- alert integration
- frontend embedding

## Verification Commands

Full verification target:

```bash
go test ./...
go run ./main.go
cd web && npm run build
docker build .
```

Focused Go verification during early phases:

```bash
go test ./pkg/core/...
go test ./pkg/server/...
go test ./pkg/client/...
```

If a full regression fails because of an existing unrelated issue, record the failure and distinguish it from restructure-introduced failures.

## Risks And Mitigations

### Circular Imports

Risk: large package moves introduce cycles.

Mitigation: enforce one-way dependencies and move one domain at a time.

### Shared Package Drift

Risk: `pkg/shared` becomes a miscellaneous package.

Mitigation: require real cross-domain use and no domain policy before moving code into shared.

### Platform Becoming A New Monolith

Risk: `pkg/platform` replaces `pkg/server` as the large mixed-responsibility package.

Mitigation: split platform by auth, admin, users, groups, and sysconfig from the beginning.

### Lost Side Effects

Risk: moving the core invocation path drops auth, trace, metrics, alert, or persistence behavior.

Mitigation: preserve these behaviors through explicit hooks, events, or service interfaces and cover them with platform regression tests.

### Broken Examples And Docs

Risk: moving `sample/` or `JsRpc/` breaks references.

Mitigation: migrate examples after backend domains stabilize, and update docs in the same phase.

## Success Criteria

- Existing entrypoints and commands remain valid.
- The target directory structure is documented.
- `pkg/core` has no database, platform, observability, AI gateway, or web dependencies.
- `pkg/shared` has no business-domain dependencies.
- Migration can proceed one domain at a time.
- Compatibility facades allow old paths to keep working during migration.
- Tests enforce the most important dependency boundaries.
