# SDD ledger — plan: docs/superpowers/plans/2026-08-14-stage-1-protocol-sdk-baseline.md

Setup: isolated worktree branch codex/stage-1-protocol-sdk-baseline from 81c328d.
Setup: pre-flight plan/spec conflict scan clean.
Setup: baseline `go test ./...` PASS after generating required `web/dist`.
Setup: codebase-memory project `go-rpc-stage1` indexed (3157 nodes, 15445 edges; no skipped source files).
Task 1: minor (deferred): tests do not assert ProtocolVersion and every registered-message JSON field value exactly.
Task 1: reviewer warning resolved — RED/GREEN evidence is recorded in task-1-report.md; HTTP status and connection-send behavior are downstream Tasks 2–4, not Task 1 scope.
Task 1: complete (commits 81c328d..da61bd0, review clean)
Task 2: minor (deferred): helper tests lack a successful enabled negotiation assertion.
Task 2: reviewer warning resolved — RED/GREEN and independent build evidence is recorded in task-2-report.md; active-route ordering is explicitly Task 3 scope.
Task 2: complete (commits da61bd0..678f604, review clean)
Task 3: pre-change impact recorded in task-3-impact.md — `main.handleRegister` and both production `Handler.HandleConnection` callers are CRITICAL.
Task 3: fix round 1/5 (2 addressed, 0 open; commits 59403f2..a64739b)
Task 3: complete (commits 678f604..a64739b, review clean)
Task 4: pre-change impact recorded in task-4-impact.md — five direct production callers of `Handler.SendInvokeRequest` are CRITICAL and converge at the shared method.
Task 4: minor (deferred): value-object test does not assert trace/group/action/client_id mapping field by field.
Task 4: verification debt: Go race suite cannot run because the Windows environment has CGO disabled and no `gcc` compiler installed.
Task 4: race debt superseded — SHA-verified portable LLVM-MinGW enabled the gate; it exposed a reproducible concurrent `WSConnection.Close` race. Root-cause record: task-4-race-debug.md.
Task 4: fix round 1/5 (1 addressed, 0 open; commits de15d80..6145241)
Task 4: fix round 2/5 (1 addressed, 0 open; commits 6145241..9c753a4)
Task 4: complete (commits a64739b..9c753a4, review clean; full race gate PASS via SHA-verified portable LLVM-MinGW)
Task 5: pre-change impact recorded in task-5-impact.md — no internal production callers, but the preserved RpcInvoker API is an external HIGH-risk compatibility surface.
Task 5: minor (deferred): no successful two-call/two-endpoint round-robin ordering regression test.
Task 5: reviewer warning resolved — RED/GREEN commands and outputs are recorded in task-5-report.md.
Task 5: complete (commits 9c753a4..e261bea, review clean)
Task 6: pre-change impact recorded in task-6-impact.md — public executor API is HIGH risk; binary-only internals have no remaining consumers after Task 5.
Task 6: minor (deferred): confirmation-before-bind test gates server reads and does not directly prove no early frame via a pre-confirmation read deadline.
Task 6: fix round 1/5 (2 addressed, 1 open — untracked/unbounded dispatch goroutines introduced by fix; commits 6ef57e8..1849cf7)
Task 6: fix round 2/5 (1 addressed, 0 open; commits 1849cf7..72d42e2)
Task 6: complete (commits e261bea..72d42e2, review clean; package race PASS)
Task 7: pre-change impact recorded in task-7-impact.md — new external npm/SDK API is HIGH risk, with no existing internal consumers or server-core changes.
Task 7: review requested changes (4 Important): stale/duplicate registration lifecycle, non-text frame handling, runtime invocation-context validation, and compiled tests leaking into the npm package.
Task 7: fix round 1/5 (4 Important and 1 Minor test-gap finding addressed, 0 open; commits e7a24b5..5e8cb16).
Task 7: package whitelist intentionally narrowed from `dist` to `dist/browser` + `dist/src` because npm 11 ignores `.npmignore` exclusions beneath an explicitly included directory; scoped review accepted the minimal compatibility-preserving deviation.
Task 7: complete (commits 72d42e2..5e8cb16, review clean; npm test 8/8 and pack gate PASS).
Task 8: pre-change impact recorded in task-8-impact.md — new Python package is HIGH risk; sample caller conventions are reusable only after removing tenacity/retry behavior.
Task 8: review requested changes (3 Important): serialize concurrent start, avoid handler-initiated destroy self-wait, and clean heartbeat/handlers on remote reader exit. Two Minor items: async context manager symmetry and stronger behavior-specific RED evidence.
Task 8: fix round 1/5 (3 Important and 2 Minor findings addressed, 0 open; commits 45562c8..ce5616f).
Task 8: complete (commits 5e8cb16..ce5616f, review clean; unittest 16/16, wheel+sdist gate PASS).
Task 9: pre-change impact recorded in task-9-impact.md — deleting nine app-local API sources and replacing them through composite build is CRITICAL; baseline Android compile also has a pre-existing Fastjson conversion error in RpcRequest.
Task 9: review requested changes (2 Critical, 7 Important): restore legacy send/actionDelay behavior, retain stream metadata, signal readiness on close, reject binary frames, enforce exact/matching context, hide cancellation mutation, avoid handler destroy self-wait, replace inadequate tests, and format the critical Java seam normally. Deferred inherited Minor: cached worker pool remains unbounded.
Task 10: added cross-SDK black-box runner, Go/TypeScript/Python/Java/legacy adapters, explicit DB-less injection, trace correlation fallback, and process cleanup; focused runner/handler tests and real runner all PASS.
Task 10 fix round 1: restored NewAPIHandler compatibility, single Go invoke after clientQueue readiness, bounded/joined legacy lifecycle, isolated Java/Python caches, and all conformance passes.
Task 11: added scoped reproducible artifact builder, verification matrix, SDK migration docs, fixed debug APK naming, and path-safety test; third/fourth artifact manifests are identical and full verify gate passes with portable CGO/race environment.
Task 11 fix round 1: rejected junction/symlink output escapes with a real external-sentinel regression and corrected the Xposed local-JAR path.
