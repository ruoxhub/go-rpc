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
