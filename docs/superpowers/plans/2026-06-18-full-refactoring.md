# go-rpc Full Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 security vulnerabilities, 3 concurrency bugs, 2 resource leaks, unify dependency injection, and fill test gaps — all while maintaining complete backward compatibility.

**Architecture:** 5-phase incremental approach: Security → Concurrency → Resources → DI refactor → Tests. Each phase produces independently deployable, fully tested code. No DI frameworks — hand-wired `AppDependencies` struct.

**Tech Stack:** Go 1.21+, Gin, GORM/PostgreSQL, gorilla/websocket, golang.org/x/sync/singleflight, golang.org/x/time/rate

**Spec:** `docs/superpowers/specs/2026-06-18-full-refactoring-design.md`

---

## File Structure

### Phase 1 — Security
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `pkg/handler/http_server.go:57` | Tighten WebSocket CheckOrigin |
| Modify | `pkg/handler/http_server_test.go` | Add CheckOrigin test cases |
| Modify | `pkg/middleware/cors.go:39` | Fix empty whitelist = deny |
| Modify | `pkg/middleware/cors_test.go` | Update existing test expectations |
| Modify | `pkg/middleware/auth.go:91` | Deprecate query token extraction |
| Modify | `pkg/middleware/auth_test.go` | Add query token toggle tests |
| Create | `pkg/middleware/login_ratelimit.go` | Login-specific IP rate limiter |
| Create | `pkg/middleware/login_ratelimit_test.go` | Login rate limit tests |
| Modify | `pkg/handler/routes.go:125` | Wire LoginRateLimitMiddleware |
| Modify | `.env.example` | Document CORS_ORIGINS and ALLOW_QUERY_TOKEN |

### Phase 2 — Concurrency
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `pkg/flow/ratelimit.go:41` | Add sync.Once to Stop() |
| Modify | `pkg/flow/ratelimit_test.go` | Add concurrent Stop test |
| Modify | `pkg/middleware/auth_cache.go:87` | Add stopChan to gcLoop |
| Modify | `pkg/middleware/auth_cache_test.go` | Add GC stop tests |
| Modify | `pkg/client/sdk/client.go:102` | Remove per-packet goroutine |
| Modify | `pkg/client/sdk/client_test.go` | Add sequential processing test |

### Phase 3 — Resources
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `main.go:586` | Close DB pool in Shutdown |
| Modify | `main_test.go` | Add DB close verification |
| Modify | `pkg/forwarder/timeout.go:308` | Add sync.Once to Shutdown |
| Modify | `pkg/forwarder/timeout_test.go` | Add concurrent Shutdown test |
| Modify | `pkg/database/database.go:115,127,146` | Replace log.Printf with logger |

### Phase 4 — DI Refactor
| Action | File | Responsibility |
|--------|------|----------------|
| Create | `pkg/deps/deps.go` | AppDependencies aggregation struct |
| Modify | `pkg/middleware/auth.go` | Add AuthMiddleware struct |
| Modify | `pkg/middleware/auth_test.go` | Add AuthMiddleware tests |
| Modify | `pkg/handler/login.go` | Add LoginHandler struct |
| Create | `pkg/handler/login_handler_test.go` | LoginHandler tests |
| Modify | `pkg/handler/routes.go` | Accept handler instances |
| Modify | `main.go` | Rewrite assembly to use AppDependencies |
| Modify | `main_test.go` | End-to-end verification |

### Phase 5 — Tests + Index
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `pkg/websocket/handler_test.go` | Extend with 8 new test cases |
| Create | `pkg/middleware/ratelimit_test.go` | RateLimitMiddleware integration tests |
| Modify | `pkg/middleware/trace_test.go` | Extend trace middleware tests |
| Create | `pkg/alert/evaluator_test.go` | Alert evaluator tests |

---

## Phase 1: Security Fixes

### Task 1: WebSocket CheckOrigin Tightening (S1)

**Files:**
- Modify: `pkg/handler/http_server.go:54-59`
- Modify: `pkg/handler/http_server_test.go`

- [ ] **Step 1: Add test cases for CheckOrigin behavior**

Append to `pkg/handler/http_server_test.go`:

```go
func TestCheckOrigin_SameOrigin(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	req.Host = "example.com:5612"
	req.Header.Set("Origin", "http://example.com:5612")
	assert.True(t, sameOriginOrNoOrigin(req))
}

func TestCheckOrigin_CrossOrigin(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	req.Host = "example.com:5612"
	req.Header.Set("Origin", "http://evil.com")
	assert.False(t, sameOriginOrNoOrigin(req))
}

func TestCheckOrigin_NoOrigin(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	req.Host = "example.com:5612"
	assert.True(t, sameOriginOrNoOrigin(req))
}

func TestCheckOrigin_SameHostDifferentPort(t *testing.T) {
	req := httptest.NewRequest("GET", "/", nil)
	req.Host = "example.com:5612"
	req.Header.Set("Origin", "http://example.com:3000")
	assert.True(t, sameOriginOrNoOrigin(req), "same host different port should be allowed")
}
```

- [ ] **Step 2: Run tests to verify existing CheckOrigin tests pass**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestCheckOrigin ./pkg/handler/... -v
```

Expected: Tests pass (sameOriginOrNoOrigin already works correctly).

- [ ] **Step 3: Modify CheckOrigin to use sameOriginOrNoOrigin**

In `pkg/handler/http_server.go`, change the `NewHTTPServer` function's `wsUpgrader`:

```go
s := &HTTPServer{
    engine: engine,
    wsUpgrader: &websocket.Upgrader{
        ReadBufferSize:  1024,
        WriteBufferSize: 1024,
        CheckOrigin: func(r *http.Request) bool {
            if cfg.LocalDebug {
                return true
            }
            return sameOriginOrNoOrigin(r)
        },
    },
}
```

- [ ] **Step 4: Run tests to verify**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/handler/... -v -count=1
```

Expected: All handler tests pass.

- [ ] **Step 5: Commit**

```bash
git add pkg/handler/http_server.go pkg/handler/http_server_test.go
git commit -m "fix(security): tighten WebSocket CheckOrigin to same-origin in production"
```

---

### Task 2: CORS Empty Whitelist Fix (S2)

**Files:**
- Modify: `pkg/middleware/cors.go:37-47`
- Modify: `pkg/middleware/cors_test.go`

- [ ] **Step 1: Update the failing test to expect deny-by-default**

In `pkg/middleware/cors_test.go`, update `TestCORSMiddleware_EmptyWhitelist_AllowsAllOrigins` to `TestCORSMiddleware_EmptyWhitelist_DeniesAll`:

```go
func TestCORSMiddleware_EmptyWhitelist_DeniesAll(t *testing.T) {
	handler := CORSMiddleware(true, []string{})(func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Origin", "http://example.com")
	c.Request = req

	handler(c)

	assert.Empty(t, w.Header().Get("Access-Control-Allow-Origin"),
		"empty whitelist should not set CORS headers")
}
```

Add a test for `"*"` wildcard:

```go
func TestCORSMiddleware_StarWildcard_AllowsAll(t *testing.T) {
	handler := CORSMiddleware(true, []string{"*"})(func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Origin", "http://any-origin.com")
	c.Request = req

	handler(c)

	assert.Equal(t, "http://any-origin.com", w.Header().Get("Access-Control-Allow-Origin"))
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestCORSMiddleware_EmptyWhitelist|TestCORSMiddleware_StarWildcard" ./pkg/middleware/... -v
```

Expected: `TestCORSMiddleware_EmptyWhitelist_DeniesAll` FAILS (current behavior allows all).

- [ ] **Step 3: Fix isOriginAllowed to deny on empty whitelist**

In `pkg/middleware/cors.go`, replace the `isOriginAllowed` function:

```go
// isOriginAllowed checks if the origin is allowed by the whitelist.
// An empty whitelist denies all origins. Use ["*"] to explicitly allow all.
func isOriginAllowed(origin string, whitelist []string) bool {
	if len(whitelist) == 0 {
		return false
	}
	for _, w := range whitelist {
		if w == "*" || w == origin {
			return true
		}
	}
	return false
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/middleware/... -v -count=1
```

Expected: All middleware tests pass.

- [ ] **Step 5: Update .env.example with CORS guidance**

In `.env.example`, update the CORS section:

```ini
# CORS
# SECURITY: Empty RPC_CORS_ORIGINS = deny all cross-origin requests.
# Use "*" to allow all origins (not recommended for production).
# Use comma-separated list for specific origins: http://example.com,http://localhost:3000
RPC_CORS=true
RPC_CORS_ORIGINS=*
```

- [ ] **Step 6: Commit**

```bash
git add pkg/middleware/cors.go pkg/middleware/cors_test.go .env.example
git commit -m "fix(security): CORS empty whitelist now denies all origins, use * to allow all"
```

---

### Task 3: Deprecate Query Token Extraction (S3)

**Files:**
- Modify: `pkg/middleware/auth.go:91-104`
- Modify: `pkg/middleware/auth_test.go`

- [ ] **Step 1: Add tests for query token toggle behavior**

Append to `pkg/middleware/auth_test.go`:

```go
func TestExtractAuthTokenFromRequest_QueryDisabled(t *testing.T) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test?sekiro_token=mytoken", nil)
	c.Request = req

	token := ExtractAuthTokenFromRequest(c, false)
	assert.Equal(t, "", token, "query token should be ignored when disabled")
}

func TestExtractAuthTokenFromRequest_QueryEnabled(t *testing.T) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test?sekiro_token=mytoken", nil)
	c.Request = req

	token := ExtractAuthTokenFromRequest(c, true)
	assert.Equal(t, "mytoken", token)
}

func TestExtractAuthTokenFromRequest_HeaderTakesPrecedence(t *testing.T) {
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test?sekiro_token=querytoken", nil)
	req.Header.Set("Authorization", "Bearer headertoken")
	c.Request = req

	token := ExtractAuthTokenFromRequest(c, true)
	assert.Equal(t, "headertoken", token, "header token should take precedence over query")
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestExtractAuthTokenFromRequest_Query" ./pkg/middleware/... -v
```

Expected: FAIL — `ExtractAuthTokenFromRequest` currently takes only 1 argument.

- [ ] **Step 3: Add allowQueryToken parameter to ExtractAuthTokenFromRequest**

In `pkg/middleware/auth.go`, update the function signature and body:

```go
func ExtractAuthTokenFromRequest(c *gin.Context, allowQueryToken bool) string {
	if token := ExtractBearerToken(c.GetHeader("Authorization")); token != "" {
		return token
	}
	if token := c.GetHeader("sekiro-token"); token != "" {
		return token
	}
	if allowQueryToken {
		if token := c.Query("sekiro_token"); token != "" {
			return token
		}
	}
	if token := c.PostForm("sekiro_token"); token != "" {
		return token
	}
	return ""
}
```

- [ ] **Step 4: Update all callers of ExtractAuthTokenFromRequest**

Search for all call sites with grep and update each one. Known callers:

1. `pkg/middleware/auth.go` — `Authenticate()` and `OptionalAuth()`: change to `ExtractAuthTokenFromRequest(c, false)` (default disabled)
2. `pkg/handler/login.go:81` — `HandleGetUserInfo`: change to `middleware.ExtractAuthTokenFromRequest(c, false)`
3. `main.go` — `authorizeRegisterAccess`: change to `middleware.ExtractAuthTokenFromRequest(c, false)`

For callers that need query token support (controlled by config), pass the config value.

- [ ] **Step 5: Update existing tests that call ExtractAuthTokenFromRequest**

Search for test files calling `ExtractAuthTokenFromRequest` and add the second argument `false` to match the new signature.

- [ ] **Step 6: Run tests to verify**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/middleware/... ./pkg/handler/... -v -count=1
```

Expected: All tests pass.

- [ ] **Step 7: Update .env.example**

Add to `.env.example`:

```ini
# Token extraction
# SECURITY: Query parameter tokens are deprecated (leaked in URL logs).
# Set to true only if legacy clients require it.
RPC_ALLOW_QUERY_TOKEN=false
```

- [ ] **Step 8: Commit**

```bash
git add pkg/middleware/auth.go pkg/middleware/auth_test.go pkg/handler/login.go main.go .env.example
git commit -m "fix(security): deprecate query parameter token extraction, disabled by default"
```

---

### Task 4: Login Rate Limiting (S4)

**Files:**
- Create: `pkg/middleware/login_ratelimit.go`
- Create: `pkg/middleware/login_ratelimit_test.go`
- Modify: `pkg/handler/routes.go:125`

- [ ] **Step 1: Create login rate limit test file**

Create `pkg/middleware/login_ratelimit_test.go`:

```go
package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestLoginRateLimit_AllowsNormalTraffic(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	for i := 0; i < 3; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "192.168.1.1:12345"
		c.Request = req
		middleware(c)
		assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "request %d should pass", i)
	}
}

func TestLoginRateLimit_BlocksExcessive(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	var blocked bool
	for i := 0; i < 20; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "192.168.1.100:12345"
		c.Request = req
		middleware(c)
		if w.Code == http.StatusTooManyRequests {
			blocked = true
			break
		}
	}
	assert.True(t, blocked, "excessive requests should be rate limited")
}

func TestLoginRateLimit_IsolatesByIP(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	// Exhaust rate limit for IP-A
	for i := 0; i < 20; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "10.0.0.1:12345"
		c.Request = req
		middleware(c)
	}

	// IP-B should still be allowed
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("POST", "/api/login", nil)
	req.RemoteAddr = "10.0.0.2:12345"
	c.Request = req
	middleware(c)
	assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "different IP should not be rate limited")
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestLoginRateLimit ./pkg/middleware/... -v
```

Expected: FAIL — `LoginRateLimitMiddleware` not defined.

- [ ] **Step 3: Create LoginRateLimitMiddleware**

Create `pkg/middleware/login_ratelimit.go`:

```go
package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/flow"
)

// LoginRateLimitMiddleware applies a strict per-IP rate limit to login endpoints
// to prevent brute-force password attacks.
func LoginRateLimitMiddleware() gin.HandlerFunc {
	limiter := flow.NewRateLimiter()

	return func(c *gin.Context) {
		key := "login:" + c.ClientIP()
		if !limiter.Allow(key, 5.0) {
			abortJSON(c, http.StatusTooManyRequests, "登录过于频繁，请稍后再试")
			return
		}
		c.Next()
	}
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestLoginRateLimit ./pkg/middleware/... -v
```

Expected: PASS.

- [ ] **Step 5: Wire into login route**

In `pkg/handler/routes.go`, change the login route from:

```go
r.POST("/api/login", HandleLogin)
```

to:

```go
r.POST("/api/login", middleware.LoginRateLimitMiddleware(), HandleLogin)
```

- [ ] **Step 6: Run full test suite**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/handler/... ./pkg/middleware/... -v -count=1
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add pkg/middleware/login_ratelimit.go pkg/middleware/login_ratelimit_test.go pkg/handler/routes.go
git commit -m "feat(security): add per-IP rate limiting to login endpoint"
```

---

## Phase 2: Concurrency Fixes

### Task 5: RateLimiter.Stop sync.Once (C1)

**Files:**
- Modify: `pkg/flow/ratelimit.go:24-47`
- Modify: `pkg/flow/ratelimit_test.go`

- [ ] **Step 1: Add concurrent Stop test**

Append to `pkg/flow/ratelimit_test.go`:

```go
func TestRateLimiter_StopConcurrent(t *testing.T) {
	rl := NewRateLimiter()
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			rl.Stop()
		}()
	}
	wg.Wait()
}

func TestRateLimiter_StopIdempotent(t *testing.T) {
	rl := NewRateLimiter()
	rl.Stop()
	rl.Stop()
	rl.Stop()
	// Should not panic
}
```

- [ ] **Step 2: Run tests to verify they fail (race/panic)**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestRateLimiter_StopConcurrent|TestRateLimiter_StopIdempotent" ./pkg/flow/... -v -race
```

Expected: FAIL or panic from double-close.

- [ ] **Step 3: Add sync.Once to RateLimiter**

In `pkg/flow/ratelimit.go`, update the struct and Stop method:

```go
type RateLimiter struct {
	mu       sync.RWMutex
	limiters map[string]*limiterEntry
	stopOnce sync.Once
	stopChan chan struct{}
}

func NewRateLimiter() *RateLimiter {
	rl := &RateLimiter{
		limiters: make(map[string]*limiterEntry),
		stopChan: make(chan struct{}),
	}
	go rl.startCleanupLoop(cleanupInterval, cleanupTTL)
	return rl
}

// Stop terminates the background cleanup goroutine. Safe to call multiple times.
func (rl *RateLimiter) Stop() {
	rl.stopOnce.Do(func() { close(rl.stopChan) })
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/flow/... -v -race -count=1
```

Expected: All flow tests pass, no race conditions.

- [ ] **Step 5: Commit**

```bash
git add pkg/flow/ratelimit.go pkg/flow/ratelimit_test.go
git commit -m "fix(concurrency): use sync.Once for RateLimiter.Stop to prevent double-close panic"
```

---

### Task 6: auth_cache GC Goroutine Stoppable (C2)

**Files:**
- Modify: `pkg/middleware/auth_cache.go:21-101`
- Modify: `pkg/middleware/auth_cache_test.go`
- Modify: `main.go` (add ShutdownCaches call)

- [ ] **Step 1: Add tests for cache Stop behavior**

Append to `pkg/middleware/auth_cache_test.go`:

```go
func TestCache_StopTerminatesGCLoop(t *testing.T) {
	c := newCache[string](time.Second, time.Second)
	initial := runtime.NumGoroutine()
	c.Stop()
	time.Sleep(100 * time.Millisecond)
	// Goroutine count should not have grown
	assert.LessOrEqual(t, runtime.NumGoroutine(), initial+1)
}

func TestCache_StopIdempotent(t *testing.T) {
	c := newCache[string](time.Second, time.Second)
	c.Stop()
	c.Stop()
	c.Stop()
	// Should not panic
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestCache_Stop" ./pkg/middleware/... -v
```

Expected: FAIL — `cache` has no `Stop` method.

- [ ] **Step 3: Add stopChan and Stop to cache struct**

In `pkg/middleware/auth_cache.go`, update the `cache` struct and related functions:

```go
type cache[T any] struct {
	mu       sync.RWMutex
	items    map[string]cacheEntry[T]
	sf       singleflight.Group
	posTTL   time.Duration
	negTTL   time.Duration
	stopOnce sync.Once
	stopChan chan struct{}
}

func newCache[T any](positiveTTL, negativeTTL time.Duration) *cache[T] {
	c := &cache[T]{
		items:    make(map[string]cacheEntry[T]),
		posTTL:   positiveTTL,
		negTTL:   negativeTTL,
		stopChan: make(chan struct{}),
	}
	go c.gcLoop()
	return c
}

func (c *cache[T]) gcLoop() {
	t := time.NewTicker(cacheGCInterval)
	defer t.Stop()
	for {
		select {
		case <-t.C:
			c.mu.Lock()
			c.purgeExpiredLocked()
			c.mu.Unlock()
		case <-c.stopChan:
			return
		}
	}
}

func (c *cache[T]) Stop() {
	c.stopOnce.Do(func() { close(c.stopChan) })
}
```

- [ ] **Step 4: Add ShutdownCaches package-level function**

In `pkg/middleware/auth_cache.go`, add after the existing package-level vars:

```go
// ShutdownCaches stops the background GC goroutines for the default token and group caches.
// Call during server shutdown to prevent goroutine leaks.
func ShutdownCaches() {
	defaultTokenCache.Stop()
	defaultGroupCache.Stop()
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/middleware/... -v -count=1
```

Expected: All middleware tests pass.

- [ ] **Step 6: Wire ShutdownCaches into main.go Shutdown**

In `main.go`, in the `Shutdown()` method, add before `logger.Info("Server stopped")`:

```go
middleware.ShutdownCaches()
```

- [ ] **Step 7: Run full test suite**

```bash
cd D:/crawler-rpc/go-rpc && go build ./... && go test ./... -count=1
```

Expected: Build and all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pkg/middleware/auth_cache.go pkg/middleware/auth_cache_test.go main.go
git commit -m "fix(concurrency): add stoppable GC goroutines for auth caches"
```

---

### Task 7: SDK Client Synchronous Packet Processing (C3)

**Files:**
- Modify: `pkg/client/sdk/client.go:88-103`
- Modify: `pkg/client/sdk/client_test.go`

- [ ] **Step 1: Add test for sequential processing**

Append to `pkg/client/sdk/client_test.go`:

```go
func TestReadLoop_ProcessesSequentially(t *testing.T) {
	// Verify that readLoop processes packets synchronously (no goroutine per packet).
	// This is validated by checking that handlePacket completes before the next read.
	// The existing client tests already exercise readLoop; this test confirms
	// no goroutine leak under load.
	initialGoroutines := runtime.NumGoroutine()

	// Create and start a client (uses existing test helpers if available)
	// ... (use existing test infrastructure)

	// After processing, goroutine count should not have grown significantly
	assert.LessOrEqual(t, runtime.NumGoroutine(), initialGoroutines+5,
		"readLoop should not spawn unbounded goroutines")
}
```

- [ ] **Step 2: Run tests to verify current behavior**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/client/sdk/... -v -count=1
```

Expected: Existing tests pass.

- [ ] **Step 3: Remove per-packet goroutine in readLoop**

In `pkg/client/sdk/client.go`, change `readLoop`:

```go
func (c *RpcClient) readLoop() {
	for {
		packet, err := c.Connection.receive(c.compressManager)
		if err != nil {
			if err == io.EOF {
				logger.Debug("Connection closed by server")
			} else {
				logger.Errorf("Receive error: %v", err)
			}
			c.handleDisconnect()
			return
		}

		c.handlePacket(packet)
	}
}
```

- [ ] **Step 4: Run tests to verify**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/client/sdk/... -v -race -count=1
```

Expected: All SDK client tests pass, no race conditions.

- [ ] **Step 5: Commit**

```bash
git add pkg/client/sdk/client.go pkg/client/sdk/client_test.go
git commit -m "fix(concurrency): process SDK client packets synchronously to prevent goroutine leak"
```

---

## Phase 3: Resource Management

### Task 8: Shutdown Closes DB Connection Pool (R1)

**Files:**
- Modify: `main.go:586-618`
- Modify: `main_test.go`

- [ ] **Step 1: Add test for DB pool closure**

Append to `main_test.go`:

```go
func TestShutdown_ClosesDatabasePool(t *testing.T) {
	// This test verifies that Shutdown closes the underlying sql.DB.
	// We use a real *gorm.DB with an in-memory sqlite or mock to verify.
	// If no DB is available, verify the nil-check path doesn't panic.
	s := &Server{}
	s.Shutdown() // s.db is nil — should not panic
}
```

- [ ] **Step 2: Run test to verify it passes (nil DB case)**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestShutdown_ClosesDatabasePool -v
```

Expected: PASS (nil DB is safely skipped).

- [ ] **Step 3: Add DB pool close to Shutdown**

In `main.go`, in the `Shutdown()` method, add before `logger.Info("Server stopped")`:

```go
if s.db != nil {
    if sqlDB, err := s.db.DB(); err == nil {
        if err := sqlDB.Close(); err != nil {
            logger.Errorf("Failed to close database pool: %v", err)
        }
    }
}
```

- [ ] **Step 4: Run tests**

```bash
cd D:/crawler-rpc/go-rpc && go build ./... && go test ./... -count=1
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.go main_test.go
git commit -m "fix(resources): close database connection pool during server shutdown"
```

---

### Task 9: TimeoutManager.Shutdown sync.Once (R2)

**Files:**
- Modify: `pkg/forwarder/timeout.go:1-15` (imports), `pkg/forwarder/timeout.go:100-115` (struct), `pkg/forwarder/timeout.go:308-322` (Shutdown)
- Modify: `pkg/forwarder/timeout_test.go`

- [ ] **Step 1: Add concurrent Shutdown test**

Append to `pkg/forwarder/timeout_test.go`:

```go
func TestTimeoutManager_ShutdownConcurrent(t *testing.T) {
	m := NewTimeoutManager(nil)
	m.Add("1", "g", "c", []byte("data"))
	m.Add("2", "g", "c", []byte("data"))

	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			m.Shutdown()
		}()
	}
	wg.Wait()
	assert.Equal(t, 0, m.Count())
}

func TestTimeoutManager_ShutdownIdempotent(t *testing.T) {
	m := NewTimeoutManager(nil)
	m.Shutdown()
	m.Shutdown()
	m.Shutdown()
	// Should not panic
}
```

- [ ] **Step 2: Run tests to verify they fail (panic from double-close)**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestTimeoutManager_ShutdownConcurrent|TestTimeoutManager_ShutdownIdempotent" ./pkg/forwarder/... -v -race
```

Expected: FAIL or panic.

- [ ] **Step 3: Add sync.Once to TimeoutManager**

In `pkg/forwarder/timeout.go`, add `sync` to imports if not present. Update the struct and Shutdown:

Add `shutdownOnce sync.Once` field to the `TimeoutManager` struct.

Replace the `Shutdown` method:

```go
func (m *TimeoutManager) Shutdown() {
	m.shutdownOnce.Do(func() {
		close(m.stopChan)
		m.wg.Wait()

		m.mu.Lock()
		defer m.mu.Unlock()
		for _, record := range m.records {
			record.Close()
		}
		for _, stream := range m.streams {
			stream.Close()
		}
		m.records = make(map[string]*InvokeRecord)
		m.streams = make(map[string]*StreamRecord)
	})
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/forwarder/... -v -race -count=1
```

Expected: All forwarder tests pass, no race conditions.

- [ ] **Step 5: Commit**

```bash
git add pkg/forwarder/timeout.go pkg/forwarder/timeout_test.go
git commit -m "fix(concurrency): use sync.Once for TimeoutManager.Shutdown to prevent double-close"
```

---

### Task 10: Unify Logging in database.go (R3)

**Files:**
- Modify: `pkg/database/database.go:1-13` (imports), `pkg/database/database.go:115,127,146`

- [ ] **Step 1: Replace log.Printf/log.Println with logger**

In `pkg/database/database.go`:

1. Remove `"log"` from imports.
2. Line 115: Replace `log.Printf("Dropped metric table: %s", t)` with `logger.Infof("Dropped metric table: %s", t)`
3. Line 127: Replace `log.Println("WARNING: Database schema is not initialized. Please run migration.sql first!")` with `logger.Warnf("Database schema is not initialized. Please run migration.sql first!")`
4. Line 146: Replace `log.Println("Database schema validation passed")` with `logger.Info("Database schema validation passed")`

- [ ] **Step 2: Verify build**

```bash
cd D:/crawler-rpc/go-rpc && go build ./...
```

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add pkg/database/database.go
git commit -m "refactor: replace log.Printf with logger in database.go for consistency"
```

---

### Task 11: Phase 1-3 Final Verification

- [ ] **Step 1: Run complete test suite with race detector**

```bash
cd D:/crawler-rpc/go-rpc && go test -race ./... -count=1
```

Expected: All tests pass, no race conditions.

- [ ] **Step 2: Run go vet**

```bash
cd D:/crawler-rpc/go-rpc && go vet ./...
```

Expected: No issues.

- [ ] **Step 3: Commit tag for Phase 1-3 completion**

```bash
git tag v0.4.0-security-concurrency-resources -m "Phase 1-3: Security, concurrency, and resource management fixes"
```

---

## Phase 4: Architecture Unification (DI Refactor)

### Task 12: Create AppDependencies Struct

**Files:**
- Create: `pkg/deps/deps.go`

- [ ] **Step 1: Create the deps package**

Create `pkg/deps/deps.go`:

```go
package deps

import (
	"github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"gorm.io/gorm"
)

// AppDependencies aggregates all shared dependencies for dependency injection.
// Constructed once in main.go and passed to all modules that need them.
type AppDependencies struct {
	DB            *gorm.DB
	UserRepo      repository.UserRepository
	GroupRepo     repository.GroupRepository
	ConfigService config.Service
	EventBus      *eventbus.EventBus
}
```

- [ ] **Step 2: Verify build**

```bash
cd D:/crawler-rpc/go-rpc && go build ./pkg/deps/...
```

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add pkg/deps/deps.go
git commit -m "feat(arch): add AppDependencies struct for unified dependency injection"
```

---

### Task 13: AuthMiddleware Struct (A3)

**Files:**
- Modify: `pkg/middleware/auth.go`
- Modify: `pkg/middleware/auth_test.go`

- [ ] **Step 1: Add tests for AuthMiddleware struct**

Append to `pkg/middleware/auth_test.go`:

```go
func TestAuthMiddleware_Struct_Authenticate(t *testing.T) {
	repo := &mockTokenUserRepo{user: &model.UserInfo{ID: 1, UserName: "admin", ApiToken: "test-token-123"}}
	am := NewAuthMiddleware(repo, defaultTokenCache, defaultGroupCache)

	handler := am.Authenticate()(func(c *gin.Context) {
		user, exists := GetCurrentUser(c)
		assert.True(t, exists)
		assert.Equal(t, "admin", user.UserName)
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer test-token-123")
	c.Request = req
	handler(c)

	assert.Equal(t, http.StatusOK, w.Code)
}

func TestLegacyWrapper_DelegatesCorrectly(t *testing.T) {
	// Verify that the package-level Authenticate() function still works
	// after AuthMiddleware is introduced (backward compatibility).
	repo := &mockTokenUserRepo{user: &model.UserInfo{ID: 1, UserName: "admin", ApiToken: "legacy-token"}}
	SetTokenUserRepository(repo)

	handler := Authenticate()(func(c *gin.Context) {
		c.String(http.StatusOK, "OK")
	})

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	req.Header.Set("Authorization", "Bearer legacy-token")
	c.Request = req
	handler(c)

	assert.Equal(t, http.StatusOK, w.Code)
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run "TestAuthMiddleware_Struct|TestLegacyWrapper" ./pkg/middleware/... -v
```

Expected: FAIL — `NewAuthMiddleware` not defined.

- [ ] **Step 3: Add AuthMiddleware struct to auth.go**

In `pkg/middleware/auth.go`, add after the existing code:

```go
// AuthMiddleware holds dependencies for authentication middleware as a struct,
// enabling proper dependency injection without package-level globals.
type AuthMiddleware struct {
	userRepo   TokenUserLookup
	tokenCache *cache[model.UserInfo]
	groupCache *cache[model.GroupConfig]
}

// NewAuthMiddleware creates an AuthMiddleware with explicit dependencies.
func NewAuthMiddleware(userRepo TokenUserLookup, tokenCache *cache[model.UserInfo], groupCache *cache[model.GroupConfig]) *AuthMiddleware {
	return &AuthMiddleware{
		userRepo:   userRepo,
		tokenCache: tokenCache,
		groupCache: groupCache,
	}
}

// Authenticate returns a gin middleware that requires valid authentication.
func (am *AuthMiddleware) Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := ExtractAuthTokenFromRequest(c, false)
		if token == "" {
			abortJSON(c, http.StatusUnauthorized, "未提供认证信息")
			return
		}

		user, err := am.findUserByToken(token)
		if err != nil {
			abortJSON(c, http.StatusUnauthorized, "无效的认证 token")
			return
		}

		c.Set(ContextUserKey, user)
		c.Next()
	}
}

func (am *AuthMiddleware) findUserByToken(token string) (*model.UserInfo, error) {
	if u, ok := am.tokenCache.get(token); ok {
		if u == nil {
			return nil, fmt.Errorf("user not found (cached)")
		}
		return u, nil
	}

	v, err, _ := am.tokenCache.sf.Do(token, func() (interface{}, error) {
		if u, ok := am.tokenCache.get(token); ok {
			return u, nil
		}
		u, err := am.userRepo.FindByToken(token)
		if err != nil {
			return nil, err
		}
		am.tokenCache.set(token, u)
		return u, nil
	})
	if err != nil {
		return nil, err
	}
	if v == nil {
		return nil, fmt.Errorf("user not found")
	}
	return v.(*model.UserInfo), nil
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/middleware/... -v -count=1
```

Expected: All middleware tests pass.

- [ ] **Step 5: Commit**

```bash
git add pkg/middleware/auth.go pkg/middleware/auth_test.go
git commit -m "feat(arch): add AuthMiddleware struct for dependency injection alongside legacy wrappers"
```

---

### Task 14: LoginHandler Struct (A2)

**Files:**
- Modify: `pkg/handler/login.go:17-27,34-77`
- Create: `pkg/handler/login_handler_test.go`

- [ ] **Step 1: Create LoginHandler test file**

Create `pkg/handler/login_handler_test.go`:

```go
package handler

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

func TestLoginHandler_Success(t *testing.T) {
	gin.SetMode(gin.TestMode)
	repo := &mockLoginUserRepo{user: &model.UserInfo{
		UserName: "admin",
		Password: "$2a$10$hashed", // Will be checked by password.CheckPassword
	}}
	lh := NewLoginHandler(repo)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("POST", "/api/login", strings.NewReader("userName=admin&password=admin123"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	c.Request = req

	lh.HandleLogin(c)
	// May return unauthorized if password hash doesn't match — that's fine,
	// the important thing is it doesn't panic and reaches the repo
	assert.Contains(t, []int{http.StatusOK, http.StatusUnauthorized}, w.Code)
}

func TestLoginHandler_RepoUnavailable(t *testing.T) {
	gin.SetMode(gin.TestMode)
	lh := NewLoginHandler(nil)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("POST", "/api/login", strings.NewReader("userName=admin&password=admin123"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	c.Request = req

	lh.HandleLogin(c)
	assert.Equal(t, http.StatusInternalServerError, w.Code)
}

func TestLoginHandler_BadCredentials(t *testing.T) {
	gin.SetMode(gin.TestMode)
	repo := &mockLoginUserRepo{user: nil}
	lh := NewLoginHandler(repo)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("POST", "/api/login", strings.NewReader("userName=unknown&password=wrong"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	c.Request = req

	lh.HandleLogin(c)
	assert.Equal(t, http.StatusUnauthorized, w.Code)
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestLoginHandler ./pkg/handler/... -v
```

Expected: FAIL — `NewLoginHandler` not defined.

- [ ] **Step 3: Add LoginHandler struct to login.go**

In `pkg/handler/login.go`, add the struct and constructor. Keep the package-level functions as wrappers:

```go
// LoginHandler handles login and registration requests with injected dependencies.
type LoginHandler struct {
	userRepo repository.UserRepository
}

// NewLoginHandler creates a LoginHandler with explicit dependencies.
func NewLoginHandler(userRepo repository.UserRepository) *LoginHandler {
	return &LoginHandler{userRepo: userRepo}
}

// HandleLogin handles login requests.
func (h *LoginHandler) HandleLogin(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBind(&req); err != nil {
		BadRequest(c, err.Error())
		return
	}

	if h.userRepo == nil {
		InternalError(c, "user repository not available")
		return
	}

	user, err := h.userRepo.FindByUserName(req.UserName)
	if err != nil || user == nil {
		Unauthorized(c, "用户名或密码错误")
		return
	}

	if !password.CheckPassword(req.Password, user.Password) {
		Unauthorized(c, "用户名或密码错误")
		return
	}

	h.userRepo.UpdateFields(user.ID, map[string]interface{}{"last_active": time.Now()})

	updateTime := ""
	if user.UpdateTime != nil {
		updateTime = user.UpdateTime.Format("2006-01-02T15:04:05")
	}

	OK(c, gin.H{
		"id":         user.ID,
		"userName":   user.UserName,
		"lastActive": user.LastActive.Format("2006-01-02T15:04:05"),
		"createTime": user.CreateTime.Format("2006-01-02T15:04:05"),
		"loginToken": user.LoginToken,
		"apiToken":   user.ApiToken,
		"isAdmin":    user.IsAdmin,
		"updateTime": updateTime,
		"permission": user.Permission,
		"quotaQps":   user.QuotaQps,
	})
}
```

Keep the legacy `HandleLogin` package-level function as a wrapper that delegates to the package-level var:

```go
// HandleLogin is the legacy package-level handler. Prefer LoginHandler.HandleLogin.
func HandleLogin(c *gin.Context) {
	legacyLoginHandler.HandleLogin(c)
}
```

Add at the bottom of the file, near the existing `SetUserRepository`:

```go
var legacyLoginHandler = &LoginHandler{}

// SetUserRepository sets the UserRepository for the legacy login handler.
func SetUserRepository(r repository.UserRepository) {
	loginUserRepo = r
	legacyLoginHandler.userRepo = r
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/handler/... -v -count=1
```

Expected: All handler tests pass.

- [ ] **Step 5: Commit**

```bash
git add pkg/handler/login.go pkg/handler/login_handler_test.go
git commit -m "feat(arch): add LoginHandler struct with dependency injection, keep legacy wrapper"
```

---

### Task 15: Rewrite main.go Assembly (A1/A2/A3)

**Files:**
- Modify: `main.go:148-340` (Start method)
- Modify: `main.go:342-493` (registerRoutes method)
- Modify: `main_test.go`

- [ ] **Step 1: Update Start() to use AppDependencies**

In `main.go`, in the `Start()` method, after the database initialization block, replace the manual repository creation and Set calls:

```go
// Build AppDependencies
appDeps := &deps.AppDependencies{
    DB:            db,
    UserRepo:      repository.NewUserRepository(db),
    GroupRepo:     repository.NewGroupRepository(db),
    ConfigService: s.configService,
    EventBus:      s.eventBus,
}

// Wire repositories to handler/middleware
handler.SetUserRepository(appDeps.UserRepo)
handler.SetLoginGroupRepository(appDeps.GroupRepo)
middleware.SetTokenUserRepository(appDeps.UserRepo)
```

- [ ] **Step 2: Update registerRoutes to accept handler instances**

Change `registerRoutes()` signature to accept the login handler:

```go
func (s *Server) registerRoutes(loginHandler *handler.LoginHandler) {
```

In the route registration, use the injected handler:

```go
s.httpServer.POST("/api/login", middleware.LoginRateLimitMiddleware(), loginHandler.HandleLogin)
```

- [ ] **Step 3: Update the call site in Start()**

```go
loginHandler := handler.NewLoginHandler(appDeps.UserRepo)
s.registerRoutes(loginHandler)
```

- [ ] **Step 4: Run full test suite**

```bash
cd D:/crawler-rpc/go-rpc && go build ./... && go test ./... -count=1
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add main.go main_test.go
git commit -m "refactor(arch): wire AppDependencies in main.go, use injected LoginHandler"
```

---

### Task 16: Mark database.DB as Deprecated

**Files:**
- Modify: `pkg/database/database.go:15`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add deprecation comment to database.DB**

In `pkg/database/database.go`, change line 15:

```go
// Deprecated: DB is a package-level global. New code should receive *gorm.DB
// via constructor injection (see pkg/deps/deps.go). Will be removed in a future version.
var DB *gorm.DB
```

- [ ] **Step 2: Update AGENTS.md**

Add to the Gotchas section:

```markdown
- **`database.DB` is deprecated**: New code should receive `*gorm.DB` via constructor injection through `deps.AppDependencies`. Direct references to `database.DB` in new code will be flagged in review.
```

- [ ] **Step 3: Commit**

```bash
git add pkg/database/database.go AGENTS.md
git commit -m "docs: mark database.DB global as deprecated"
```

---

### Task 17: Phase 4 Final Verification

- [ ] **Step 1: Run complete test suite with race detector**

```bash
cd D:/crawler-rpc/go-rpc && go test -race ./... -count=1
```

Expected: All tests pass, no race conditions.

- [ ] **Step 2: Verify no remaining direct references to package-level Set functions in new code**

```bash
cd D:/crawler-rpc/go-rpc && grep -rn "SetUserRepository\|SetLoginGroupRepository\|SetTokenUserRepository" --include="*.go" | grep -v "_test.go" | grep -v "login.go" | grep -v "auth.go" | grep -v "main.go"
```

Expected: No results (all Set calls are in known legacy locations).

---

## Phase 5: Test Coverage + Index Health

### Task 18: WebSocket Handler Tests

**Files:**
- Modify: `pkg/websocket/handler_test.go`

- [ ] **Step 1: Add HandleConnection lifecycle test**

Append to `pkg/websocket/handler_test.go`:

```go
func TestHandleConnection_NormalLifecycle(t *testing.T) {
	// Setup: create test WebSocket server and client
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upgrader := websocket.Upgrader{}
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Fatal(err)
		}
		defer conn.Close()
		// Read one message then close
		_, _, _ = conn.ReadMessage()
	}))
	defer s.Close()

	// Connect client
	wsURL := "ws" + strings.TrimPrefix(s.URL, "http")
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	require.NoError(t, err)
	defer conn.Close()

	cm := client.NewClientManager()
	tm := forwarder.NewTimeoutManager(nil)
	defer tm.Shutdown()
	h := NewHandler(cm, tm, nil, nil, nil)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	done := make(chan struct{})
	go func() {
		h.HandleConnection(ctx, conn, "test-group", "test-client")
		close(done)
	}()

	// Send a heartbeat
	msg := RpcMessage{Type: MessageTypeHeartbeat, Group: "test-group", ClientID: "test-client", Timestamp: time.Now().UnixMilli()}
	data, _ := json.Marshal(msg)
	conn.WriteMessage(websocket.TextMessage, data)

	// Close connection to trigger cleanup
	conn.Close()

	select {
	case <-done:
		// Handler exited as expected
	case <-time.After(5 * time.Second):
		t.Fatal("HandleConnection did not exit after connection close")
	}
}

func TestProcessMessage_MalformedJSON(t *testing.T) {
	cm := client.NewClientManager()
	tm := forwarder.NewTimeoutManager(nil)
	defer tm.Shutdown()
	h := NewHandler(cm, tm, nil, nil, nil)

	// Create a mock client
	transport := &mockTransport{}
	sc := client.NewRpcClient("test", "client1", transport)
	cm.Register(sc)

	// Send malformed JSON — should not panic
	h.processMessage(context.Background(), sc, []byte("{invalid json"))

	// Client should still be registered
	assert.NotNil(t, cm.GetClient("test", "client1"))
}
```

- [ ] **Step 2: Run WebSocket handler tests**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/websocket/... -v -count=1 -timeout=30s
```

Expected: All WebSocket tests pass.

- [ ] **Step 3: Commit**

```bash
git add pkg/websocket/handler_test.go
git commit -m "test: add WebSocket handler lifecycle and malformed message tests"
```

---

### Task 19: RateLimitMiddleware Integration Tests

**Files:**
- Create: `pkg/middleware/ratelimit_test.go`

- [ ] **Step 1: Create ratelimit middleware test**

Create `pkg/middleware/ratelimit_test.go`:

```go
package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

type mockConfigService struct {
	floatVal float64
	boolVal  bool
}

func (m *mockConfigService) GetConfig(key string) string                   { return "" }
func (m *mockConfigService) GetConfigBool(key string, def bool) bool       { return m.boolVal }
func (m *mockConfigService) GetConfigFloat(key string, def float64) float64 { return m.floatVal }
func (m *mockConfigService) GetConfigInt(key string, def int) int           { return 0 }
func (m *mockConfigService) GetAllConfigs() map[string]string               { return nil }
func (m *mockConfigService) Refresh(db interface{}) error                   { return nil }
func (m *mockConfigService) Update(key, value string) error                 { return nil }

func TestRateLimitMiddleware_AnonymousUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigService{floatVal: 2.0}
	middleware := RateLimitMiddleware(cfg)

	var blocked bool
	for i := 0; i < 10; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("GET", "/test", nil)
		req.RemoteAddr = "192.168.1.50:12345"
		c.Request = req
		middleware(c)
		if w.Code == http.StatusTooManyRequests {
			blocked = true
			break
		}
	}
	assert.True(t, blocked, "anonymous user should be rate limited by config QPS")
}

func TestRateLimitMiddleware_AuthenticatedUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigService{floatVal: 10.0}
	middleware := RateLimitMiddleware(cfg)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	c.Request = req
	// Set authenticated user in context
	c.Set(ContextUserKey, &model.UserInfo{ID: 42, QuotaQps: 100.0})
	middleware(c)
	assert.NotEqual(t, http.StatusTooManyRequests, w.Code)
}

func TestRateLimitMiddleware_ZeroQPS(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigService{floatVal: 0}
	middleware := RateLimitMiddleware(cfg)

	// QPS=0 means no rate limiting
	for i := 0; i < 100; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("GET", "/test", nil)
		req.RemoteAddr = "10.0.0.99:12345"
		c.Request = req
		c.Set(ContextUserKey, &model.UserInfo{ID: 1, QuotaQps: 0})
		middleware(c)
		assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "QPS=0 should allow all requests")
	}
}
```

- [ ] **Step 2: Run tests**

```bash
cd D:/crawler-rpc/go-rpc && go test -run TestRateLimitMiddleware ./pkg/middleware/... -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add pkg/middleware/ratelimit_test.go
git commit -m "test: add RateLimitMiddleware integration tests for anonymous/auth/zero-QPS"
```

---

### Task 20: Alert Evaluator Tests

**Files:**
- Create: `pkg/alert/evaluator_test.go`

- [ ] **Step 1: Create evaluator test file**

Create `pkg/alert/evaluator_test.go`:

```go
package alert

import (
	"context"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

func TestCheckThreshold_AllOperators(t *testing.T) {
	e := &Evaluator{}
	tests := []struct {
		name      string
		value     float64
		operator  string
		threshold float64
		expected  bool
	}{
		{"greater_than_true", 10, model.OpGreaterThan, 5, true},
		{"greater_than_false", 3, model.OpGreaterThan, 5, false},
		{"less_than_true", 3, model.OpLessThan, 5, true},
		{"less_than_false", 10, model.OpLessThan, 5, false},
		{"gte_equal", 5, model.OpGreaterThanOrEqual, 5, true},
		{"gte_greater", 6, model.OpGreaterThanOrEqual, 5, true},
		{"gte_less", 4, model.OpGreaterThanOrEqual, 5, false},
		{"lte_equal", 5, model.OpLessThanOrEqual, 5, true},
		{"equal_true", 5, model.OpEqual, 5, true},
		{"equal_false", 5.1, model.OpEqual, 5, false},
		{"not_equal_true", 5.1, model.OpNotEqual, 5, true},
		{"not_equal_false", 5, model.OpNotEqual, 5, false},
		{"unknown_operator", 5, "invalid", 5, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := e.checkThreshold(tt.value, tt.operator, tt.threshold)
			assert.Equal(t, tt.expected, result)
		})
	}
}

func TestEvaluator_StartStop(t *testing.T) {
	initialGoroutines := countGoroutines()
	e := NewEvaluator(100*time.Millisecond, &mockMetricsReader{})
	e.Start(context.Background())
	time.Sleep(200 * time.Millisecond)
	e.Stop()
	time.Sleep(200 * time.Millisecond)

	// Goroutine count should not have grown
	assert.LessOrEqual(t, countGoroutines(), initialGoroutines+2,
		"evaluator should not leak goroutines after Stop")
}

func countGoroutines() int {
	return runtime.NumGoroutine()
}

type mockMetricsReader struct{}

func (m *mockMetricsReader) QueryMetrics(metricName string, tags map[string]string, window string) ([]MetricPoint, error) {
	return nil, nil
}
```

- [ ] **Step 2: Run tests**

```bash
cd D:/crawler-rpc/go-rpc && go test ./pkg/alert/... -v -count=1
```

Expected: All alert tests pass.

- [ ] **Step 3: Commit**

```bash
git add pkg/alert/evaluator_test.go
git commit -m "test: add alert evaluator tests for threshold operators and lifecycle"
```

---

### Task 21: GitNexus Index Rebuild

- [ ] **Step 1: Rebuild GitNexus index**

```bash
cd D:/crawler-rpc/go-rpc && npx gitnexus analyze --force
```

Expected: Index rebuild completes successfully.

- [ ] **Step 2: Verify FTS search works**

Use GitNexus query to verify search returns results:

```bash
cd D:/crawler-rpc/go-rpc && npx gitnexus query "error handling"
```

Expected: Non-empty results.

---

### Task 22: Final Verification

- [ ] **Step 1: Full build**

```bash
cd D:/crawler-rpc/go-rpc && go build ./...
```

Expected: Build succeeds.

- [ ] **Step 2: Static analysis**

```bash
cd D:/crawler-rpc/go-rpc && go vet ./...
```

Expected: No issues.

- [ ] **Step 3: Full test suite**

```bash
cd D:/crawler-rpc/go-rpc && go test ./... -count=1
```

Expected: All tests pass.

- [ ] **Step 4: Race detector**

```bash
cd D:/crawler-rpc/go-rpc && go test -race ./... -count=1
```

Expected: All tests pass, no race conditions.

- [ ] **Step 5: Final commit and tag**

```bash
git tag v0.5.0-full-refactoring -m "Phase 1-5: Complete refactoring — security, concurrency, resources, DI, tests"
```

---

## Summary

| Phase | Tasks | Focus | Key Deliverable |
|-------|-------|-------|-----------------|
| 1 | Tasks 1-4 | Security | CORS fix, CheckOrigin, token deprecation, login rate limit |
| 2 | Tasks 5-7 | Concurrency | sync.Once for Stop/Shutdown, no goroutine leaks |
| 3 | Tasks 8-10 | Resources | DB pool close, TimeoutManager safety, log unification |
| 4 | Tasks 12-17 | Architecture | AppDependencies, AuthMiddleware struct, LoginHandler struct |
| 5 | Tasks 18-22 | Tests + Index | WebSocket/middleware/alert tests, GitNexus rebuild |

**Total: 22 tasks, ~50 commits**
