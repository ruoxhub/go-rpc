# WebSocket 支持和完整路由转发实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 WebSocket 客户端注册支持和完整的路由转发逻辑，使 Go 版本能够与 Java 版本互操作。

**Architecture:**
- WebSocket 层使用 gorilla/websocket 处理 Upgrade 握手和帧编解码，包装为 net.Conn 接口与现有 SekiroHandler 复用
- 路由转发通过 ClientManager 管理客户端注册表，使用 serial number 跟踪异步响应
- HTTP API 处理器处理调用端请求，转发到注册的客户端并等待响应

**Tech Stack:** Go 1.21, gorilla/websocket v1.5.x, 原生 net/bufio, zap logging

---

## Chunk 1: WebSocket 基础支持

### Task 1: 添加 gorilla/websocket 依赖

**Files:**
- Modify: `go.mod`
- Modify: `go.sum` (auto-generated)

- [ ] **Step 1: 添加依赖**

在 `go.mod` 中添加：
```go
require github.com/gorilla/websocket v1.5.1
```

- [ ] **Step 2: 下载依赖**

```bash
cd d:\work\sekiro_rpc\sekiro-go
go mod tidy
```

Expected: `go.sum` 更新，包含 gorilla/websocket 依赖

- [ ] **Step 3: 验证依赖**

```bash
go build ./...
```

Expected: 编译成功

- [ ] **Step 4:  Commit**

```bash
git add go.mod go.sum
git commit -m "chore: add gorilla/websocket dependency"
```

---

### Task 2: 创建 WebSocket 连接适配层

**Files:**
- Create: `pkg/server/detector/websocket_conn.go`

- [ ] **Step 1: 编写测试**

```go
// pkg/server/detector/websocket_conn_test.go
package detector

import (
    "testing"
    "net"
    "github.com/gorilla/websocket"
)

func TestWebSocketConnImplementsNetConn(t *testing.T) {
    var conn net.Conn
    wsConn := &WebSocketConn{
        UnderlyingConn: &net.TCPConn{}, // mock
        WsConn: &websocket.Conn{},
    }
    conn = wsConn
    _ = conn // verify it implements net.Conn
}
```

- [ ] **Step 2: 实现 WebSocketConn**

```go
// pkg/server/detector/websocket_conn.go
package detector

import (
    "net"
    "time"
    "github.com/gorilla/websocket"
)

// WebSocketConn wraps a websocket.Conn to implement net.Conn interface
type WebSocketConn struct {
    UnderlyingConn net.Conn
    WsConn         *websocket.Conn
    readDeadline   time.Time
    writeDeadline  time.Time
}

// Read reads binary messages from the websocket connection
func (w *WebSocketConn) Read(b []byte) (n int, err error) {
    messageType, message, err := w.WsConn.ReadMessage()
    if err != nil {
        return 0, err
    }
    if messageType != websocket.BinaryMessage {
        return 0, websocket.ErrBadHandshake
    }
    return copy(b, message), nil
}

// Write writes binary messages to the websocket connection
func (w *WebSocketConn) Write(b []byte) (n int, err error) {
    err = w.WsConn.WriteMessage(websocket.BinaryMessage, b)
    if err != nil {
        return 0, err
    }
    return len(b), nil
}

// Close closes the websocket connection
func (w *WebSocketConn) Close() error {
    return w.WsConn.Close()
}

// LocalAddr returns the local network address
func (w *WebSocketConn) LocalAddr() net.Addr {
    return w.UnderlyingConn.LocalAddr()
}

// RemoteAddr returns the remote network address
func (w *WebSocketConn) RemoteAddr() net.Addr {
    return w.UnderlyingConn.RemoteAddr()
}

// SetDeadline sets both read and write deadlines
func (w *WebSocketConn) SetDeadline(t time.Time) error {
    w.readDeadline = t
    w.writeDeadline = t
    return w.WsConn.SetReadDeadline(t)
}

// SetReadDeadline sets the read deadline
func (w *WebSocketConn) SetReadDeadline(t time.Time) error {
    w.readDeadline = t
    return w.WsConn.SetReadDeadline(t)
}

// SetWriteDeadline sets the write deadline
func (w *WebSocketConn) SetWriteDeadline(t time.Time) error {
    w.writeDeadline = t
    return w.WsConn.SetWriteDeadline(t)
}
```

- [ ] **Step 3: 运行测试**

```bash
cd d:\work\sekiro_rpc\sekiro-go
go test ./pkg/server/detector/... -v -run TestWebSocketConnImplementsNetConn
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pkg/server/detector/websocket_conn.go pkg/server/detector/websocket_conn_test.go
git commit -m "feat: add WebSocketConn net.Conn adapter"
```

---

### Task 3: 实现 WebSocket 升级处理器

**Files:**
- Create: `pkg/server/detector/websocket_handler.go`
- Modify: `pkg/server/detector/http_handler.go`

- [ ] **Step 1: 编写 WebSocket 升级测试**

```go
// pkg/server/detector/websocket_handler_test.go
package detector

import (
    "testing"
    "net/http"
    "net/http/httptest"
)

func TestWebSocketUpgradeValidation(t *testing.T) {
    handler := NewWebSocketHandler(nil)

    // Test non-websocket request
    req := httptest.NewRequest("GET", "/register", nil)
    w := httptest.NewRecorder()
    handler.ServeHTTP(w, req)

    if w.Code != http.StatusBadRequest {
        t.Errorf("expected 400 for non-websocket request, got %d", w.Code)
    }
}
```

- [ ] **Step 2: 实现 WebSocketHandler**

```go
// pkg/server/detector/websocket_handler.go
package detector

import (
    "context"
    "net"
    "net/http"

    "github.com/gorilla/websocket"
    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
)

var upgrader = websocket.Upgrader{
    ReadBufferSize:  1024,
    WriteBufferSize: 1024,
    CheckOrigin: func(r *http.Request) bool {
        return true // Allow all origins for now
    },
}

// WebSocketHandler handles WebSocket upgrade requests
type WebSocketHandler struct {
    compressManager *compress.CompressorManager
}

// NewWebSocketHandler creates a new WebSocketHandler
func NewWebSocketHandler(compressManager *compress.CompressorManager) *WebSocketHandler {
    return &WebSocketHandler{
        compressManager: compressManager,
    }
}

// ServeHTTP handles HTTP requests and upgrades to WebSocket
func (h *WebSocketHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    // Check if this is a WebSocket upgrade request
    if !websocket.IsWebSocketUpgrade(r) {
        http.Error(w, "WebSocket upgrade required", http.StatusBadRequest)
        return
    }

    // Validate path - only /register is supported for WebSocket clients
    path := r.URL.Path
    if path != "/register" && path != "/business/register" && path != "/business-demo/register" {
        http.Error(w, "Invalid WebSocket path", http.StatusBadRequest)
        return
    }

    // Parse group and clientId from query parameters
    query := r.URL.Query()
    group := query.Get("group")
    clientID := query.Get("clientId")

    if group == "" || clientID == "" {
        http.Error(w, "group and clientId parameters required", http.StatusBadRequest)
        return
    }

    // Upgrade to WebSocket
    conn, err := upgrader.Upgrade(w, r, nil)
    if err != nil {
        logger.Errorf("WebSocket upgrade failed: %v", err)
        return
    }

    logger.Infof("WebSocket upgraded: group=%s, clientId=%s", group, clientID)

    // Handle the WebSocket connection
    go h.handleWebSocketConn(conn)
}

func (h *WebSocketHandler) handleWebSocketConn(wsConn *websocket.Conn) {
    // Get underlying connection for address info
    underlyingConn := wsConn.UnderlyingConn()

    // Wrap as WebSocketConn
    wrappedConn := &WebSocketConn{
        UnderlyingConn: underlyingConn,
        WsConn:         wsConn,
    }

    // Create SekiroHandler and handle
    sekiroHandler := newSekiroHandler(wrappedConn, h.compressManager)
    ctx := context.Background()

    if err := sekiroHandler.Handle(ctx); err != nil {
        logger.Errorf("WebSocket SekiroHandler error: %v", err)
    }
}
```

- [ ] **Step 3: 修改 HTTPHandler 集成 WebSocket 升级**

在 `http_handler.go` 中添加：
```go
// 修改 handleWebSocketUpgrade 方法
func (h *HTTPHandler) handleWebSocketUpgrade(request *HTTPRequest) error {
    logger.Debug("WebSocket upgrade request detected")

    // For now, return 501 - WebSocket will be handled by dedicated handler
    // This method will be removed once WebSocketHandler is integrated
    response := "HTTP/1.1 501 Not Implemented\r\nContent-Length: 19\r\n\r\nWebSocket not ready"
    _, err := h.conn.Write([]byte(response))
    return err
}
```

- [ ] **Step 4: 运行测试**

```bash
cd d:\work\sekiro_rpc\sekiro-go
go test ./pkg/server/detector/... -v -run TestWebSocketUpgradeValidation
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pkg/server/detector/websocket_handler.go pkg/server/detector/websocket_handler_test.go pkg/server/detector/http_handler.go
git commit -m "feat: add WebSocket upgrade handler"
```

---

### Task 4: 集成 WebSocket 到服务器启动流程

**Files:**
- Modify: `pkg/server/bootstrap.go`
- Modify: `pkg/server/detector/http_matcher.go`

- [ ] **Step 1: 修改服务器以支持 WebSocket 路由**

在 `bootstrap.go` 中，修改 `acceptConnections` 方法：
```go
func (s *Server) acceptConnections(ctx context.Context) {
    for {
        select {
        case <-ctx.Done():
            return
        default:
        }

        conn, err := s.listener.Accept()
        if err != nil {
            logger.Errorf("Accept error: %v", err)
            continue
        }

        // Create detector with WebSocket support
        detector := NewProtocolDetector(s.clientManager)

        go func(c net.Conn) {
            defer c.Close()
            if err := detector.DetectAndHandle(ctx, c); err != nil {
                logger.Errorf("Handle connection error: %v", err)
            }
        }(conn)
    }
}
```

- [ ] **Step 2: 创建 ProtocolDetector 统一入口**

```go
// pkg/server/detector/protocol_detector.go
package detector

import (
    "bufio"
    "context"
    "encoding/binary"
    "net"
    "net/http"

    "github.com/sekiro-go/sekiro-go/pkg/compress"
    "github.com/sekiro-go/sekiro-go/pkg/protocol"
    "github.com/sekiro-go/sekiro-go/pkg/server"
)

// ProtocolDetector detects and routes to appropriate protocol handler
type ProtocolDetector struct {
    clientManager   *server.ClientManager
    compressManager *compress.CompressorManager
    httpHandler     *HTTPHandler
    wsHandler       *WebSocketHandler
}

// NewProtocolDetector creates a new ProtocolDetector
func NewProtocolDetector(clientManager *server.ClientManager) *ProtocolDetector {
    return &ProtocolDetector{
        clientManager:   clientManager,
        compressManager: compress.NewCompressorManager(),
    }
}

// DetectAndHandle detects protocol and handles connection
func (d *ProtocolDetector) DetectAndHandle(ctx context.Context, conn net.Conn) error {
    // Peek at first bytes to detect protocol
    buf := make([]byte, protocol.MagicLength)
    n, err := conn.Read(buf)
    if err != nil {
        return err
    }

    // Check for WebSocket upgrade (HTTP with Upgrade header)
    if n >= 3 && string(buf[:3]) == "GET" {
        return d.handleHTTP(ctx, conn, buf[:n])
    }

    // Check for Sekiro binary protocol
    if n >= protocol.MagicLength {
        magic := int64(binary.BigEndian.Uint64(buf[:8]))
        if magic == protocol.Magic {
            return d.handleSekiro(ctx, conn, buf[:n])
        }
    }

    return nil
}

func (d *ProtocolDetector) handleHTTP(ctx context.Context, conn net.Conn, initialBuf []byte) error {
    // Create HTTP handler with buffered reader
    reader := bufio.NewReader(&bufConn{buf: initialBuf, conn: conn})

    // Read HTTP request line
    requestLine, err := reader.ReadString('\n')
    if err != nil {
        return err
    }

    // Check for WebSocket upgrade
    if containsUpgradeHeader(requestLine, reader) {
        return d.handleWebSocket(ctx, conn, reader, requestLine)
    }

    // Handle regular HTTP
    return d.handleHTTPAPI(ctx, conn, reader, requestLine)
}

func containsUpgradeHeader(requestLine string, reader *bufio.Reader) bool {
    // Read headers and check for Upgrade: websocket
    for {
        line, err := reader.ReadString('\n')
        if err != nil {
            return false
        }
        line = line[:len(line)-1] // Remove \n
        if line == "" {
            break
        }
        if len(line) >= 7 && line[:7] == "Upgrade" {
            return true
        }
    }
    return false
}

func (d *ProtocolDetector) handleSekiro(ctx context.Context, conn net.Conn, initialBuf []byte) error {
    handler := newSekiroHandler(conn, d.compressManager)
    // Need to prepend initial buffer
    // This requires modifying SekiroHandler to support buffered start
    return handler.Handle(ctx)
}

// bufConn wraps a connection with an initial buffer
type bufConn struct {
    buf  []byte
    conn net.Conn
    pos  int
}

func (b *bufConn) Read(p []byte) (n int, err error) {
    if b.pos < len(b.buf) {
        n = copy(p, b.buf[b.pos:])
        b.pos += n
        return n, nil
    }
    return b.conn.Read(p)
}

func (b *bufConn) Write(p []byte) (n int, err error) {
    return b.conn.Write(p)
}

func (b *bufConn) Close() error {
    return b.conn.Close()
}

func (b *bufConn) LocalAddr() net.Addr {
    return b.conn.LocalAddr()
}

func (b *bufConn) RemoteAddr() net.Addr {
    return b.conn.RemoteAddr()
}

func (b *bufConn) SetDeadline(t time.Time) error {
    return b.conn.SetDeadline(t)
}

func (b *bufConn) SetReadDeadline(t time.Time) error {
    return b.conn.SetReadDeadline(t)
}

func (b *bufConn) SetWriteDeadline(t time.Time) error {
    return b.conn.SetWriteDeadline(t)
}
```

- [ ] **Step 3: 修改 server 包导出 ClientManager**

确保 `ClientManager` 可以从 detector 包访问。

- [ ] **Step 4: 构建验证**

```bash
cd d:\work\sekiro_rpc\sekiro-go
go build ./...
```

Expected: 编译成功

- [ ] **Step 5: Commit**

```bash
git add pkg/server/bootstrap.go pkg/server/detector/protocol_detector.go
git commit -m "feat: integrate WebSocket into server startup"
```

---

## Chunk 2: 客户端注册和路由转发

### Task 5: 实现客户端注册处理

**Files:**
- Modify: `pkg/server/detector/sekiro_handler.go`
- Modify: `pkg/server/client_manager.go`

- [ ] **Step 1: 修改 SekiroHandler 接收 ClientManager**

```go
// sekiro_handler.go
type SekiroHandler struct {
    conn            net.Conn
    compressManager *compress.CompressorManager
    clientManager   *server.ClientManager  // Add this
    reader          *bufio.Reader
    mu              sync.Mutex
    closed          bool
}

func newSekiroHandler(conn net.Conn, compressManager *compress.CompressorManager, clientManager *server.ClientManager) *SekiroHandler {
    return &SekiroHandler{
        conn:            conn,
        compressManager: compressManager,
        clientManager:   clientManager,
        reader:          bufio.NewReader(conn),
    }
}
```

- [ ] **Step 2: 实现 handleRegister**

```go
func (h *SekiroHandler) handleRegister(packet *protocol.SekiroPacket) error {
    logger.Debug("Register packet received")

    // Extract group and clientId from headers
    group := packet.Headers["group"]
    clientID := packet.Headers["clientId"]

    if group == "" || clientID == "" {
        logger.Error("Register packet missing group or clientId")
        // Send error response or close connection
        return nil
    }

    // Create SekiroClient and register
    sekiroClient := server.NewSekiroClient(group, clientID, h)
    h.clientManager.Register(sekiroClient)

    // Update handler status
    h.Status = StatusOnline

    logger.Infof("Client registered: group=%s, clientId=%s", group, clientID)
    return nil
}
```

- [ ] **Step 3: 添加 Status 字段到 SekiroHandler**

```go
type SekiroHandler struct {
    // ... existing fields
    Status server.ClientStatus
}
```

- [ ] **Step 4: 实现 handleOffline**

```go
func (h *SekiroHandler) handleOffline(packet *protocol.SekiroPacket) error {
    logger.Debug("Client offline notification received")

    // Unregister client
    if h.clientManager != nil {
        // Need to extract group and clientId from context
        h.clientManager.UnregisterByConnection(h)
    }

    return h.Close()
}
```

- [ ] **Step 5: 添加 UnregisterByConnection 到 ClientManager**

```go
// client_manager.go
func (m *ClientManager) UnregisterByConnection(conn *SekiroHandler) {
    m.mu.Lock()
    defer m.mu.Unlock()

    for group, clients := range m.clients {
        for clientID, client := range clients {
            if client.Connection == conn {
                if client.Connection != nil {
                    client.Connection.Close()
                }
                delete(clients, clientID)
                logger.Infof("Client unregistered: group=%s, clientID=%s", group, clientID)
                return
            }
        }
    }
}
```

- [ ] **Step 6: 运行构建**

```bash
go build ./...
```

- [ ] **Step 7: Commit**

```bash
git add pkg/server/detector/sekiro_handler.go pkg/server/client_manager.go
git commit -m "feat: implement client registration handling"
```

---

### Task 6: 实现调用端请求转发

**Files:**
- Create: `pkg/server/http_api.go`
- Modify: `pkg/server/client_manager.go`

- [ ] **Step 1: 创建 HTTP API 处理器**

```go
// pkg/server/http_api.go
package server

import (
    "encoding/json"
    "io"
    "net/http"
    "time"

    "github.com/sekiro-go/sekiro-go/internal/utils/logger"
    "github.com/sekiro-go/sekiro-go/pkg/protocol"
)

// HTTPAPIHandler handles HTTP API requests
type HTTPAPIHandler struct {
    clientManager *ClientManager
}

// NewHTTPAPIHandler creates a new HTTPAPIHandler
func NewHTTPAPIHandler(clientManager *ClientManager) *HTTPAPIHandler {
    return &HTTPAPIHandler{
        clientManager: clientManager,
    }
}

// ServeHTTP handles HTTP requests
func (h *HTTPAPIHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
    path := r.URL.Path

    switch path {
    case "/business/invoke", "/business-demo/invoke":
        h.handleInvoke(w, r)
    case "/business/groupList", "/business-demo/groupList":
        h.handleGroupList(w, r)
    case "/business/clientQueue", "/business-demo/clientQueue":
        h.handleClientQueue(w, r)
    default:
        http.NotFound(w, r)
    }
}

// InvokeRequest represents an invoke request
type InvokeRequest struct {
    Group   string                 `json:"group"`
    Api     string                 `json:"api"`
    Params  map[string]interface{} `json:"params"`
    Timeout int64                  `json:"timeout"`
}

// InvokeResponse represents an invoke response
type InvokeResponse struct {
    Code    int         `json:"code"`
    Message string      `json:"message"`
    Data    interface{} `json:"data"`
}

func (h *HTTPAPIHandler) handleInvoke(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    // Parse request body
    var req InvokeRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Invalid request body", http.StatusBadRequest)
        return
    }

    logger.Infof("Invoke request: group=%s, api=%s", req.Group, req.Api)

    // Allocate client
    client := h.clientManager.AllocateClient(req.Group)
    if client == nil {
        http.Error(w, "No available client for group: "+req.Group, http.StatusServiceUnavailable)
        return
    }

    // Build invoke packet
    packet := &protocol.SekiroPacket{
        Type:         protocol.PacketTypeSInvoke,
        SerialNumber: h.clientManager.NextSerial(),
        Headers: map[string]string{
            "group": req.Group,
            "api":   req.Api,
        },
        Data: h.buildInvokeData(req),
    }

    // Send to client and wait for response
    response, err := h.clientManager.InvokeAndWait(client, packet, time.Duration(req.Timeout)*time.Millisecond)
    if err != nil {
        http.Error(w, "Invoke failed: "+err.Error(), http.StatusGatewayTimeout)
        return
    }

    // Send response
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}

func (h *HTTPAPIHandler) buildInvokeData(req InvokeRequest) []byte {
    data, _ := json.Marshal(req.Params)
    return data
}

func (h *HTTPAPIHandler) handleGroupList(w http.ResponseWriter, r *http.Request) {
    groups := h.clientManager.GetAllGroups()

    response := map[string]interface{}{
        "code":    0,
        "message": "success",
        "data":    groups,
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}

func (h *HTTPAPIHandler) handleClientQueue(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    var req struct {
        Group string `json:"group"`
    }

    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Invalid request body", http.StatusBadRequest)
        return
    }

    clients := h.clientManager.GetClientsByGroup(req.Group)
    clientIDs := make([]string, 0, len(clients))
    for _, c := range clients {
        clientIDs = append(clientIDs, c.ClientID)
    }

    response := map[string]interface{}{
        "code":    0,
        "message": "success",
        "data":    clientIDs,
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}
```

- [ ] **Step 2: 添加响应跟踪到 ClientManager**

```go
// client_manager.go
type ClientManager struct {
    // ... existing fields
    respWaiters   map[int32]chan *protocol.SekiroPacket
    respWaitersMu sync.RWMutex
    serialCounter int32
}

func NewClientManager() *ClientManager {
    return &ClientManager{
        clients:     make(map[string]map[string]*SekiroClient),
        respWaiters: make(map[int32]chan *protocol.SekiroPacket),
    }
}

// NextSerial returns the next serial number
func (m *ClientManager) NextSerial() int32 {
    return atomic.AddInt32(&m.serialCounter, 1)
}

// RegisterWaiter registers a response waiter
func (m *ClientManager) RegisterWaiter(serial int32) chan *protocol.SekiroPacket {
    ch := make(chan *protocol.SekiroPacket, 1)
    m.respWaitersMu.Lock()
    m.respWaiters[serial] = ch
    m.respWaitersMu.Unlock()
    return ch
}

// UnregisterWaiter unregisters a response waiter
func (m *ClientManager) UnregisterWaiter(serial int32) {
    m.respWaitersMu.Lock()
    delete(m.respWaiters, serial)
    m.respWaitersMu.Unlock()
}

// DispatchResponse dispatches a response to the waiter
func (m *ClientManager) DispatchResponse(packet *protocol.SekiroPacket) {
    m.respWaitersMu.RLock()
    ch, ok := m.respWaiters[packet.SerialNumber]
    m.respWaitersMu.RUnlock()

    if ok {
        select {
        case ch <- packet:
        default:
            logger.Warnf("Response channel full for serial %d", packet.SerialNumber)
        }
    }
}

// InvokeAndWait sends a packet and waits for response
func (m *ClientManager) InvokeAndWait(client *SekiroClient, packet *protocol.SekiroPacket, timeout time.Duration) (*InvokeResponse, error) {
    // Register waiter
    respCh := m.RegisterWaiter(packet.SerialNumber)
    defer m.UnregisterWaiter(packet.SerialNumber)

    // Send packet
    if err := client.Connection.Send(packet); err != nil {
        return nil, err
    }

    // Wait for response
    select {
    case resp := <-respCh:
        return parseInvokeResponse(resp.Data)
    case <-time.After(timeout):
        return nil, errors.New("timeout waiting for response")
    }
}

// InvokeResponse 结构
type InvokeResponse struct {
    Code    int         `json:"code"`
    Message string      `json:"message"`
    Data    interface{} `json:"data"`
}

func parseInvokeResponse(data []byte) (*InvokeResponse, error) {
    var resp InvokeResponse
    if err := json.Unmarshal(data, &resp); err != nil {
        // If not JSON, return raw data
        resp.Code = 0
        resp.Message = "success"
        resp.Data = string(data)
    }
    return &resp, nil
}
```

- [ ] **Step 3: 修改 SekiroHandler 分发响应**

```go
// sekiro_handler.go
func (h *SekiroHandler) handleInvokeResponse(packet *protocol.SekiroPacket) error {
    logger.Debug("Invoke response received")

    if h.clientManager != nil {
        h.clientManager.DispatchResponse(packet)
    }
    return nil
}
```

- [ ] **Step 4: 集成 HTTP API 到服务器**

在 `bootstrap.go` 中添加 HTTP API 路由：
```go
// 添加 HTTP API handler 到 server
func (s *Server) startHTTPAPI() {
    httpAPI := NewHTTPAPIHandler(s.clientManager)
    http.Handle("/business/", httpAPI)
    http.Handle("/business-demo/", httpAPI)

    // Start on separate port or same port with different handler
    go http.ListenAndServe(":5613", nil)
}
```

- [ ] **Step 5: 运行构建**

```bash
go build ./...
```

- [ ] **Step 6: Commit**

```bash
git add pkg/server/http_api.go pkg/server/client_manager.go pkg/server/detector/sekiro_handler.go
git commit -m "feat: implement HTTP API invoke forwarding"
```

---

## Chunk 3: 完整集成和测试

### Task 7: 集成测试

**Files:**
- Create: `integration/websocket_client_test.go`
- Create: `integration/http_invoke_test.go`

- [ ] **Step 1: 创建 WebSocket 客户端集成测试**

```go
// integration/websocket_client_test.go
package integration

import (
    "testing"
    "time"

    "github.com/gorilla/websocket"
)

func TestWebSocketClientRegister(t *testing.T) {
    // Connect to server via WebSocket
    conn, _, err := websocket.DefaultDialer.Dial("ws://localhost:5612/register?group=test&clientId=test-1", nil)
    if err != nil {
        t.Fatalf("WebSocket dial failed: %v", err)
    }
    defer conn.Close()

    // Send register packet
    // ... (build and send Sekiro register packet)

    // Verify client is registered (check via HTTP API)
    time.Sleep(100 * time.Millisecond)

    // Make HTTP request to verify
    resp, err := http.Get("http://localhost:5613/business/groupList")
    if err != nil {
        t.Fatalf("HTTP request failed: %v", err)
    }
    defer resp.Body.Close()

    // Parse and verify group "test" is present
    // ...
}
```

- [ ] **Step 2: 创建 HTTP 调用集成测试**

```go
// integration/http_invoke_test.go
package integration

import (
    "testing"
    "bytes"
    "encoding/json"
    "net/http"
)

func TestHTTPInvoke(t *testing.T) {
    // Build invoke request
    req := map[string]interface{}{
        "group": "test",
        "api":   "test-api",
        "params": map[string]interface{}{
            "key": "value",
        },
    }

    body, _ := json.Marshal(req)

    resp, err := http.Post("http://localhost:5613/business/invoke", "application/json", bytes.NewReader(body))
    if err != nil {
        t.Fatalf("HTTP invoke failed: %v", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        t.Errorf("Expected 200, got %d", resp.StatusCode)
    }

    // Parse response
    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)

    if result["code"] != 0 {
        t.Errorf("Expected code 0, got %v", result["code"])
    }
}
```

- [ ] **Step 3: 运行集成测试**

```bash
# First start server
go run cmd/server/main.go -port 5612 &
SERVER_PID=$!

# Start client
go run cmd/client/main.go -server localhost:5612 -group test -client-id test-1 &
CLIENT_PID=$!

# Wait for startup
sleep 2

# Run tests
go test ./integration/... -v

# Cleanup
kill $SERVER_PID $CLIENT_PID
```

- [ ] **Step 4: Commit**

```bash
git add integration/
git commit -m "test: add integration tests for WebSocket and HTTP"
```

---

### Task 8: 完善错误处理和日志

**Files:**
- Modify: All modified files

- [ ] **Step 1: 添加完整的错误处理**

检查所有 TODO 和 "will be implemented" 注释，替换为实际错误处理。

- [ ] **Step 2: 添加详细的日志记录**

确保关键路径有适当的日志记录：
- 客户端注册/注销
- 请求转发
- 响应超时
- WebSocket 连接事件

- [ ] **Step 3: Commit**

```bash
git commit -am "chore: improve error handling and logging"
```

---

### Task 9: 更新文档

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新 README 状态**

修改 "当前状态" 部分：
```markdown
✅ 已完成:
- WebSocket 支持（客户端注册）
- 完整的路由转发逻辑
- HTTP API（/business/invoke, /business/groupList, /business/clientQueue）
- 客户端注册/注销流程
- 异步响应处理（serial number 跟踪）
```

- [ ] **Step 2: 添加使用示例**

```bash
# WebSocket 客户端
go run cmd/client/main.go -server localhost:5612 -group test -client-id test-1

# HTTP 调用
curl -X POST http://localhost:5613/business/invoke \
  -H "Content-Type: application/json" \
  -d '{"group":"test","api":"test","params":{"key":"value"}}'
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with WebSocket and routing status"
```

---

## Verification

最终验证步骤：

```bash
# 清理构建
go clean

# 重新构建
go mod tidy
go build ./...

# 运行测试
go test ./... -v

# 运行服务器
go run cmd/server/main.go -port 5612

# 在另一个终端运行客户端
go run cmd/client/main.go -server localhost:5612 -group test -client-id test-1

# 测试 HTTP API
curl http://localhost:5613/business/groupList
```
