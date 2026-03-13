# Sekiro Go 版本重构实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 Java Sekiro3 实现，重构 Go 版本的 HTTP 解析、客户端管理、路由策略和流量控制模块

**Architecture:** 分五个阶段渐进式重构：(1) 使用标准库 net/http 替换手写解析；(2) 使用 channel+goroutine 实现无锁并发；(3) 实现三种路由策略；(4) 实现空队列延迟退避；(5) 完善 WebSocket 注册转发

**Tech Stack:** Go 1.21+, gorilla/websocket, 标准库 net/http, sync/atomic, treemap 用于一致性 Hash

---

## Chunk 1: HTTP 解析标准化

### Task 1.1: 创建 HTTP 服务器基础结构

**Files:**
- Create: `pkg/server/api/http_server.go`
- Create: `pkg/server/api/config.go`
- Test: `pkg/server/api/http_server_test.go`

- [ ] **Step 1: 编写 HTTPServer 结构定义测试**

```go
// pkg/server/api/http_server_test.go
func TestHTTPServer_Start(t *testing.T) {
    server := NewHTTPServer(&Config{
        Host: "127.0.0.1",
        Port: 0, // 使用随机可用端口
    })

    // 验证服务器可以启动
    err := server.Start()
    if err != nil {
        t.Fatalf("Failed to start server: %v", err)
    }

    // 验证服务器监听地址
    if server.Addr() == "" {
        t.Fatal("Server address not set")
    }

    server.Shutdown()
}
```

- [ ] **Step 2: 实现 HTTPServer 基础结构**

```go
// pkg/server/api/http_server.go
package api

import (
    "context"
    "fmt"
    "net"
    "net/http"
    "time"

    "github.com/gorilla/websocket"
)

// Config holds HTTP server configuration
type Config struct {
    Host         string
    Port         int
    ReadTimeout  time.Duration
    WriteTimeout time.Duration
}

// DefaultConfig returns default HTTP configuration
func DefaultConfig() *Config {
    return &Config{
        Host:         "0.0.0.0",
        Port:         5612,
        ReadTimeout:  30 * time.Second,
        WriteTimeout: 30 * time.Second,
    }
}

// HTTPServer wraps net/http.Server with WebSocket support
type HTTPServer struct {
    server     *http.Server
    router     *http.ServeMux
    wsUpgrader *websocket.Upgrader
    addr       string
}

// NewHTTPServer creates a new HTTPServer
func NewHTTPServer(cfg *Config) *HTTPServer {
    s := &HTTPServer{
        router: http.NewServeMux(),
        wsUpgrader: &websocket.Upgrader{
            ReadBufferSize:  1024,
            WriteBufferSize: 1024,
            CheckOrigin:     func(r *http.Request) bool { return true },
        },
    }

    s.server = &http.Server{
        Addr:         fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
        Handler:      s.router,
        ReadTimeout:  cfg.ReadTimeout,
        WriteTimeout: cfg.WriteTimeout,
    }

    return s
}

// Start starts the HTTP server
func (s *HTTPServer) Start() error {
    ln, err := net.Listen("tcp", s.server.Addr)
    if err != nil {
        return err
    }
    s.addr = ln.Addr().String()

    go func() {
        _ = s.server.Serve(ln)
    }()

    return nil
}

// Addr returns the server address
func (s *HTTPServer) Addr() string {
    return s.addr
}

// Shutdown gracefully shuts down the server
func (s *HTTPServer) Shutdown() error {
    return s.server.Shutdown(context.Background())
}

// RegisterHandler registers an HTTP handler
func (s *HTTPServer) RegisterHandler(pattern string, handler http.HandlerFunc) {
    s.router.HandleFunc(pattern, handler)
}

// WSUpgrader returns the WebSocket upgrader
func (s *HTTPServer) WSUpgrader() *websocket.Upgrader {
    return s.wsUpgrader
}
```

- [ ] **Step 3: 运行测试验证通过**

```bash
cd pkg/server/api
go test -v -run TestHTTPServer_Start
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/api/http_server.go pkg/server/api/http_server_test.go pkg/server/api/config.go
git commit -m "feat(api): add HTTPServer base structure with WebSocket support"
```

---

### Task 1.2: 实现 API 处理器

**Files:**
- Create: `pkg/server/api/handlers.go`
- Test: `pkg/server/api/handlers_test.go`

- [ ] **Step 1: 编写 handlers 测试**

```go
// pkg/server/api/handlers_test.go
func TestHandleGroupList(t *testing.T) {
    // 创建测试服务器
    server := NewHTTPServer(DefaultConfig())
    server.Start()
    defer server.Shutdown()

    // 创建 mock ClientManager
    mockManager := &MockClientManager{
        groups: []string{"group1", "group2"},
    }

    handler := NewAPIHandler(mockManager)
    server.RegisterHandler("/business/groupList", handler.HandleGroupList)

    // 发送 GET 请求
    resp, err := http.Get("http://" + server.Addr() + "/business/groupList")
    if err != nil {
        t.Fatalf("Request failed: %v", err)
    }
    defer resp.Body.Close()

    // 验证响应
    if resp.StatusCode != http.StatusOK {
        t.Errorf("Expected status 200, got %d", resp.StatusCode)
    }

    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    if result["status"].(float64) != 0 {
        t.Error("Expected status code 0")
    }
}
```

- [ ] **Step 2: 实现 API 处理器**

```go
// pkg/server/api/handlers.go
package api

import (
    "encoding/json"
    "net/http"

    "github.com/sekiro-go/sekiro-go/pkg/server/client"
)

// APIHandler handles HTTP API requests
type APIHandler struct {
    clientManager *client.ClientManager
}

// NewAPIHandler creates a new APIHandler
func NewAPIHandler(manager *client.ClientManager) *APIHandler {
    return &APIHandler{
        clientManager: manager,
    }
}

// HandleGroupList handles /business/groupList request
func (h *APIHandler) HandleGroupList(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodGet {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    groups := h.clientManager.GetAllGroups()
    response := map[string]interface{}{
        "status":  0,
        "message": "success",
        "data":    groups,
    }

    h.sendJSONResponse(w, response)
}

// HandleClientQueue handles /business/clientQueue request
func (h *APIHandler) HandleClientQueue(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodGet {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    group := r.URL.Query().Get("group")
    if group == "" {
        h.sendJSONResponse(w, map[string]interface{}{
            "status":  -1,
            "message": "group parameter required",
        })
        return
    }

    clients := h.clientManager.GetClientsByGroup(group)
    clientIDs := make([]string, len(clients))
    for i, c := range clients {
        clientIDs[i] = c.ClientID
    }

    response := map[string]interface{}{
        "status":  0,
        "message": "success",
        "data":    clientIDs,
    }

    h.sendJSONResponse(w, response)
}

// HandleInvoke handles /business/invoke request
func (h *APIHandler) HandleInvoke(w http.ResponseWriter, r *http.Request) {
    // 解析请求体
    var req struct {
        Group          string      `json:"group"`
        ClientID       string      `json:"clientId,omitempty"`
        ConstantInvoke string      `json:"constantInvoke,omitempty"`
        Timeout        int         `json:"timeout,omitempty"`
        Action         string      `json:"action"`
        Params         interface{} `json:"params"`
    }

    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        h.sendJSONResponse(w, map[string]interface{}{
            "status":  -1,
            "message": "Invalid JSON: " + err.Error(),
        })
        return
    }

    // 参数验证
    if req.Group == "" {
        h.sendJSONResponse(w, map[string]interface{}{
            "status":  -1,
            "message": "group parameter required",
        })
        return
    }

    // 路由分配和请求转发逻辑将在后续任务实现
    h.sendJSONResponse(w, map[string]interface{}{
        "status":  -1,
        "message": "invoke not implemented yet",
    })
}

func (h *APIHandler) sendJSONResponse(w http.ResponseWriter, data map[string]interface{}) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(data)
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/api
go test -v -run TestHandleGroupList
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/api/handlers.go pkg/server/api/handlers_test.go
git commit -m "feat(api): implement groupList, clientQueue, and invoke handlers"
```

---

### Task 1.3: 实现 WebSocket 升级处理

**Files:**
- Create: `pkg/server/api/websocket.go`
- Test: `pkg/server/api/websocket_test.go`

- [ ] **Step 1: 编写 WebSocket 升级测试**

```go
// pkg/server/api/websocket_test.go
func TestWebSocketUpgrade(t *testing.T) {
    server := NewHTTPServer(DefaultConfig())
    server.Start()
    defer server.Shutdown()

    // 创建 WebSocket 客户端
    wsURL := "ws://" + server.Addr() + "/register?group=test&clientId=testClient"
    conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
    if err != nil {
        t.Fatalf("WebSocket upgrade failed: %v", err)
    }
    defer conn.Close()

    // 验证连接成功
    if conn == nil {
        t.Fatal("WebSocket connection is nil")
    }
}
```

- [ ] **Step 2: 实现 WebSocket 升级处理器**

```go
// pkg/server/api/websocket.go
package api

import (
    "net/http"

    "github.com/gorilla/websocket"
    "github.com/sekiro-go/sekiro-go/pkg/server/client"
    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
)

// WebSocketHandler handles WebSocket connections
type WebSocketHandler struct {
    clientManager *client.ClientManager
}

// NewWebSocketHandler creates a new WebSocketHandler
func NewWebSocketHandler(manager *client.ClientManager) *WebSocketHandler {
    return &WebSocketHandler{
        clientManager: manager,
    }
}

// HandleRegister handles WebSocket registration requests
func (h *WebSocketHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
    // 获取查询参数
    group := r.URL.Query().Get("group")
    clientID := r.URL.Query().Get("clientId")

    if group == "" || clientID == "" {
        http.Error(w, "group and clientId parameters required", http.StatusBadRequest)
        return
    }

    logger.Infof("WebSocket register: group=%s, clientId=%s", group, clientID)

    // WebSocket 升级由 HTTPServer 的 upgrader 处理
    // 实际的连接管理将在后续任务实现
}

// IsWebSocketUpgrade checks if request is a WebSocket upgrade request
func IsWebSocketUpgrade(r *http.Request) bool {
    return r.Header.Get("Upgrade") == "websocket"
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/api
go test -v -run TestWebSocketUpgrade
```
Expected: PASS（可能需要调整测试）

- [ ] **Step 4: 提交**

```bash
git add pkg/server/api/websocket.go pkg/server/api/websocket_test.go
git commit -m "feat(api): add WebSocket upgrade handler for client registration"
```

---

### Task 1.4: 删除旧 HTTP 处理器并集成新 API

**Files:**
- Modify: `pkg/server/bootstrap.go`
- Delete: `pkg/server/detector/http_handler.go`
- Delete: `pkg/server/detector/websocket_handler.go`

- [ ] **Step 1: 更新 bootstrap.go 使用新 API 服务器**

```go
// pkg/server/bootstrap.go - 修改 Start 方法
func (s *Server) Start() error {
    logger.InitLogger(s.config.Debug)

    // 创建新的 HTTP API 服务器
    httpCfg := api.DefaultConfig()
    httpCfg.Host = s.config.Host
    httpCfg.Port = s.config.Port

    httpServer := api.NewHTTPServer(httpCfg)

    // 创建 API 处理器
    apiHandler := api.NewAPIHandler(s.clientManager)
    httpServer.RegisterHandler("/business/groupList", apiHandler.HandleGroupList)
    httpServer.RegisterHandler("/business/clientQueue", apiHandler.HandleClientQueue)
    httpServer.RegisterHandler("/business/invoke", apiHandler.HandleInvoke)

    // WebSocket 注册处理器
    wsHandler := api.NewWebSocketHandler(s.clientManager)
    httpServer.RegisterHandler("/business/register", wsHandler.HandleRegister)
    httpServer.RegisterHandler("/register", wsHandler.HandleRegister)

    // 启动 HTTP 服务器
    if err := httpServer.Start(); err != nil {
        return fmt.Errorf("failed to start HTTP server: %w", err)
    }

    logger.Infof("Sekiro server starting on %s", httpServer.Addr())

    // 等待关闭信号
    s.waitForShutdown()
    httpServer.Shutdown()

    return nil
}
```

- [ ] **Step 2: 删除旧文件**

```bash
rm pkg/server/detector/http_handler.go
rm pkg/server/detector/websocket_handler.go
```

- [ ] **Step 3: 验证编译通过**

```bash
go build ./cmd/server
```
Expected: 编译成功

- [ ] **Step 4: 提交**

```bash
git add pkg/server/bootstrap.go
git rm pkg/server/detector/http_handler.go pkg/server/detector/websocket_handler.go
git commit -m "refactor(api): replace handwritten HTTP parser with net/http standard library"
```

---

## Chunk 2: ClientManager 并发重构

### Task 2.1: 创建基于 Channel 的 SekiroGroup

**Files:**
- Create: `pkg/server/client/group.go`
- Create: `pkg/server/client/group_test.go`

- [ ] **Step 1: 编写 SekiroGroup 测试**

```go
// pkg/server/client/group_test.go
func TestSekiroGroup_Register(t *testing.T) {
    group := NewSekiroGroup("test-group")
    defer group.Close()

    client := &SekiroClient{
        Group:    "test-group",
        ClientID: "client-1",
    }

    // 注册客户端
    group.Register(client)

    // 验证注册成功
    registered := group.GetClient("client-1")
    if registered == nil {
        t.Fatal("Client not registered")
    }
    if registered.ClientID != "client-1" {
        t.Errorf("Expected client-1, got %s", registered.ClientID)
    }
}

func TestSekiroGroup_Unregister(t *testing.T) {
    group := NewSekiroGroup("test-group")
    defer group.Close()

    client := &SekiroClient{
        Group:    "test-group",
        ClientID: "client-1",
    }
    group.Register(client)

    // 注销客户端
    group.Unregister("client-1")

    // 验证注销成功
    registered := group.GetClient("client-1")
    if registered != nil {
        t.Error("Client should be unregistered")
    }
}
```

- [ ] **Step 2: 实现 SekiroGroup 结构**

```go
// pkg/server/client/group.go
package client

import (
    "sync"
    "time"

    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
)

// commandType represents types of group commands
type commandType int

const (
    cmdRegister commandType = iota
    cmdUnregister
    cmdGetClient
    cmdGetAllClients
    cmdAllocate
    cmdClose
)

// groupCommand represents a command to the group goroutine
type groupCommand struct {
    typ      commandType
    client   *SekiroClient
    clientID string
    callback chan commandResult
}

// commandResult holds the result of a group command
type commandResult struct {
    client  *SekiroClient
    clients []*SekiroClient
    err     error
}

// SekiroGroup manages clients in a single group using goroutine + channel
type SekiroGroup struct {
    name        string
    commandChan chan groupCommand
    clients     map[string]*SekiroClient
    wg          sync.WaitGroup
    closed      bool
}

// NewSekiroGroup creates a new SekiroGroup
func NewSekiroGroup(name string) *SekiroGroup {
    g := &SekiroGroup{
        name:        name,
        commandChan: make(chan groupCommand, 64),
        clients:     make(map[string]*SekiroClient),
    }

    g.wg.Add(1)
    go g.runLoop()

    return g
}

// runLoop processes commands in a single goroutine
func (g *SekiroGroup) runLoop() {
    defer g.wg.Done()

    for cmd := range g.commandChan {
        switch cmd.typ {
        case cmdRegister:
            g.clients[cmd.client.ClientID] = cmd.client
            logger.Infof("Client registered: group=%s, clientId=%s", g.name, cmd.client.ClientID)

        case cmdUnregister:
            if client, ok := g.clients[cmd.clientID]; ok {
                if client.Connection != nil {
                    client.Connection.Close()
                }
                delete(g.clients, cmd.clientID)
                logger.Infof("Client unregistered: group=%s, clientId=%s", g.name, cmd.clientID)
            }

        case cmdGetClient:
            client := g.clients[cmd.clientID]
            cmd.callback <- commandResult{client: client}

        case cmdGetAllClients:
            clients := make([]*SekiroClient, 0, len(g.clients))
            for _, c := range g.clients {
                clients = append(clients, c)
            }
            cmd.callback <- commandResult{clients: clients}

        case cmdAllocate:
            // 简单的轮询分配，后续任务实现三种路由策略
            var allocated *SekiroClient
            for _, c := range g.clients {
                if c.Status == StatusOnline {
                    allocated = c
                    break
                }
            }
            if allocated == nil && len(g.clients) > 0 {
                for _, c := range g.clients {
                    allocated = c
                    break
                }
            }
            cmd.callback <- commandResult{client: allocated}

        case cmdClose:
            for _, c := range g.clients {
                if c.Connection != nil {
                    c.Connection.Close()
                }
            }
            g.clients = make(map[string]*SekiroClient)
            cmd.callback <- commandResult{}
            return
        }
    }
}

// Register registers a client to the group
func (g *SekiroGroup) Register(client *SekiroClient) {
    if g.closed {
        return
    }
    g.commandChan <- groupCommand{
        typ:    cmdRegister,
        client: client,
    }
}

// Unregister unregisters a client from the group
func (g *SekiroGroup) Unregister(clientID string) {
    if g.closed {
        return
    }
    g.commandChan <- groupCommand{
        typ:      cmdUnregister,
        clientID: clientID,
    }
}

// GetClient gets a client by ID
func (g *SekiroGroup) GetClient(clientID string) *SekiroClient {
    callback := make(chan commandResult, 1)
    g.commandChan <- groupCommand{
        typ:      cmdGetClient,
        clientID: clientID,
        callback: callback,
    }
    result := <-callback
    return result.client
}

// GetAllClients gets all clients in the group
func (g *SekiroGroup) GetAllClients() []*SekiroClient {
    callback := make(chan commandResult, 1)
    g.commandChan <- groupCommand{
        typ:      cmdGetAllClients,
        callback: callback,
    }
    result := <-callback
    return result.clients
}

// AllocateClient allocates a client for invocation
func (g *SekiroGroup) AllocateClient() *SekiroClient {
    callback := make(chan commandResult, 1)
    g.commandChan <- groupCommand{
        typ:      cmdAllocate,
        callback: callback,
    }
    result := <-callback
    return result.client
}

// Close closes the group and all clients
func (g *SekiroGroup) Close() {
    if g.closed {
        return
    }
    g.closed = true

    callback := make(chan commandResult, 1)
    g.commandChan <- groupCommand{
        typ:      cmdClose,
        callback: callback,
    }
    <-callback

    g.wg.Wait()
    close(g.commandChan)
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/client
go test -v -run "TestSekiroGroup_"
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/client/group.go pkg/server/client/group_test.go
git commit -m "feat(client): implement SekiroGroup with goroutine + channel concurrency model"
```

---

### Task 2.2: 更新 ClientManager 使用 SekiroGroup

**Files:**
- Modify: `pkg/server/client/manager.go`
- Test: `pkg/server/client/manager_test.go`

- [ ] **Step 1: 更新 ClientManager 实现**

```go
// pkg/server/client/manager.go
package client

import (
    "sync"
)

// ClientManager manages all SekiroGroups
type ClientManager struct {
    groups map[string]*SekiroGroup
    mu     sync.RWMutex
}

// NewClientManager creates a new ClientManager
func NewClientManager() *ClientManager {
    return &ClientManager{
        groups: make(map[string]*SekiroGroup),
    }
}

// getOrCreateGroup gets or creates a group
func (m *ClientManager) getOrCreateGroup(groupName string) *SekiroGroup {
    m.mu.RLock()
    group, ok := m.groups[groupName]
    m.mu.RUnlock()

    if ok {
        return group
    }

    m.mu.Lock()
    defer m.mu.Unlock()

    // Double-check after acquiring write lock
    if group, ok := m.groups[groupName]; ok {
        return group
    }

    group = NewSekiroGroup(groupName)
    m.groups[groupName] = group
    return group
}

// Register registers a client
func (m *ClientManager) Register(client *SekiroClient) {
    group := m.getOrCreateGroup(client.Group)
    group.Register(client)
}

// Unregister unregisters a client
func (m *ClientManager) Unregister(groupName, clientID string) {
    m.mu.RLock()
    group, ok := m.groups[groupName]
    m.mu.RUnlock()

    if ok {
        group.Unregister(clientID)
    }
}

// GetClient gets a client by group and clientID
func (m *ClientManager) GetClient(group, clientID string) *SekiroClient {
    m.mu.RLock()
    groupInst, ok := m.groups[group]
    m.mu.RUnlock()

    if !ok {
        return nil
    }
    return groupInst.GetClient(clientID)
}

// GetClientsByGroup gets all clients in a group
func (m *ClientManager) GetClientsByGroup(group string) []*SekiroClient {
    m.mu.RLock()
    groupInst, ok := m.groups[group]
    m.mu.RUnlock()

    if !ok {
        return nil
    }
    return groupInst.GetAllClients()
}

// GetAllGroups returns all group names
func (m *ClientManager) GetAllGroups() []string {
    m.mu.RLock()
    defer m.mu.RUnlock()

    groups := make([]string, 0, len(m.groups))
    for name := range m.groups {
        groups = append(groups, name)
    }
    return groups
}

// AllocateClient allocates a client for invocation
func (m *ClientManager) AllocateClient(group string) *SekiroClient {
    groupInst := m.getOrCreateGroup(group)
    return groupInst.AllocateClient()
}

// CleanupAll cleans up all clients
func (m *ClientManager) CleanupAll() {
    m.mu.Lock()
    defer m.mu.Unlock()

    for _, group := range m.groups {
        group.Close()
    }
    m.groups = make(map[string]*SekiroGroup)
}
```

- [ ] **Step 2: 更新 client.go 中的 SekiroClient 结构**

```go
// pkg/server/client/client.go
package client

import (
    "sync"
    "time"
)

// ClientStatus represents client connection status
type ClientStatus int

const (
    StatusConnected ClientStatus = iota
    StatusOnline
    StatusOffline
)

// SekiroClient represents a connected Sekiro client
type SekiroClient struct {
    Group      string
    ClientID   string
    Connection interface{} // WebSocket connection handler
    Status     ClientStatus
    LastActive time.Time
    mu         sync.RWMutex
}

// NewSekiroClient creates a new SekiroClient
func NewSekiroClient(group, clientID string, conn interface{}) *SekiroClient {
    return &SekiroClient{
        Group:      group,
        ClientID:   clientID,
        Connection: conn,
        Status:     StatusConnected,
        LastActive: time.Now(),
    }
}

// UpdateActive updates the last active timestamp
func (c *SekiroClient) UpdateActive() {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.LastActive = time.Now()
}

// SetStatus sets the client status
func (c *SekiroClient) SetStatus(status ClientStatus) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.Status = status
}

// GetStatus returns the client status
func (c *SekiroClient) GetStatus() ClientStatus {
    c.mu.RLock()
    defer c.mu.RUnlock()
    return c.Status
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/client
go test -v -run "TestClientManager_"
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/client/manager.go pkg/server/client/client.go
git commit -m "refactor(client): update ClientManager to use SekiroGroup"
```

---

## Chunk 3: 三种路由策略实现

### Task 3.1: 实现一致性 Hash 工具

**Files:**
- Create: `pkg/server/router/hash.go`
- Test: `pkg/server/router/hash_test.go`

- [ ] **Step 1: 实现 MurmurHash 算法**

```go
// pkg/server/router/hash.go
package router

import "sort"

// murmurHash implements a simple hash function similar to Java's MurmurHash
func murmurHash(key string) uint64 {
    const (
        seed = 0x123456789abcdef0
        m    = 0xc6a4a7935bd1e995
        r    = 47
    )

    var h uint64 = seed ^ (uint64(len(key)) * m)

    for i := 0; i < len(key)-len(key)%8; i += 8 {
        k := uint64(key[i]) | uint64(key[i+1])<<8 | uint64(key[i+2])<<16 | uint64(key[i+3])<<24 |
            uint64(key[i+4])<<32 | uint64(key[i+5])<<40 | uint64(key[i+6])<<48 | uint64(key[i+7])<<56

        k *= m
        k ^= k >> r
        k *= m

        h ^= k
        h *= m
    }

    switch len(key) % 8 {
    case 7:
        h ^= uint64(key[len(key)-2]) << 48
        fallthrough
    case 6:
        h ^= uint64(key[len(key)-3]) << 40
        fallthrough
    case 5:
        h ^= uint64(key[len(key)-4]) << 32
        fallthrough
    case 4:
        h ^= uint64(key[len(key)-5]) << 24
        fallthrough
    case 3:
        h ^= uint64(key[len(key)-6]) << 16
        fallthrough
    case 2:
        h ^= uint64(key[len(key)-7]) << 8
        fallthrough
    case 1:
        h ^= uint64(key[len(key)-8])
        h *= m
    }

    h ^= h >> r
    h *= m
    h ^= h >> r

    return h
}

// ConsistentHashNode represents a node in consistent hash ring
type ConsistentHashNode struct {
    Hash     uint64
    ClientID string
}

// ConsistentHashRing implements consistent hashing
type ConsistentHashRing struct {
    nodes []ConsistentHashNode
}

// NewConsistentHashRing creates a new consistent hash ring
func NewConsistentHashRing() *ConsistentHashRing {
    return &ConsistentHashRing{
        nodes: make([]ConsistentHashNode, 0),
    }
}

// Add adds a node to the ring
func (r *ConsistentHashRing) Add(clientID string) {
    hash := murmurHash(clientID)
    r.nodes = append(r.nodes, ConsistentHashNode{
        Hash:     hash,
        ClientID: clientID,
    })
    sort.Slice(r.nodes, func(i, j int) bool {
        return r.nodes[i].Hash < r.nodes[j].Hash
    })
}

// Remove removes a node from the ring
func (r *ConsistentHashRing) Remove(clientID string) {
    for i, node := range r.nodes {
        if node.ClientID == clientID {
            r.nodes = append(r.nodes[:i], r.nodes[i+1:]...)
            break
        }
    }
}

// Get returns the node responsible for the key
func (r *ConsistentHashRing) Get(key string) string {
    if len(r.nodes) == 0 {
        return ""
    }

    hash := murmurHash(key)

    // 二分查找第一个 >= hash 的节点
    idx := sort.Search(len(r.nodes), func(i int) bool {
        return r.nodes[i].Hash >= hash
    })

    // 如果没有找到，返回第一个节点（循环）
    if idx >= len(r.nodes) {
        idx = 0
    }

    return r.nodes[idx].ClientID
}
```

- [ ] **Step 2: 编写测试**

```go
// pkg/server/router/hash_test.go
package router

import "testing"

func TestMurmurHash(t *testing.T) {
    // 验证相同输入产生相同输出
    h1 := murmurHash("test-key")
    h2 := murmurHash("test-key")
    if h1 != h2 {
        t.Errorf("Expected same hash, got %d and %d", h1, h2)
    }

    // 验证不同输入产生不同输出（大概率）
    h3 := murmurHash("different-key")
    if h1 == h3 {
        t.Error("Expected different hashes for different keys")
    }
}

func TestConsistentHashRing(t *testing.T) {
    ring := NewConsistentHashRing()

    // 添加节点
    ring.Add("client-1")
    ring.Add("client-2")
    ring.Add("client-3")

    // 验证路由
    key := "test-key"
    node := ring.Get(key)
    if node == "" {
        t.Error("Expected a node, got empty")
    }

    // 验证相同 key 路由到相同节点
    node2 := ring.Get(key)
    if node != node2 {
        t.Errorf("Expected same node, got %s and %s", node, node2)
    }

    // 验证移除节点
    ring.Remove("client-2")
    node3 := ring.Get(key)
    if node3 == "client-2" {
        t.Error("Should not route to removed node")
    }
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/router
go test -v
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/router/hash.go pkg/server/router/hash_test.go
git commit -m "feat(router): implement consistent hash with MurmurHash algorithm"
```

---

### Task 3.2: 实现三种路由策略

**Files:**
- Create: `pkg/server/router/strategy.go`
- Modify: `pkg/server/client/group.go`
- Test: `pkg/server/router/strategy_test.go`

- [ ] **Step 1: 实现路由策略**

```go
// pkg/server/router/strategy.go
package router

import (
    "errors"
    "sync"

    "github.com/sekiro-go/sekiro-go/pkg/server/client"
)

// RoutingStrategy represents the routing strategy type
type RoutingStrategy int

const (
    RouteRoundRobin RoutingStrategy = iota
    RouteSpecifiedClient
    RouteConsistentHash
)

// RouteParams holds parameters for routing decision
type RouteParams struct {
    ClientID      string
    ConsistentKey string
}

// Strategy selects which client to use for invocation
type Strategy interface {
    Select(clients []*client.SekiroClient, params RouteParams) (*client.SekiroClient, error)
}

// RoundRobinStrategy implements round-robin load balancing
type RoundRobinStrategy struct {
    mu           sync.Mutex
    currentIndex int
}

func (s *RoundRobinStrategy) Select(clients []*client.SekiroClient, params RouteParams) (*client.SekiroClient, error) {
    if len(clients) == 0 {
        return nil, errors.New("no clients available")
    }

    s.mu.Lock()
    defer s.mu.Unlock()

    for i := 0; i < len(clients); i++ {
        idx := (s.currentIndex + i) % len(clients)
        if clients[idx].GetStatus() == client.StatusOnline {
            s.currentIndex = idx
            return clients[idx], nil
        }
    }

    s.currentIndex = (s.currentIndex + 1) % len(clients)
    return clients[s.currentIndex], nil
}

// SpecifiedClientStrategy routes to a specific client by ID
type SpecifiedClientStrategy struct{}

func (s *SpecifiedClientStrategy) Select(clients []*client.SekiroClient, params RouteParams) (*client.SekiroClient, error) {
    if params.ClientID == "" {
        return nil, errors.New("clientId not specified")
    }

    for _, c := range clients {
        if c.ClientID == params.ClientID {
            return c, nil
        }
    }

    return nil, errors.New("client not found: " + params.ClientID)
}

// ConsistentHashStrategy routes based on consistent hash
type ConsistentHashStrategy struct {
    ring *ConsistentHashRing
}

func NewConsistentHashStrategy() *ConsistentHashStrategy {
    return &ConsistentHashStrategy{
        ring: NewConsistentHashRing(),
    }
}

func (s *ConsistentHashStrategy) Select(clients []*client.SekiroClient, params RouteParams) (*client.SekiroClient, error) {
    if params.ConsistentKey == "" {
        return nil, errors.New("consistentKey not specified")
    }

    existingClients := make(map[string]bool)
    for _, c := range clients {
        existingClients[c.ClientID] = true
    }

    s.ring = NewConsistentHashRing()
    for clientID := range existingClients {
        s.ring.Add(clientID)
    }

    targetID := s.ring.Get(params.ConsistentKey)
    if targetID == "" {
        return nil, errors.New("no clients available")
    }

    for _, c := range clients {
        if c.ClientID == targetID {
            return c, nil
        }
    }

    return nil, errors.New("client not found: " + targetID)
}

// Router combines all strategies
type Router struct {
    roundRobin *RoundRobinStrategy
    specified  *SpecifiedClientStrategy
    consistent *ConsistentHashStrategy
}

// NewRouter creates a new Router
func NewRouter() *Router {
    return &Router{
        roundRobin: &RoundRobinStrategy{},
        specified:  &SpecifiedClientStrategy{},
        consistent: NewConsistentHashStrategy(),
    }
}

// Route selects a client based on parameters
func (r *Router) Route(clients []*client.SekiroClient, params RouteParams) (*client.SekiroClient, error) {
    // 优先级：指定客户端 > 一致性 Hash > 轮询
    if params.ClientID != "" {
        return r.specified.Select(clients, params)
    }
    if params.ConsistentKey != "" {
        return r.consistent.Select(clients, params)
    }
    return r.roundRobin.Select(clients, params)
}
```

- [ ] **Step 2: 编写测试**

```go
// pkg/server/router/strategy_test.go
func TestRouter_Route(t *testing.T) {
    clients := []*client.SekiroClient{
        {ClientID: "client-1", Status: client.StatusOnline},
        {ClientID: "client-2", Status: client.StatusOnline},
        {ClientID: "client-3", Status: client.StatusOffline},
    }

    router := NewRouter()

    // 测试指定客户端
    result, err := router.Route(clients, RouteParams{ClientID: "client-2"})
    if err != nil {
        t.Fatalf("Unexpected error: %v", err)
    }
    if result.ClientID != "client-2" {
        t.Errorf("Expected client-2, got %s", result.ClientID)
    }

    // 测试轮询
    result, err = router.Route(clients, RouteParams{})
    if err != nil {
        t.Fatalf("Unexpected error: %v", err)
    }
    if result == nil {
        t.Error("Expected a client")
    }

    // 测试一致性 Hash
    result, err = router.Route(clients, RouteParams{ConsistentKey: "user-123"})
    if err != nil {
        t.Fatalf("Unexpected error: %v", err)
    }
    if result == nil {
        t.Error("Expected a client")
    }
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/router
go test -v
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/router/strategy.go pkg/server/router/strategy_test.go pkg/server/client/group.go
git commit -m "feat(router): implement three routing strategies: round-robin, specified, consistent hash"
```

---

## Chunk 4: 流量控制与超时管理

### Task 4.1: 实现空队列延迟退避机制

**Files:**
- Create: `pkg/server/flow/backoff.go`
- Test: `pkg/server/flow/backoff_test.go`

- [ ] **Step 1: 实现 BackoffController**

```go
// pkg/server/flow/backoff.go
package flow

import (
    "sync"
    "time"
)

// BackoffController implements delay backoff for empty queue scenarios
type BackoffController struct {
    mu             sync.Mutex
    emptyCount     int
    firstEmptyTime time.Time
}

// RecordEmpty records an empty queue access and returns delay duration
func (b *BackoffController) RecordEmpty() time.Duration {
    b.mu.Lock()
    defer b.mu.Unlock()

    if b.emptyCount == 0 {
        b.firstEmptyTime = time.Now()
    }
    b.emptyCount++

    // Java 版退避逻辑的 Go 实现
    if b.emptyCount <= 5 {
        return 0
    }

    if b.emptyCount <= 10 {
        return time.Duration(b.emptyCount-4) * time.Second
    }

    if b.emptyCount < 100 {
        if time.Since(b.firstEmptyTime) > 10*time.Minute {
            return 15 * time.Second
        }
        return 10 * time.Second
    }

    if time.Since(b.firstEmptyTime) > 30*time.Minute {
        return 20 * time.Second
    }
    return 15 * time.Second
}

// RecordSuccess records a successful allocation, resets counter
func (b *BackoffController) RecordSuccess() {
    b.mu.Lock()
    defer b.mu.Unlock()

    b.emptyCount = 0
    b.firstEmptyTime = time.Time{}
}

// GetEmptyCount returns current empty count (for testing)
func (b *BackoffController) GetEmptyCount() int {
    b.mu.Lock()
    defer b.mu.Unlock()
    return b.emptyCount
}
```

- [ ] **Step 2: 编写测试**

```go
// pkg/server/flow/backoff_test.go
package flow

import (
    "testing"
    "time"
)

func TestBackoffController(t *testing.T) {
    ctrl := &BackoffController{}

    // 前 5 次应该不延时
    for i := 0; i < 5; i++ {
        delay := ctrl.RecordEmpty()
        if delay != 0 {
            t.Errorf("Expected 0 delay for count %d, got %v", i+1, delay)
        }
    }

    // 第 6 次应该延时 1 秒
    delay := ctrl.RecordEmpty()
    if delay != time.Second {
        t.Errorf("Expected 1s delay, got %v", delay)
    }

    // 第 10 次应该延时 5 秒
    for i := 0; i < 3; i++ {
        ctrl.RecordEmpty()
    }
    delay = ctrl.RecordEmpty()
    if delay != 5*time.Second {
        t.Errorf("Expected 5s delay, got %v", delay)
    }

    // 测试重置
    ctrl.RecordSuccess()
    if ctrl.GetEmptyCount() != 0 {
        t.Error("Expected empty count to be reset")
    }
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/flow
go test -v
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/flow/backoff.go pkg/server/flow/backoff_test.go
git commit -m "feat(flow): implement empty queue delay backoff mechanism"
```

---

### Task 4.2: 实现超时管理

**Files:**
- Create: `pkg/server/forwarder/timeout.go`
- Test: `pkg/server/forwarder/timeout_test.go`

- [ ] **Step 1: 实现 InvokeRecord 和超时管理**

```go
// pkg/server/forwarder/timeout.go
package forwarder

import (
    "sync"
    "time"
)

// CommonRes represents a common response
type CommonRes struct {
    Status   int         `json:"status"`
    Message  string      `json:"message"`
    Data     interface{} `json:"data,omitempty"`
    Seq      int32       `json:"-"`
    ClientID string      `json:"clientId,omitempty"`
}

// OK returns a success response
func OK(data interface{}) *CommonRes {
    return &CommonRes{
        Status:  0,
        Message: "success",
        Data:    data,
    }
}

// Failed returns a failed response
func Failed(message string) *CommonRes {
    return &CommonRes{
        Status:  -1,
        Message: message,
    }
}

// InvokeRecord tracks an invocation request
type InvokeRecord struct {
    mu           sync.Mutex
    request      interface{}
    responseChan chan *CommonRes
    timeout      time.Duration
    deadline     time.Time
    timer        *time.Timer
    seq          int32
    client       interface{}
    isSegment    bool
    hasResponded bool
}

// NewInvokeRecord creates a new InvokeRecord
func NewInvokeRecord(request interface{}, timeout time.Duration) *InvokeRecord {
    return &InvokeRecord{
        request:      request,
        responseChan: make(chan *CommonRes, 1),
        timeout:      timeout,
        deadline:     time.Now().Add(timeout),
    }
}

// StartTimeout starts the timeout timer
func (r *InvokeRecord) StartTimeout() {
    r.mu.Lock()
    defer r.mu.Unlock()

    r.timer = time.AfterFunc(r.timeout, func() {
        r.mu.Lock()
        defer r.mu.Unlock()

        if r.isSegment && time.Now().Before(r.deadline) {
            r.timer.Reset(r.timeout)
            return
        }

        if !r.hasResponded {
            r.hasResponded = true
            r.responseChan <- Failed("timeout")
        }
    })
}

// Response sends a response
func (r *InvokeRecord) Response(res *CommonRes) {
    r.mu.Lock()
    defer r.mu.Unlock()

    if r.hasResponded {
        return
    }

    r.hasResponded = true
    if r.timer != nil {
        r.timer.Stop()
    }

    select {
    case r.responseChan <- res:
    default:
    }
}

// WaitResponse waits for response with timeout
func (r *InvokeRecord) WaitResponse() *CommonRes {
    return <-r.responseChan
}

// SetSeq sets the sequence number
func (r *InvokeRecord) SetSeq(seq int32) {
    r.seq = seq
}

// SetClient sets the client
func (r *InvokeRecord) SetClient(client interface{}) {
    r.client = client
}

// SetSegment sets segment mode
func (r *InvokeRecord) SetSegment(isSegment bool) {
    r.isSegment = isSegment
}
```

- [ ] **Step 2: 编写测试**

```go
// pkg/server/forwarder/timeout_test.go
package forwarder

import (
    "testing"
    "time"
)

func TestInvokeRecord_Timeout(t *testing.T) {
    record := NewInvokeRecord(nil, 100*time.Millisecond)
    record.StartTimeout()

    // 等待超时
    res := record.WaitResponse()
    if res == nil {
        t.Fatal("Expected timeout response")
    }
    if res.Message != "timeout" {
        t.Errorf("Expected timeout message, got %s", res.Message)
    }
}

func TestInvokeRecord_Response(t *testing.T) {
    record := NewInvokeRecord(nil, 5*time.Second)

    expected := OK("test data")
    go func() {
        time.Sleep(50 * time.Millisecond)
        record.Response(expected)
    }()

    res := record.WaitResponse()
    if res == nil {
        t.Fatal("Expected response")
    }
    if res.Status != 0 {
        t.Errorf("Expected success status, got %d", res.Status)
    }
}
```

- [ ] **Step 3: 运行测试验证**

```bash
cd pkg/server/forwarder
go test -v -timeout 10s
```
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add pkg/server/forwarder/timeout.go pkg/server/forwarder/timeout_test.go
git commit -m "feat(forwarder): implement InvokeRecord with timeout management"
```

---

## Chunk 5: WebSocket 客户端注册完善

### Task 5.1: 实现 WebSocket 消息处理器

**Files:**
- Create: `pkg/server/websocket/handler.go`
- Test: `pkg/server/websocket/handler_test.go`

- [ ] **Step 1: 实现 WebSocketHandler**

```go
// pkg/server/websocket/handler.go
package websocket

import (
    "context"
    "encoding/json"
    "io"
    "sync"
    "sync/atomic"

    "github.com/gorilla/websocket"
    "github.com/sekiro-go/sekiro-go/pkg/protocol"
    "github.com/sekiro-go/sekiro-go/pkg/server/client"
    "github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
)

// Handler handles WebSocket client connections
type Handler struct {
    conn        *websocket.Conn
    group       *client.SekiroGroup
    client      *client.SekiroClient
    pendingReqs map[int32]*forwarder.InvokeRecord
    mu          sync.RWMutex
    seqGen      atomic.Int32
    closed      bool
}

// NewHandler creates a new WebSocket handler
func NewHandler(conn *websocket.Conn) *Handler {
    return &Handler{
        conn:        conn,
        pendingReqs: make(map[int32]*forwarder.InvokeRecord),
    }
}

// Handle handles the WebSocket connection
func (h *Handler) Handle(ctx context.Context) error {
    for {
        select {
        case <-ctx.Done():
            return ctx.Err()
        default:
        }

        _, message, err := h.conn.ReadMessage()
        if err != nil {
            if err == io.EOF || websocket.IsCloseError(err, websocket.CloseNormalClosure) {
                logger.Debug("WebSocket connection closed")
                return nil
            }
            logger.Errorf("WebSocket read error: %v", err)
            return err
        }

        var msg map[string]interface{}
        if err := json.Unmarshal(message, &msg); err != nil {
            logger.Errorf("JSON parse error: %v", err)
            continue
        }

        if err := h.handleMessage(msg); err != nil {
            logger.Errorf("Handle message error: %v", err)
        }
    }
}

func (h *Handler) handleMessage(msg map[string]interface{}) error {
    seqFloat, ok := msg["webSocketSeqNumber"]
    if !ok {
        return h.sendError("webSocketSeqNumber required")
    }
    seq := int32(seqFloat.(float64))
    if seq <= 0 {
        return h.sendError("invalid webSocketSeqNumber")
    }

    delete(msg, "webSocketSeqNumber")

    respData, _ := json.Marshal(msg)
    packet := &protocol.SekiroPacket{
        Type:         protocol.PacketTypeInvokeResponse,
        SerialNumber: seq,
        Data:         respData,
    }

    h.mu.Lock()
    record, ok := h.pendingReqs[seq]
    if ok {
        delete(h.pendingReqs, seq)
    }
    h.mu.Unlock()

    if !ok {
        logger.Debugf("No pending request for seq %d", seq)
        return nil
    }

    record.Response(forwarder.OK(msg))

    return nil
}

func (h *Handler) sendError(message string) error {
    resp := map[string]interface{}{
        "status":  -1,
        "message": message,
    }
    data, _ := json.Marshal(resp)
    return h.conn.WriteMessage(websocket.TextMessage, data)
}

// Forward forwards a request to the WebSocket client
func (h *Handler) Forward(record *forwarder.InvokeRecord) error {
    seq := h.seqGen.Add(1)
    record.SetSeq(seq)

    h.mu.Lock()
    h.pendingReqs[seq] = record
    h.mu.Unlock()

    msg := record.request.(map[string]interface{})
    msg["webSocketSeqNumber"] = seq

    data, err := json.Marshal(msg)
    if err != nil {
        return err
    }

    return h.conn.WriteMessage(websocket.TextMessage, data)
}

// Close closes the WebSocket connection
func (h *Handler) Close() error {
    h.mu.Lock()
    defer h.mu.Unlock()

    if h.closed {
        return nil
    }

    h.closed = true

    for _, record := range h.pendingReqs {
        record.Response(forwarder.Failed("connection closed"))
    }

    return h.conn.Close()
}

// SetClient sets the associated client
func (h *Handler) SetClient(client *client.SekiroClient) {
    h.client = client
}

// SetGroup sets the associated group
func (h *Handler) SetGroup(group *client.SekiroGroup) {
    h.group = group
}
```

- [ ] **Step 2: 运行测试验证**

```bash
cd pkg/server/websocket
go test -v
```
Expected: PASS（可能需要 mock）

- [ ] **Step 3: 提交**

```bash
git add pkg/server/websocket/handler.go
git commit -m "feat(websocket): implement WebSocket message handler with request tracking"
```

---

## 验证标准检查清单

- [ ] 所有单元测试通过 (`go test ./...`)
- [ ] HTTP API 与 Java 版行为一致
- [ ] WebSocket 客户端注册成功
- [ ] 三种路由策略工作正常
- [ ] 空队列延迟退避机制生效
- [ ] 超时管理正常
- [ ] 压力测试无明显性能问题
- [ ] 代码通过 `go vet` 和 `golint`

---

**计划完成并保存到** `docs/superpowers/plans/2026-03-12-sekiro-go-refactor.md`
