# Task 10 Report — Stage-1 Cross-SDK Black-Box Conformance

## RED

Added `conformance/runner/main_test.go` before implementing the runner. The
initial focused command:

```text
go test ./conformance/runner/...
```

failed to compile with `undefined: runAdapter`, proving the required command
runner seam was absent. The test then covered exact adapter name, exit code,
stdout, stderr, and context-timeout propagation.

## GREEN

```text
go test ./conformance/runner/...
```

PASS.

```text
go test ./pkg/handler ./conformance/runner/...
```

PASS, including explicit DB-less authorization regression coverage.

```text
go run ./conformance/runner
```

PASS Go
PASS TypeScript/Web
PASS Python
PASS Java
PASS legacy

The run used one random loopback port, real `/health`, serial 60-second
adapter limits, process cleanup, registration/bind/invoke/destroy, and legacy
silence plus second-connection invocation evidence.

## Changes

- Added runner lifecycle, command failure propagation tests, Unix process-group
  and Windows process-tree cleanup helpers.
- Added Go, TypeScript/Node, and Python formal-SDK adapters.
- Added Java real-server conformance target and Gradle test JVM property
  forwarding.
- Added legacy raw WebSocket/HTTP evidence and `conformance/README.md`.
- Added explicit `dbLessMode` injection to `APIHandler`; default nil dependency
  authorization remains fail-closed, while `ServerConfig.DisableDatabase` is
  the only anonymous DB-less path.

## Concerns

The runner sets all required disable flags, including `RPC_DISABLE_TRACE=true`.
Trace correlation is now generated at the HTTP response boundary when the
optional trace middleware/persistence is disabled, so metadata remains present
without enabling recording. No dependency installation or remote operation is
performed.

## Fix Round 1

- Restored the exact eight-parameter `NewAPIHandler` and added the explicit
  `NewAPIHandlerWithDBLessMode`; the ordinary constructor remains fail-closed.
- Replaced Go invoke retry with bounded `/business/clientQueue` readiness
  polling followed by exactly one formal HTTP invoke.
- Added a 60-second context to legacy, `DialContext`/request contexts, bounded
  read deadlines, and joined the HTTP goroutine before return.
- Isolated Java project cache in a temporary directory, propagated the prepared
  Gradle home, and disabled Python bytecode output.
- Moved Java disconnect into an all-path `finally`; added trace fallback and
  authorization regression tests.

Final evidence:

```text
go test ./conformance/runner/... ./pkg/handler/... -count=1  PASS
go run ./conformance/runner  PASS Go / PASS TypeScript/Web / PASS Python / PASS Java / PASS legacy
```

The worktree was clean before the final commit; generated Java/Python caches
were removed before staging. No dependency installation or remote write was
performed.

## Fix Round 2

- `runLegacy` now installs one all-return-path `defer` immediately after the
  HTTP goroutine starts; it cancels the request context and waits for the
  buffered-result goroutine before every return. WebSocket deadlines remain
  bounded by the parent context.
- Java `postInvoke` is normally indented and disconnects from an all-path
  `finally`.
- Re-ran the runner/handler focused tests, isolated-cache Java test, and the
  real runner; all passed. The existing timeout test verifies cancellation
  propagation but does not assert a separately spawned descendant PID. The
  current cross-platform helper has no portable child-PID injection seam;
  adding shell/platform process fixtures would be brittle and outside this
  minimal fix.
