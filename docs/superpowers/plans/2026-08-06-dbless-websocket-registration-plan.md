# DB-less WebSocket Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore anonymous `/business/register` access when the server is explicitly configured for DB-less operation while preserving fail-closed authorization in database mode.

**Architecture:** Keep the change in the existing `Server` composition root. `authorizeRegisterAccess` will branch on the loaded `ServerConfig.DisableDatabase` value before touching database-backed authorization dependencies; the existing database-mode authorization path remains unchanged. The DB-less startup branch will emit an explicit security warning rather than introducing a new authentication abstraction or configuration surface.

**Tech Stack:** Go, Gin, `net/http/httptest`, existing `internal/config`, existing repository logger, Go `testing` package.

## Global Constraints

- DB-less mode allows anonymous access to the existing `/business/*` surface; do not add tokens, IP allowlists, policy enums, persistence, or rate limiting.
- Database mode must retain its existing group lookup, token validation, ownership checks, and fail-closed behavior.
- Determine DB-less mode only from the loaded `ServerConfig.DisableDatabase` value, never from nil repositories.
- Keep the implementation surgical: modify only `main.go` and `main_test.go`.
- Production logging must use `internal/utils/logger`.
- Format changed Go files with `gofmt` and run the repository verification commands through `rtk`.

## File Structure

- Modify `main.go`: explicitly authorize registrations in configured DB-less mode and emit the startup security warning.
- Modify `main_test.go`: add focused regression tests for DB-less authorization and database-mode fail-closed behavior.

---

### Task 1: Distinguish configured DB-less mode from broken database authorization

**Files:**
- Modify: `main_test.go`
- Modify: `main.go:643`

**Interfaces:**
- Consumes: `Server.serverConfig *config.ServerConfig` and `config.ServerConfig.DisableDatabase bool`.
- Produces: unchanged method signature `func (s *Server) authorizeRegisterAccess(c *gin.Context, groupName string) bool`; it returns `true` immediately only when `DisableDatabase` is explicitly true.

- [ ] **Step 1: Write the failing authorization regression tests**

Append these tests to `main_test.go`:

```go
func TestAuthorizeRegisterAccess_DBlessAllowsAnonymousRegistration(t *testing.T) {
	gin.SetMode(gin.TestMode)

	s := &Server{
		serverConfig: &config.ServerConfig{DisableDatabase: true},
	}
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group=kalodata&clientId=test", nil)

	if !s.authorizeRegisterAccess(c, "kalodata") {
		t.Fatalf("authorizeRegisterAccess() = false in DB-less mode; status=%d body=%s", w.Code, w.Body.String())
	}
	if w.Code == http.StatusServiceUnavailable {
		t.Fatalf("DB-less registration returned 503: %s", w.Body.String())
	}
}

func TestAuthorizeRegisterAccess_DatabaseModeWithoutDependenciesFailsClosed(t *testing.T) {
	gin.SetMode(gin.TestMode)

	s := &Server{
		serverConfig: &config.ServerConfig{DisableDatabase: false},
	}
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/register?group=kalodata&clientId=test", nil)

	if s.authorizeRegisterAccess(c, "kalodata") {
		t.Fatal("authorizeRegisterAccess() = true without database authorization dependencies")
	}
	if w.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d; body=%s", w.Code, http.StatusServiceUnavailable, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "group access verification unavailable") {
		t.Fatalf("unexpected response body: %s", w.Body.String())
	}
}
```

- [ ] **Step 2: Run the focused tests and verify the DB-less case fails**

Run:

```powershell
rtk go test . -run "TestAuthorizeRegisterAccess_(DBlessAllowsAnonymousRegistration|DatabaseModeWithoutDependenciesFailsClosed)$" -count=1
```

Expected: `TestAuthorizeRegisterAccess_DBlessAllowsAnonymousRegistration` fails because the current nil `groupRepo`/`authMW` guard returns `503`; the database-mode test passes.

- [ ] **Step 3: Add the minimal explicit DB-less branch**

In `main.go`, add this branch at the start of `authorizeRegisterAccess`, before the global IP allowlist and nil dependency checks:

```go
func (s *Server) authorizeRegisterAccess(c *gin.Context, groupName string) bool {
	// DB-less mode intentionally exposes /business/* without authentication.
	// Check the explicit mode flag rather than inferring it from nil repositories,
	// so broken database-mode dependency wiring remains fail-closed.
	if s.serverConfig != nil && s.serverConfig.DisableDatabase {
		return true
	}

	// Existing database-mode authorization continues below unchanged.
```

Do not change the existing `s.groupRepo == nil || s.authMW == nil` guard or any subsequent database-mode authorization code.

- [ ] **Step 4: Format and rerun focused tests**

Run:

```powershell
rtk gofmt -w main.go main_test.go
rtk go test . -run "TestAuthorizeRegisterAccess_(DBlessAllowsAnonymousRegistration|DatabaseModeWithoutDependenciesFailsClosed)$" -count=1
```

Expected: both tests pass.

- [ ] **Step 5: Run existing configuration and route regressions**

Run:

```powershell
rtk go test ./internal/config -run "TestLoadServerConfigFromEnv(ReadsAllFields|ReturnsDefaultsWhenEmpty)$" -count=1
rtk go test . -run "Test(RegisterRoutesChatCompletionsAndV1NoRoute|AuthorizeRegisterAccess_)" -count=1
```

Expected: all selected tests pass, confirming the environment flag is still loaded and existing routes remain intact.

- [ ] **Step 6: Review and commit the authorization change**

Run:

```powershell
rtk git diff --check
rtk git diff -- main.go main_test.go
rtk git add -- main.go main_test.go
rtk git commit -m "fix(server): allow registration in DB-less mode"
```

Expected: the diff contains only the two regression tests and the explicit DB-less authorization branch.

---

### Task 2: Warn when DB-less business APIs are anonymously exposed

**Files:**
- Modify: `main.go:288`

**Interfaces:**
- Consumes: the existing `disableDB` startup branch in `Server.Start`.
- Produces: a warning log with a stable, searchable statement that `/business/*` is anonymously accessible and must not be exposed to untrusted networks.

- [ ] **Step 1: Add the explicit startup security warning**

Replace the existing generic DB-less warning block:

```go
} else {
	logger.Info("Running in DB-less mode (DisableDatabase=true)")
	logger.Warn("数据库未初始化，跳过配置刷新")
```

with:

```go
} else {
	logger.Info("Running in DB-less mode (DisableDatabase=true)")
	logger.Warn("SECURITY: DB-less mode allows anonymous access to /business/*; do not expose this server to untrusted networks")
	logger.Warn("数据库未初始化，跳过配置刷新")
```

Keep the existing metrics collector behavior below the warning unchanged.

- [ ] **Step 2: Format and verify the warning and focused behavior**

Run:

```powershell
rtk gofmt -w main.go
rtk rg -n "SECURITY: DB-less mode allows anonymous access to /business/\\*" main.go
rtk go test . -run "TestAuthorizeRegisterAccess_" -count=1
```

Expected: `rg` finds exactly one warning in the DB-less startup branch and both authorization tests pass.

- [ ] **Step 3: Run repository-wide verification**

Run:

```powershell
rtk go test ./...
rtk go build ./...
```

Expected: both commands exit successfully. If the repository validation gate is available, also run:

```powershell
rtk proxy pwsh -NoProfile -File scripts/verify.ps1 -ImpactAnalysisEvidence "Manual review: main.go DB-less authorization branch only; database-mode fail-closed path retained and covered by regression tests"
```

Expected: the validation gate passes, or its output records any environment-only prerequisite that cannot run locally.

- [ ] **Step 4: Perform the manual WebSocket acceptance check**

Start the server using the approved environment configuration:

```dotenv
RPC_DISABLE_WEB_ADMIN=true
RPC_DISABLE_METRICS=true
RPC_DISABLE_ALERT=true
RPC_DISABLE_DATABASE=true
```

Verify all of the following:

- Startup output contains the `SECURITY: DB-less mode allows anonymous access to /business/*` warning.
- Kalodata Extractor connects to `/business/register?group=kalodata&clientId=<generated-id>` without a reconnect loop.
- The server does not return `503` with `group access verification unavailable`.
- The browser no longer reports close code `1006` for this authorization failure.

- [ ] **Step 5: Review and commit the warning**

Run:

```powershell
rtk git diff --check
rtk git diff -- main.go
rtk git add -- main.go
rtk git commit -m "docs(server): warn about anonymous DB-less access"
```

Expected: the diff contains only the DB-less startup warning added after Task 1.
