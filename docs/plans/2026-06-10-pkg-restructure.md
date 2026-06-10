# pkg/ 目录结构重构实施计划

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `pkg/server/` 下的子包扁平化到 `pkg/`，修复客户端 SDK 反向依赖，合并 api/ + handlers/ 为统一 handler/ 包。

**Architecture:** 按依赖层次从底到顶逐步迁移。每步只移动一个或一组包，更新所有 import 路径和 package 声明，立即编译验证。不引入新功能，不改变业务逻辑。

**Tech Stack:** Go 1.25, GORM, Gin, gorilla/websocket

**Module path:** `github.com/mrh30000/go-rpc`

**Spec:** `docs/2026-06-10-pkg-restructure-design.md`

**Environment:** 所有 bash 命令（`find`、`sed -i`、`xargs`）需在 Git Bash 中执行。项目平台为 win32，PowerShell/CMD 不支持这些命令。

---

## Chunk 1: 基础设施层迁移（Task 1-3）

### Task 1: 提升 transport/ 到 pkg/transport/

将 `pkg/server/transport/` 提升为 `pkg/transport/`，修复所有导入路径。

**Files:**
- Move: `pkg/server/transport/*` → `pkg/transport/`
- Modify imports in: `pkg/client/client.go`, `pkg/client/invoker.go`, `pkg/client/client_test.go`, `pkg/server/client/client.go`, `pkg/server/websocket/handler.go`, `pkg/server/websocket/handler_test.go`, `pkg/server/websocket/stream_test.go`, `pkg/server/api/websocket.go`, `pkg/server/api/websocket_test.go`

- [ ] **Step 1: 创建目标目录并移动文件**

```bash
mkdir -p pkg/transport
git mv pkg/server/transport/connection.go pkg/transport/
git mv pkg/server/transport/tcp_conn.go pkg/transport/
git mv pkg/server/transport/ws_conn.go pkg/transport/
```

- [ ] **Step 2: package 声明无需修改**

`transport` 包名不变（原声明为 `package transport`），无需修改。

- [ ] **Step 3: 更新所有导入路径**

在所有引用 `pkg/server/transport` 的 `.go` 文件中执行替换：

```bash
find . -name "*.go" -exec grep -l 'pkg/server/transport' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/transport|github.com/mrh30000/go-rpc/pkg/transport|g'
```

- [ ] **Step 4: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 5: 测试验证**

```bash
go test ./pkg/transport/... ./pkg/client/... ./pkg/server/...
```

Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "refactor: promote transport to top-level package

Move pkg/server/transport to pkg/transport to fix the reverse
dependency where pkg/client (SDK) imported a server sub-package."
```

---

### Task 2: 合并根目录 utils/ 到 pkg/utils/

将根目录 `utils/`（code.go, file.go）移入 `pkg/utils/`。这两个文件当前不被任何代码导入。

**Files:**
- Move: `utils/code.go` → `pkg/utils/code.go`
- Move: `utils/file.go` → `pkg/utils/file.go`
- Delete: `utils/` directory

- [ ] **Step 1: 移动文件**

注意：根目录 `utils/` 的 package 声明是 `package utils`，与 `pkg/utils/password` 和 `pkg/utils/traceid` 不同层级，不会冲突。

```bash
git mv utils/code.go pkg/utils/code.go
git mv utils/file.go pkg/utils/file.go
rmdir utils
```

- [ ] **Step 2: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS（文件无导入者）

- [ ] **Step 3: 提交**

```bash
git add -A
git commit -m "refactor: merge root utils/ into pkg/utils/

Consolidate the two utils directories. Root utils/code.go and
utils/file.go were unused; now co-located with password/ and traceid/."
```

---

### Task 3: 移动客户端 SDK 到 pkg/client/sdk/

将原 `pkg/client/`（SDK 代码）移到 `pkg/client/sdk/`，为后续 `server/client/` 移入 `pkg/client/` 腾出空间。

**Files:**
- Move: `pkg/client/client.go` → `pkg/client/sdk/client.go`
- Move: `pkg/client/invoker.go` → `pkg/client/sdk/invoker.go`
- Move: `pkg/client/client_test.go` → `pkg/client/sdk/client_test.go`（如存在）
- Move: `pkg/client/invoker_test.go` → `pkg/client/sdk/invoker_test.go`

- [ ] **Step 1: 创建目标目录并移动文件**

```bash
mkdir -p pkg/client/sdk
git mv pkg/client/client.go pkg/client/sdk/
git mv pkg/client/invoker.go pkg/client/sdk/
git mv pkg/client/client_test.go pkg/client/sdk/ 2>/dev/null || true
git mv pkg/client/invoker_test.go pkg/client/sdk/
```

- [ ] **Step 2: 更新 package 声明**

修改移动后的文件，将 `package client` 改为 `package sdk`：

```bash
sed -i 's/^package client$/package sdk/' pkg/client/sdk/client.go
sed -i 's/^package client$/package sdk/' pkg/client/sdk/invoker.go
sed -i 's/^package client$/package sdk/' pkg/client/sdk/invoker_test.go
# 测试文件如果是 package client_test 也需要改
sed -i 's/^package client_test$/package sdk_test/' pkg/client/sdk/client_test.go 2>/dev/null || true
```

- [ ] **Step 3: 更新导入路径**

原 SDK 不被项目内任何 Go 代码导入（仅 README.md 提及），但需更新移动后文件内部的 import（如果有自引用）：

```bash
# 检查 SDK 内部是否有自引用
grep -r 'github.com/mrh30000/go-rpc/pkg/client' pkg/client/sdk/ || echo "No self-references found"
```

如果有自引用，更新为新路径 `pkg/client/sdk`。

同时更新 `pkg/client/sdk/` 内文件中对 `pkg/server/transport` 的引用（如果 Task 1 已执行，这些应该已经被更新为 `pkg/transport`）。

- [ ] **Step 4: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 5: 测试验证**

```bash
go test ./pkg/client/sdk/...
```

Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "refactor: move client SDK to pkg/client/sdk

Relocate the SDK client code to make room for the server-side
client management package (from pkg/server/client) at pkg/client."
```

---

## Chunk 2: 服务端包迁移（Task 4-6）

### Task 4: 移动 server/client/ 到 pkg/client/

将服务端的客户端管理包从 `pkg/server/client/` 移到 `pkg/client/`。

**Files:**
- Move: `pkg/server/client/client.go` → `pkg/client/client.go`
- Move: `pkg/server/client/group.go` → `pkg/client/group.go`
- Move: `pkg/server/client/manager.go` → `pkg/client/manager.go`
- Move: `pkg/server/client/*_test.go` → `pkg/client/`（如存在）
- Modify imports in: `pkg/server/router/strategy.go`, `pkg/server/router/strategy_test.go`, `pkg/server/api/handlers.go`, `pkg/server/api/handlers_test.go`, `pkg/server/api/chat_completions.go`, `pkg/server/api/chat_completions_test.go`, `pkg/server/websocket/handler.go`, `pkg/server/websocket/handler_test.go`, `pkg/server/bootstrap.go`, `pkg/server/bootstrap_test.go`

- [ ] **Step 1: 移动文件**

```bash
git mv pkg/server/client/client.go pkg/client/
git mv pkg/server/client/group.go pkg/client/
git mv pkg/server/client/manager.go pkg/client/
# 移动测试文件（如果存在）
git mv pkg/server/client/*_test.go pkg/client/ 2>/dev/null || true
```

- [ ] **Step 2: 更新导入路径**

```bash
find . -name "*.go" -exec grep -l 'pkg/server/client' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/client|github.com/mrh30000/go-rpc/pkg/client|g'
```

- [ ] **Step 3: 处理 import 别名冲突**

`bootstrap.go` 中有 `pkg/server/client` 的导入。移动后导入路径变为 `pkg/client`，不需要别名。但如果有文件同时导入 `pkg/client`（旧 SDK 路径）和 `pkg/server/client`，需要更新为 `pkg/client/sdk` 和 `pkg/client`。由于 SDK 已移到 `pkg/client/sdk`（Task 3），不应有冲突。

- [ ] **Step 4: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 5: 测试验证**

```bash
go test ./pkg/client/... ./pkg/server/...
```

Expected: ALL PASS

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "refactor: move server client management to pkg/client

Server-side RpcClient, RpcGroup, and ClientManager now live at
pkg/client alongside the SDK at pkg/client/sdk."
```

---

### Task 5: 提升 config/, flow/, forwarder/

这三个包依赖较少，属于中低层基础设施。

**Files:**
- Move: `pkg/server/config/*` → `pkg/config/`
- Move: `pkg/server/flow/*` → `pkg/flow/`
- Move: `pkg/server/forwarder/*` → `pkg/forwarder/`
- Modify imports in: `pkg/server/middleware/ratelimit.go`, `pkg/server/api/handlers.go`, `pkg/server/websocket/handler.go`, `pkg/server/bootstrap.go`

- [ ] **Step 1: 移动文件**

```bash
mkdir -p pkg/config pkg/flow pkg/forwarder
git mv pkg/server/config/service.go pkg/config/
git mv pkg/server/flow/backoff.go pkg/flow/
git mv pkg/server/flow/ratelimit.go pkg/flow/
git mv pkg/server/forwarder/timeout.go pkg/forwarder/
git mv pkg/server/forwarder/streamframe.go pkg/forwarder/
# 移动测试文件（如果存在）
git mv pkg/server/config/*_test.go pkg/config/ 2>/dev/null || true
git mv pkg/server/flow/*_test.go pkg/flow/ 2>/dev/null || true
git mv pkg/server/forwarder/*_test.go pkg/forwarder/ 2>/dev/null || true
```

- [ ] **Step 2: 更新导入路径**

```bash
find . -name "*.go" -exec grep -l 'pkg/server/config' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/config|github.com/mrh30000/go-rpc/pkg/config|g'
find . -name "*.go" -exec grep -l 'pkg/server/flow' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/flow|github.com/mrh30000/go-rpc/pkg/flow|g'
find . -name "*.go" -exec grep -l 'pkg/server/forwarder' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/forwarder|github.com/mrh30000/go-rpc/pkg/forwarder|g'
```

注意：`bootstrap.go` 中使用了别名 `pkgconfig "github.com/mrh30000/go-rpc/pkg/server/config"`。更新后应改为 `pkgconfig "github.com/mrh30000/go-rpc/pkg/config"`，或者直接去掉别名改为 `"github.com/mrh30000/go-rpc/pkg/config"`（因为不再与 `internal/config` 冲突时不需要别名）。检查 bootstrap.go 是否同时导入了 `internal/config`：如果是，保留别名 `pkgconfig`。

- [ ] **Step 3: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 4: 测试验证**

```bash
go test ./pkg/config/... ./pkg/flow/... ./pkg/forwarder/... ./pkg/server/...
```

Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor: promote config, flow, forwarder to top-level packages

Move pkg/server/{config,flow,forwarder} to pkg/{config,flow,forwarder}."
```

---

### Task 6: 提升 middleware/, router/, alert/, metrics/

这四个包属于中间层，依赖 Task 1-5 中已迁移的包。

**Files:**
- Move: `pkg/server/middleware/*` → `pkg/middleware/`
- Move: `pkg/server/router/*` → `pkg/router/`
- Move: `pkg/server/alert/*` → `pkg/alert/`
- Move: `pkg/server/metrics/*` → `pkg/metrics/`

- [ ] **Step 1: 移动文件**

```bash
mkdir -p pkg/middleware pkg/router pkg/alert pkg/metrics

git mv pkg/server/middleware/auth.go pkg/middleware/
git mv pkg/server/middleware/auth_cache.go pkg/middleware/
git mv pkg/server/middleware/logging.go pkg/middleware/
git mv pkg/server/middleware/trace.go pkg/middleware/
git mv pkg/server/middleware/ratelimit.go pkg/middleware/
git mv pkg/server/middleware/*_test.go pkg/middleware/ 2>/dev/null || true

git mv pkg/server/router/hash.go pkg/router/
git mv pkg/server/router/strategy.go pkg/router/
git mv pkg/server/router/*_test.go pkg/router/ 2>/dev/null || true

git mv pkg/server/alert/evaluator.go pkg/alert/
git mv pkg/server/alert/notifier.go pkg/alert/
git mv pkg/server/alert/*_test.go pkg/alert/ 2>/dev/null || true

git mv pkg/server/metrics/collector.go pkg/metrics/
git mv pkg/server/metrics/*_test.go pkg/metrics/ 2>/dev/null || true
```

- [ ] **Step 2: 更新导入路径**

```bash
find . -name "*.go" -exec grep -l 'pkg/server/middleware' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/middleware|github.com/mrh30000/go-rpc/pkg/middleware|g'
find . -name "*.go" -exec grep -l 'pkg/server/router' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/router|github.com/mrh30000/go-rpc/pkg/router|g'
find . -name "*.go" -exec grep -l 'pkg/server/alert' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/alert|github.com/mrh30000/go-rpc/pkg/alert|g'
find . -name "*.go" -exec grep -l 'pkg/server/metrics' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/metrics|github.com/mrh30000/go-rpc/pkg/metrics|g'
```

- [ ] **Step 3: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 4: 测试验证**

```bash
go test ./pkg/middleware/... ./pkg/router/... ./pkg/alert/... ./pkg/metrics/... ./pkg/server/...
```

Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor: promote middleware, router, alert, metrics to top-level

Move pkg/server/{middleware,router,alert,metrics} to
pkg/{middleware,router,alert,metrics}."
```

---

## Chunk 3: 顶层合并与清理（Task 7-10）

### Task 7: 移动 server/websocket/ 到 pkg/websocket/

**Files:**
- Move: `pkg/server/websocket/*` → `pkg/websocket/`

- [ ] **Step 1: 移动文件**

```bash
mkdir -p pkg/websocket
git mv pkg/server/websocket/handler.go pkg/websocket/
git mv pkg/server/websocket/handler_test.go pkg/websocket/ 2>/dev/null || true
git mv pkg/server/websocket/stream_test.go pkg/websocket/ 2>/dev/null || true
git mv pkg/server/websocket/handler_benchmark_test.go pkg/websocket/ 2>/dev/null || true
```

- [ ] **Step 2: 更新导入路径**

```bash
find . -name "*.go" -exec grep -l 'pkg/server/websocket' {} \; | xargs sed -i 's|github.com/mrh30000/go-rpc/pkg/server/websocket|github.com/mrh30000/go-rpc/pkg/websocket|g'
```

- [ ] **Step 3: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 4: 测试验证**

```bash
go test ./pkg/websocket/... ./pkg/server/...
```

Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor: move websocket handler to pkg/websocket

Move pkg/server/websocket to pkg/websocket."
```

---

### Task 8: 合并 api/ + handlers/ 为 pkg/handler/

这是最复杂的迁移步骤。需要将两个包的文件合并到同一个 `pkg/handler/` 包中，统一 package 声明，合并响应类型，统一路由注册。

**Files:**
- Move: `pkg/server/api/*.go` → `pkg/handler/`
- Move: `pkg/server/handlers/*.go` → `pkg/handler/`
- Rename: `api/handlers.go` → `handler/invoke.go`
- Rename: `api/chat_completions.go` → `handler/chat.go`
- Rename: `api/stream_holdback.go` → `handler/stream.go`
- Rename: `api/http_server.go` → `handler/http_server.go`（保留，提供 HTTPServer 和 Config 类型）
- Merge: `api/response.go` + `handlers/response.go` → `handler/response.go`
- Merge: `handlers/routes.go` 逻辑合并到 `handler/routes.go`

- [ ] **Step 1: 创建目标目录**

```bash
mkdir -p pkg/handler
```

- [ ] **Step 2: 移动 api/ 文件（重命名冲突文件）**

```bash
# 直接移动（无命名冲突的文件）
git mv pkg/server/api/qwen.go pkg/handler/
git mv pkg/server/api/websocket.go pkg/handler/
git mv pkg/server/api/response.go pkg/handler/response.go

# 移动并重命名
git mv pkg/server/api/handlers.go pkg/handler/invoke.go
git mv pkg/server/api/chat_completions.go pkg/handler/chat.go
git mv pkg/server/api/stream_holdback.go pkg/handler/stream.go
git mv pkg/server/api/http_server.go pkg/handler/http_server.go

# 移动测试文件
git mv pkg/server/api/handlers_test.go pkg/handler/invoke_test.go
git mv pkg/server/api/chat_completions_test.go pkg/handler/chat_test.go
git mv pkg/server/api/qwen_test.go pkg/handler/qwen_test.go
git mv pkg/server/api/websocket_test.go pkg/handler/websocket_test.go
git mv pkg/server/api/http_server_test.go pkg/handler/http_server_test.go
```

- [ ] **Step 3: 移动 handlers/ 文件**

```bash
git mv pkg/server/handlers/login.go pkg/handler/
git mv pkg/server/handlers/user.go pkg/handler/
git mv pkg/server/handlers/group.go pkg/handler/
git mv pkg/server/handlers/alert.go pkg/handler/
git mv pkg/server/handlers/metric.go pkg/handler/
git mv pkg/server/handlers/trace.go pkg/handler/
git mv pkg/server/handlers/sysconfig.go pkg/handler/
git mv pkg/server/handlers/anonymous.go pkg/handler/
git mv pkg/server/handlers/authz.go pkg/handler/
git mv pkg/server/handlers/audit.go pkg/handler/
git mv pkg/server/handlers/constants.go pkg/handler/
git mv pkg/server/handlers/register_test.go pkg/handler/login_test.go
```

- [ ] **Step 4: 统一所有移动文件的 package 声明**

```bash
# 原 api/ 文件的 package 声明从 "api" 改为 "handler"
find pkg/handler -name "*.go" -exec sed -i 's/^package api$/package handler/' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/^package api_test$/package handler_test/' {} \;

# 原 handlers/ 文件的 package 声明从 "handlers" 改为 "handler"
find pkg/handler -name "*.go" -exec sed -i 's/^package handlers$/package handler/' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/^package handlers_test$/package handler_test/' {} \;
```

- [ ] **Step 5: 合并 response.go — 函数重命名映射与替换**

原 `api/response.go` 和 `handlers/response.go` 的函数/类型需要统一重命名。以下是完整的映射表：

**原 api/response.go → 新 handler/response.go 映射：**

| 原名 | 新名 | 说明 |
|------|------|------|
| `BusinessResponse` | `RpcResponse` | 结构体重命名 |
| `BusinessExtraResponse` | `RpcExtraResponse` | 结构体重命名 |
| `BusinessSuccess(c, data)` | `RpcSuccess(c, data)` | 函数重命名 |
| `BusinessError(c, msg)` | `RpcError(c, -1, msg)` | **注意参数差异**：新签名多一个 status int 参数 |
| `BusinessServerError(c, msg)` | `RpcServerError(c, msg)` | 函数重命名 |
| `BusinessUnauthorized(c, msg)` | `RpcUnauthorized(c, msg)` | 函数重命名 |
| `BusinessForbidden(c, msg)` | `RpcForbidden(c, msg)` | 函数重命名 |

**原 handlers/response.go → 新 handler/response.go 映射：**

| 原名 | 新名 | 说明 |
|------|------|------|
| `Response` | `ApiResponse` | 结构体重命名（保留 Total 字段） |
| `Success(c, data)` | `Success(c, data)` | **保持不变** |
| `SuccessWithTotal(c, data, total)` | `SuccessWithTotal(c, data, total)` | **保持不变** |
| `Error(c, code, msg)` | `Error(c, code, msg)` | **保持不变** |
| `BadRequest(c, msg)` | `BadRequest(c, msg)` | **保持不变** |
| `Unauthorized(c, msg)` | `Unauthorized(c, msg)` | **保持不变** |
| `Forbidden(c, msg)` | `Forbidden(c, msg)` | **保持不变** |
| `NotFound(c, msg)` | `NotFound(c, msg)` | **保持不变** |
| `InternalError(c, msg)` | `InternalError(c, msg)` | **保持不变** |
| `RpcApiResponse` | `RpcResponse` | 结构体重命名（与 api 版本合并） |
| `RpcApiSuccess(c, data)` | `RpcSuccess(c, data)` | 函数重命名（与 api 版本合并） |
| `RpcApiError(c, status, msg)` | `RpcError(c, status, msg)` | 函数重命名（与 api 版本合并） |

**批量替换命令（在 handler/ 目录下执行）：**

```bash
# api 侧：Business* → Rpc*
find pkg/handler -name "*.go" -exec sed -i 's/BusinessResponse/RpcResponse/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/BusinessExtraResponse/RpcExtraResponse/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/BusinessSuccess/RpcSuccess/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/BusinessServerError/RpcServerError/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/BusinessUnauthorized/RpcUnauthorized/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/BusinessForbidden/RpcForbidden/g' {} \;

# api 侧：BusinessError 需要特殊处理（参数签名不同）
# 原：BusinessError(c, "message") → 新：RpcError(c, -1, "message")
# 手动逐一替换所有 BusinessError 调用，或使用以下 sed：
find pkg/handler -name "*.go" -exec sed -i 's/BusinessError(\([^,]*\), /RpcError(\1, -1, /g' {} \;

# handlers 侧：Response → ApiResponse（结构体名）
find pkg/handler -name "*.go" -exec sed -i 's/\bResponse{/ApiResponse{/g' {} \;
# 注意：不要替换 gin.H 或 http.Response 等其他 Response 类型
# handlers 侧的 Success/Error/BadRequest 等函数名保持不变，无需替换

# handlers 侧：RpcApi* → Rpc*
find pkg/handler -name "*.go" -exec sed -i 's/RpcApiResponse/RpcResponse/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/RpcApiSuccess/RpcSuccess/g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's/RpcApiError/RpcError/g' {} \;
```

**注意**：sed 批量替换后，必须手动检查以下文件确认无错误替换：
- `invoke.go`（原 api/handlers.go）— 大量使用 BusinessSuccess/BusinessError
- `login.go`（原 handlers/login.go）— 大量使用 RpcApiSuccess/RpcApiError
- `response.go` 本身 — 确保函数定义与新类型名一致

写入最终的 `pkg/handler/response.go`（覆盖 Step 2 中 git mv 过来的版本）：

```go
package handler

import "github.com/gin-gonic/gin"

// ApiResponse 管理后台 API 响应（用于 /api/* 管理端点）
type ApiResponse struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
	Total   int64       `json:"total,omitempty"`
}

func Success(c *gin.Context, data interface{}) {
	c.JSON(200, ApiResponse{Code: 0, Message: "success", Data: data})
}

func SuccessWithTotal(c *gin.Context, data interface{}, total int64) {
	c.JSON(200, ApiResponse{Code: 0, Message: "success", Data: data, Total: total})
}

func Error(c *gin.Context, code int, message string) {
	c.JSON(code, ApiResponse{Code: code, Message: message})
}

func BadRequest(c *gin.Context, message string)  { Error(c, 400, message) }
func Unauthorized(c *gin.Context, message string) { Error(c, 401, message) }
func Forbidden(c *gin.Context, message string)    { Error(c, 403, message) }
func NotFound(c *gin.Context, message string)     { Error(c, 404, message) }
func InternalError(c *gin.Context, message string) { Error(c, 500, message) }

// RpcResponse RPC 调用响应（用于 /rpc-api/* 和 /business/* 对外接口）
// 前端 Login.jsx 依赖 status === 0 判断成功，类型必须为 int
type RpcResponse struct {
	Status  int         `json:"status"`
	Message string      `json:"message"`
	Data    interface{} `json:"data,omitempty"`
}

func RpcSuccess(c *gin.Context, data interface{}) {
	c.JSON(200, RpcResponse{Status: 0, Message: "success", Data: data})
}

func RpcError(c *gin.Context, status int, message string) {
	c.JSON(200, RpcResponse{Status: status, Message: message})
}

func RpcServerError(c *gin.Context, message string) {
	c.JSON(500, RpcResponse{Status: -1, Message: message})
}

func RpcUnauthorized(c *gin.Context, message string) {
	c.JSON(401, RpcResponse{Status: -1, Message: message})
}

func RpcForbidden(c *gin.Context, message string) {
	c.JSON(403, RpcResponse{Status: -1, Message: message})
}

// RpcExtraResponse RPC 调用响应（带分组和客户端信息）
type RpcExtraResponse struct {
	Status   int         `json:"status"`
	Message  string      `json:"message"`
	Group    string      `json:"group,omitempty"`
	ClientID string      `json:"clientId,omitempty"`
	Data     interface{} `json:"data,omitempty"`
}
```

删除原 handlers/response.go（不移动到 handler/，因为已被统一版本覆盖）：

```bash
git rm pkg/server/handlers/response.go
```

- [ ] **Step 6: 更新 handler/ 内部所有文件的 import 路径**

原 `api/` 文件导入了 `pkg/server/client`、`pkg/server/config`、`pkg/server/forwarder` 等（这些已在 Task 4-6 中移走），以及 `pkg/server/middleware`、`pkg/server/router`、`pkg/server/websocket`。

```bash
# 这些路径应该已经在 Task 1-7 中被全局替换了
# 验证 handler/ 下没有残留的旧路径
grep -r 'pkg/server/' pkg/handler/ || echo "No old paths remaining"
```

如果有残留（因为文件是在替换之后移动的），执行：

```bash
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/middleware|github.com/mrh30000/go-rpc/pkg/middleware|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/router|github.com/mrh30000/go-rpc/pkg/router|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/websocket|github.com/mrh30000/go-rpc/pkg/websocket|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/client|github.com/mrh30000/go-rpc/pkg/client|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/config|github.com/mrh30000/go-rpc/pkg/config|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/forwarder|github.com/mrh30000/go-rpc/pkg/forwarder|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/metrics|github.com/mrh30000/go-rpc/pkg/metrics|g' {} \;
find pkg/handler -name "*.go" -exec sed -i 's|github.com/mrh30000/go-rpc/pkg/server/alert|github.com/mrh30000/go-rpc/pkg/alert|g' {} \;
```

同时，原 `handlers/` 文件中可能导入了同包内的其他文件（如 `handlers.Response`），现在同属 `handler` 包，这些内部引用需要删除（同包不需要 import）。

- [ ] **Step 7: 合并路由注册**

将 `handlers/routes.go`（`SetupWebRoutes`）和 `bootstrap.go` 中的路由注册逻辑统一到 `handler/routes.go`。

原 `handlers/routes.go` 的 `SetupWebRoutes` 函数签名保持不变，但包名从 `handlers` 改为 `handler`。

原 `bootstrap.go` 中的路由注册（`registerRoutes` 方法）将在 Task 10 中合并到 `main.go`。

- [ ] **Step 8: 编译验证**

```bash
go build ./...
```

Expected: 可能有编译错误，需要逐步修复：
- 同名符号冲突（如果 `api/` 和 `handlers/` 有同名函数/类型）
- 缺失的内部引用

逐一排查和修复编译错误，直到 BUILD SUCCESS。

- [ ] **Step 9: 测试验证**

```bash
go test ./pkg/handler/...
```

Expected: ALL PASS

- [ ] **Step 10: 提交**

```bash
git add -A
git commit -m "refactor: merge api/ and handlers/ into unified handler/ package

Consolidate pkg/server/api and pkg/server/handlers into pkg/handler.
Unify response types: ApiResponse (admin), RpcResponse (external),
RpcExtraResponse (external with group/client info)."
```

---

### Task 9: 消除重复代码

**Files:**
- Create: `pkg/model/group.go`
- Modify: `pkg/handler/constants.go`（删除 DefaultGroupActions）
- Modify: `pkg/websocket/handler.go`（删除 DefaultGroupActions，改用 model.DefaultGroupActions）
- Modify: `pkg/handler/login.go`（将 database.GetDB() 调用改为 Repository 注入）

- [ ] **Step 1: 创建 pkg/model/group.go**

```go
package model

// DefaultGroupActions 默认分组 Actions 列表
// 当设备连接到正式分组时，这些 Actions 会被自动添加到 group_actions 表中
var DefaultGroupActions = []string{"invoke", "execJs", "getHtml", "getCookie"}
```

- [ ] **Step 2: 更新 handler/constants.go 和 handler/anonymous.go**

删除 `handler/constants.go` 中的 `DefaultGroupActions` 变量定义，保留其他常量（`ClientInactiveThreshold`、`DefaultGroupQPS`、`DefaultDeviceQPS`）。

同时更新 `handler/anonymous.go` 中所有 `DefaultGroupActions` 引用为 `model.DefaultGroupActions`，并确保该文件 import 了 `model` 包。

- [ ] **Step 3: 更新 websocket/handler.go**

删除本地 `DefaultGroupActions` 定义，将引用改为 `model.DefaultGroupActions`。

- [ ] **Step 4: 更新 handler/login.go**

将 `HandleLogin`、`HandleRegister` 等独立函数中对 `database.GetDB()` 的直接调用改为通过 Repository 接口注入。具体做法：将这些函数从独立函数改为 `Deps` 结构体的方法（与 `UserHandler` 等保持一致），或添加 Repository 参数。

- [ ] **Step 5: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 6: 测试验证**

```bash
go test ./pkg/model/... ./pkg/handler/... ./pkg/websocket/...
```

Expected: ALL PASS

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "refactor: eliminate duplicate DefaultGroupActions and fix login.go DB access

Move DefaultGroupActions to pkg/model/group.go as the single source
of truth. Convert login.go standalone functions to use repository
injection instead of direct database.GetDB() calls."
```

---

### Task 10: 合并 bootstrap.go 到 main.go，删除 pkg/server/

最后一步：将 `pkg/server/bootstrap.go` 的所有逻辑合并到 `main.go`，然后删除 `pkg/server/` 目录。

**Files:**
- Merge: `pkg/server/bootstrap.go` → `main.go`
- Delete: `pkg/server/` directory

- [ ] **Step 1: 分析 bootstrap.go 的完整符号清单**

`bootstrap.go` 导出了以下符号，全部需要合并到 `main.go`：

**类型定义：**
- `Config` — 服务器配置（Port, Host, Debug, LocalDebug, ConfigPath）
- `Server` — 服务器主结构体

**构造函数：**
- `DefaultConfig()` — 默认配置
- `NewServer(config *Config)` — 创建 Server 实例

**Server 方法（全部需移入 main.go）：**
- `loadYAMLConfig()` — 加载 YAML 配置
- `applyYAMLConfig()` — 应用 YAML 配置
- `Start()` — 启动服务器（核心方法）
- `registerRoutes()` — 路由注册（最复杂的方法，引用 handler 包）
- `optionalAuthGroup()` — 创建可选认证路由组
- `newHTTPConfig()` — 创建 HTTP 配置（返回 `*handler.Config`）
- `handleRegister()` — HTTP 注册端点
- `authorizeRegisterAccess()` — 注册访问授权
- `waitForShutdown()` — 等待关闭信号
- `Shutdown()` — 优雅关闭
- `GetClientManager()` — 获取客户端管理器
- `GetMetricsCollector()` — 获取指标收集器

**包级函数：**
- `logFileOptions()` — 日志文件选项映射
- `ginCorsMiddleware()` — CORS 中间件
- `isOriginAllowed()` — 域名白名单检查
- `ginRouteReplaceMiddleware()` — 路由替换中间件
- `isAPIPath()` — API 路径检查
- `apiPathPrefixes` — API 路径前缀列表

**Config 命名注意**：`bootstrap.go` 的 `Config` 和 `handler/http_server.go` 的 `Config` 是两个不同类型。合并到 `main.go` 后：
- 保留 `Config`（服务器配置）在 `main.go` 中
- `handler/http_server.go` 的 `Config` 重命名为 `HTTPConfig`，避免歧义

```bash
# 在 handler/http_server.go 中重命名
sed -i 's/type Config struct/type HTTPConfig struct/' pkg/handler/http_server.go
sed -i 's/func DefaultConfig()/func DefaultHTTPConfig()/' pkg/handler/http_server.go
sed -i 's/\*Config/\*HTTPConfig/g' pkg/handler/http_server.go
# 更新 main.go 中的引用
sed -i 's/handler\.Config/handler.HTTPConfig/g' main.go
sed -i 's/handler\.DefaultConfig/handler.DefaultHTTPConfig/g' main.go
```

**bootstrap_test.go 处理策略**：`bootstrap_test.go` 中的测试依赖 `server.Config` 和 `server.NewServer`。合并到 `main.go` 后，由于 Go 的 `main` 包不支持外部导入，将测试改为集成测试或移到 `pkg/` 下的独立测试包。具体做法：如果测试只验证 `NewServer` 和 `Start` 的基本行为，可以保留在 `main_test.go` 中（`package main` 的测试文件可以测试 main 包内的函数）。

- [ ] **Step 2: 重写 main.go**

将 `main.go` 和 `bootstrap.go` 的内容合并。`main.go` 的新内容包含：
1. 原 `main.go` 的 flag 解析逻辑
2. 原 `bootstrap.go` 的 `Config`、`Server` 类型定义
3. 原 `bootstrap.go` 的 `NewServer`、`Start`、`Shutdown` 等方法
4. 原 `bootstrap.go` 的辅助函数
5. 所有 import 路径更新为新位置

关键 import 路径变更（在合并后的 main.go 中）：

```go
import (
    // ... stdlib imports ...
    "github.com/mrh30000/go-rpc/internal/config"
    "github.com/mrh30000/go-rpc/internal/utils/logger"
    "github.com/mrh30000/go-rpc/pkg/alert"
    "github.com/mrh30000/go-rpc/pkg/client"
    pkgconfig "github.com/mrh30000/go-rpc/pkg/config"
    "github.com/mrh30000/go-rpc/pkg/database"
    "github.com/mrh30000/go-rpc/pkg/database/repository"
    "github.com/mrh30000/go-rpc/pkg/eventbus"
    "github.com/mrh30000/go-rpc/pkg/forwarder"
    "github.com/mrh30000/go-rpc/pkg/handler"
    "github.com/mrh30000/go-rpc/pkg/metrics"
    "github.com/mrh30000/go-rpc/pkg/middleware"
    "github.com/mrh30000/go-rpc/pkg/model"
    "github.com/mrh30000/go-rpc/pkg/websocket"
    webui "github.com/mrh30000/go-rpc/web"
)
```

注意：`main.go` 中引用 `handler.Deps`、`handler.SetupWebRoutes`（原 `handlers.Deps`、`handlers.SetupWebRoutes`）和 `handler.NewHTTPServer`（原 `api.NewHTTPServer`）、`handler.NewAPIHandler`（原 `api.NewAPIHandler`）等。

- [ ] **Step 3: 更新 main.go 中对 api/handlers 的引用**

合并后，原来的 `api.HTTPServer`、`api.APIHandler`、`api.Config` 等类型变成了 `handler.HTTPServer`、`handler.APIHandler`、`handler.Config`。

原来的 `handlers.Deps`、`handlers.SetupWebRoutes` 变成了 `handler.Deps`、`handler.SetupWebRoutes`。

原来的 `handlers.HandleLogin`、`handlers.HandleRegister` 等变成了 `handler.HandleLogin`、`handler.HandleRegister`。

- [ ] **Step 4: 删除 pkg/server/ 目录**

```bash
git rm pkg/server/bootstrap.go
git rm pkg/server/bootstrap_test.go
rmdir pkg/server 2>/dev/null || true
# 如果 pkg/server 下还有残留文件，逐一清理
find pkg/server -type f 2>/dev/null
```

- [ ] **Step 5: 编译验证**

```bash
go build ./...
```

Expected: BUILD SUCCESS

- [ ] **Step 6: 全量测试**

```bash
go test ./...
```

Expected: ALL PASS

- [ ] **Step 7: 静态分析**

```bash
go vet ./...
```

Expected: NO WARNINGS

- [ ] **Step 8: 验证 pkg/server/ 已完全清除**

```bash
ls pkg/server/ 2>/dev/null && echo "ERROR: pkg/server/ still exists" || echo "OK: pkg/server/ removed"
grep -r 'pkg/server/' --include="*.go" . && echo "ERROR: old imports remain" || echo "OK: all imports updated"
```

- [ ] **Step 9: 提交**

```bash
git add -A
git commit -m "refactor: merge bootstrap into main.go and remove pkg/server/

Eliminate the pkg/server/ intermediate layer. main.go now serves as
the composition root, directly wiring all flattened pkg/ packages."
```

---

### Task 11: 最终验证与清理

- [ ] **Step 1: 全量构建**

```bash
go build ./...
```

- [ ] **Step 2: 全量测试**

```bash
go test ./...
```

- [ ] **Step 3: 静态分析**

```bash
go vet ./...
```

- [ ] **Step 4: 验证目录结构**

```bash
find pkg/ -type d | sort
```

Expected output:
```
pkg/alert
pkg/client
pkg/client/sdk
pkg/compress
pkg/config
pkg/database
pkg/database/repository
pkg/eventbus
pkg/flow
pkg/forwarder
pkg/handler
pkg/metrics
pkg/middleware
pkg/model
pkg/protocol
pkg/router
pkg/transport
pkg/utils
pkg/utils/password
pkg/utils/traceid
pkg/websocket
```

- [ ] **Step 5: 验证无旧路径残留**

```bash
grep -r 'pkg/server/' --include="*.go" . && echo "FAIL" || echo "PASS: no old imports"
```

- [ ] **Step 6: 验证依赖层次**

```bash
# 验证 transport 不导入任何 pkg/ 子包
grep 'github.com/mrh30000/go-rpc/pkg/' pkg/transport/*.go && echo "FAIL" || echo "PASS: transport is leaf"

# 验证 client/sdk 不导入服务端包
grep -E 'pkg/(client|handler|middleware|router|websocket|alert|metrics|config|flow|forwarder)' pkg/client/sdk/*.go | grep -v 'pkg/transport' | grep -v 'pkg/compress' | grep -v 'pkg/protocol' && echo "FAIL" || echo "PASS: SDK only depends on leaf packages"
```

- [ ] **Step 7: 最终提交（如有清理）**

```bash
git add -A
git status
# 如果有变更则提交
git diff --cached --quiet || git commit -m "chore: post-refactor cleanup and verification"
```
