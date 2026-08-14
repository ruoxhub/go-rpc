# Task 11 Report — Build Reproducible Local Artifacts and Document Migration

## Implementation

- Added `scripts/build-sdk-artifacts.ps1` with validated `artifacts/<child>` output paths, exact scoped cleanup, command exit-code checks, environment/location restoration, isolated Gradle project caches, Python no-bytecode mode, five-artifact selection, and UTF-8 no-BOM SHA256 manifest generation.
- Added `scripts/test-build-sdk-artifacts.ps1` as a dependency-free path-safety check.
- Fixed debug APK output to the stable `sekiro-demo-debug.apk` name.
- Extended `scripts/verify.ps1` with TypeScript, Python, Java, and Stage 1 conformance checks while retaining mandatory impact evidence and Go/frontend checks.
- Added formal SDK/migration documentation and local-only publication guidance.

## RED / GREEN evidence

Initial RED:

```text
& powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-build-sdk-artifacts.ps1
build-sdk-artifacts.ps1 is missing
```

After the script was added, the same test passed. It rejected `artifacts`, `artifacts/../outside`, `..\outside`, and a rooted path before any build command:

```text
Artifact output path safety checks passed.
```

The first two-build attempt exposed a real reproducibility failure: the Python sdist gzip header and tar member mtimes changed between builds. The builder now normalizes sdist member order, mtime, uid/gid, names, pax headers, and gzip mtime from `SOURCE_DATE_EPOCH=1786636800`.

## Build and verification

- `powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-first` — successful.
- `powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-second` — successful; initial comparison identified only Python sdist drift.
- `powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-third` — successful after normalization.
- `powershell -File scripts/build-sdk-artifacts.ps1 -OutputDirectory artifacts/sdk-fourth` — successful.
- `Compare-Object (Get-Content artifacts/sdk-third/SHA256SUMS) (Get-Content artifacts/sdk-fourth/SHA256SUMS)` — no output.
- Final five hashes were identical across third/fourth builds: npm tgz, Python wheel, Python sdist, Java jar, and debug APK.
- `scripts/test-build-sdk-artifacts.ps1` — passed.
- Portable race environment plus `scripts/verify.ps1 -ImpactAnalysisEvidence (Get-Content artifacts/stage1-impact-evidence.txt -Raw)` — passed.
- Verify output included `PASS Go`, `PASS TypeScript/Web`, `PASS Python`, `PASS Java`, `PASS legacy`, and `All repository verification checks passed.`
- `git diff --check` — passed.

The first verify attempt without CGO failed at the pre-existing race gate (`-race requires cgo`); rerunning with the documented portable clang/CGO environment passed the complete gate.

## Artifacts

Each output directory contains exactly:

```text
go-rpc-sdk-0.1.0-experimental.1.jar
go_rpc_sdk-0.1.0.dev1-py3-none-any.whl
go_rpc_sdk-0.1.0.dev1.tar.gz
mrh30000-go-rpc-sdk-0.1.0-experimental.1.tgz
sekiro-demo-debug.apk
SHA256SUMS
```

Artifact directories are ignored and are not committed. `artifacts/stage1-impact-evidence.txt` records preliminary manual/graph evidence for the later Task 12 formal gate.

## Changed files

`scripts/build-sdk-artifacts.ps1`, `scripts/test-build-sdk-artifacts.ps1`, `scripts/verify.ps1`, `.gitignore`, `sample/xposed/app/build.gradle`, `README.md`, `sample/frida/README.md`, `sample/python/README.md`, `sample/xposed/README.md`, `sdk/typescript/README.md`, `sdk/python/README.md`, and `sdk/java/README.md`.

## Self-check / concerns

- No registry, Maven, PyPI, npm, GitHub, or other remote publication was performed.
- Gradle dependency cache is preserved in the configured/prepared `GRADLE_USER_HOME`; each build uses and removes separate temporary project-cache directories.
- The Python normalization is intentionally local to the artifact builder because the upstream setuptools sdist metadata is timestamped; source package contents are preserved while archive metadata is made deterministic.
- Review fix: the builder now rejects every existing reparse-point segment from `artifacts/` through the selected output before creating, deleting, or building anything. A real junction-to-temp regression preserved its external sentinel and passed.
- Review fix: the Xposed local-JAR example now resolves `artifacts/sdk` from the sample's Gradle `rootProject`.

## Branch review fix — SDK lifecycle, context boundary, and deletion TOCTOU

### Implementation

- Reworked the Go SDK heartbeat loop to select on the lifecycle context and expose a per-start completion channel. `Destroy` now waits for both reader and heartbeat completion within its existing wait budget.
- Added strict wire-boundary validation for exactly nine invocation-context fields, exact string/bool/number types, non-negative finite integer deadline/attempt values within representable bounds, and top-level identity matching. Invalid frames receive one status `-1` response and never enter the handler queue.
- Added a deterministic artifact deletion race hook and regression: after the initial path check, the test replaces the output directory with a junction before release; the builder performs its immediately-adjacent reparse check, rejects the path, and preserves the external sentinel.

### RED / GREEN

- RED: before the heartbeat seam existed, `go test -race ./pkg/client/sdk/... -count=1` failed to compile because `RpcClient` had no observable heartbeat completion channel.
- RED: before context validation was wired into `handleMessage`, the invalid-context table reached the handler/returned status `0` instead of the required single status `-1` response (the old tests also used incomplete contexts).
- GREEN: with the lifecycle/context changes, portable clang/CGO `go test -race ./pkg/client/sdk/... -count=1` passed (`ok .../pkg/client/sdk 1.785s`).
- GREEN: `powershell -NoProfile -File scripts/test-build-sdk-artifacts.ps1` passed both `Artifact output path safety checks passed.` and `Artifact TOCTOU reparse safety check passed.`; the race replacement was rejected with a reparse-point error and the external sentinel remained.
- GREEN: `git diff --check` passed. A no-CGO race invocation was also attempted and correctly reported the toolchain prerequisite (`-race requires cgo`); it was not counted as a test result.

### Files and concerns

Changed source/tests: `pkg/client/sdk/client.go`, `pkg/client/sdk/client_test.go`, `scripts/build-sdk-artifacts.ps1`, and `scripts/test-build-sdk-artifacts.ps1`. The completion channel is intentionally an internal test seam; no public API changed. Artifact tests create and remove only their unique junction/temp paths.
