// Package client implements the Rpc client SDK.
package client

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net"
	"net/http"
	"net/url"
	"sort"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

const (
	clientReadLimit  = 10 << 20
	registrationWait = 5 * time.Second
	heartbeatPeriod  = 25 * time.Second
)

// RegisterHandler is the compatibility raw JSON handler.
type RegisterHandler func(request []byte) ([]byte, error)

// ActionHandler handles a named invocation without a Go context.
type ActionHandler func(request map[string]interface{}) (interface{}, error)

// ContextActionHandler handles a named invocation with its negotiated context.
type ContextActionHandler func(context.Context, protocol.WireInvocationContext, map[string]interface{}) (interface{}, error)

type registeredAction struct {
	plain   ActionHandler
	context ContextActionHandler
}

type dispatchJob struct {
	conn                      *websocket.Conn
	sequence, group, clientID string
	traceID                   string
	wire                      protocol.WireInvocationContext
	request                   map[string]interface{}
	payload                   []byte
	action                    string
}

// RegistrationError reports a failed versioned WebSocket registration.
type RegistrationError struct {
	Reason string
	Err    error
}

func (e *RegistrationError) Error() string {
	if e.Err == nil {
		return "websocket registration failed: " + e.Reason
	}
	return "websocket registration failed: " + e.Reason + ": " + e.Err.Error()
}

func (e *RegistrationError) Unwrap() error { return e.Err }

// RpcClient represents a confirmed WebSocket JSON RPC client.
type RpcClient struct {
	Group      string
	ClientID   string
	ServerHost string
	ServerPort int

	serverURL *url.URL
	apiToken  string
	initErr   error

	mu              sync.RWMutex
	writeMu         sync.Mutex
	conn            *websocket.Conn
	started         bool
	destroyed       bool
	closed          bool
	heartbeat       *time.Ticker
	heartbeatDone   chan struct{}
	readerDone      chan struct{}
	lifecycleCtx    context.Context
	lifecycleCancel context.CancelFunc
	dispatchQueue   chan dispatchJob
	dispatchDone    chan struct{}
	handlers        map[string]registeredAction
	fallback        RegisterHandler
}

// NewRpcClient creates a WebSocket client using the legacy host/port shape.
func NewRpcClient(group, clientID, serverHost string, serverPort int) *RpcClient {
	server := "ws://" + net.JoinHostPort(serverHost, fmt.Sprintf("%d", serverPort))
	client, err := NewRpcClientURL(group, clientID, server)
	if client == nil {
		client = &RpcClient{Group: group, ClientID: clientID, ServerHost: serverHost, ServerPort: serverPort, handlers: make(map[string]registeredAction)}
	}
	client.ServerHost = serverHost
	client.ServerPort = serverPort
	if err != nil {
		client.initErr = err
	}
	return client
}

// NewRpcClientURL creates a WebSocket client from a ws/wss or http/https URL.
func NewRpcClientURL(group, clientID, serverURL string) (*RpcClient, error) {
	u, err := url.Parse(serverURL)
	if err != nil || u.Host == "" {
		return nil, fmt.Errorf("invalid server URL %q", serverURL)
	}
	switch u.Scheme {
	case "http":
		u.Scheme = "ws"
	case "https":
		u.Scheme = "wss"
	case "ws", "wss":
	default:
		return nil, fmt.Errorf("unsupported WebSocket URL scheme %q", u.Scheme)
	}
	if u.Path == "" || u.Path == "/" {
		u.Path = "/business/register"
	}
	return &RpcClient{
		Group:     group,
		ClientID:  clientID,
		serverURL: u,
		handlers:  make(map[string]registeredAction),
	}, nil
}

// SetToken configures the Authorization bearer token and returns the client.
func (c *RpcClient) SetToken(token string) *RpcClient {
	c.mu.Lock()
	c.apiToken = token
	c.mu.Unlock()
	return c
}

// Register stores the compatibility raw JSON handler.
func (c *RpcClient) Register(handler RegisterHandler) {
	c.mu.Lock()
	c.fallback = handler
	c.mu.Unlock()
}

// RegisterAction registers a named plain action handler.
func (c *RpcClient) RegisterAction(action string, handler ActionHandler) error {
	if action == "" {
		return errors.New("action name is empty")
	}
	if handler == nil {
		return errors.New("action handler is nil")
	}
	c.mu.Lock()
	if c.handlers == nil {
		c.handlers = make(map[string]registeredAction)
	}
	entry := c.handlers[action]
	entry.plain = handler
	c.handlers[action] = entry
	c.mu.Unlock()
	return nil
}

// RegisterActionContext registers a named context-aware action handler.
func (c *RpcClient) RegisterActionContext(action string, handler ContextActionHandler) error {
	if action == "" {
		return errors.New("action name is empty")
	}
	if handler == nil {
		return errors.New("action handler is nil")
	}
	c.mu.Lock()
	if c.handlers == nil {
		c.handlers = make(map[string]registeredAction)
	}
	entry := c.handlers[action]
	entry.context = handler
	c.handlers[action] = entry
	c.mu.Unlock()
	return nil
}

// Start opens one confirmed WebSocket connection and starts its reader.
func (c *RpcClient) Start() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.destroyed {
		return io.ErrClosedPipe
	}
	if c.started {
		return nil
	}
	if c.initErr != nil {
		return c.initErr
	}
	if c.serverURL == nil {
		return errors.New("server URL is not configured")
	}

	headers := http.Header{}
	if c.apiToken != "" {
		headers.Set("Authorization", "Bearer "+c.apiToken)
	}
	requestURL := *c.serverURL
	query := requestURL.Query()
	query.Set("protocol_version", fmt.Sprintf("%d", protocol.CurrentProtocolVersion))
	query.Set("capabilities", protocol.CapabilityInvocationContextV1)
	query.Set("group", c.Group)
	query.Set("clientId", c.ClientID)
	requestURL.RawQuery = query.Encode()

	conn, _, err := websocket.DefaultDialer.Dial(requestURL.String(), headers)
	if err != nil {
		return err
	}
	conn.SetReadLimit(clientReadLimit)
	if err := conn.SetReadDeadline(time.Now().Add(registrationWait)); err != nil {
		_ = conn.Close()
		return &RegistrationError{Reason: "set confirmation deadline", Err: err}
	}
	_, payload, err := conn.ReadMessage()
	if err != nil {
		_ = conn.Close()
		return &RegistrationError{Reason: "confirmation missing", Err: err}
	}
	var registered protocol.WSMessage
	if err := json.Unmarshal(payload, &registered); err != nil {
		_ = conn.Close()
		return &RegistrationError{Reason: "confirmation is invalid JSON", Err: err}
	}
	if registered.Type != protocol.MessageTypeRegistered {
		_ = conn.Close()
		return &RegistrationError{Reason: "confirmation message type is not registered"}
	}
	if registered.ProtocolVersion != protocol.CurrentProtocolVersion {
		_ = conn.Close()
		return &RegistrationError{Reason: "confirmation protocol version is unsupported"}
	}
	if !contains(registered.Capabilities, protocol.CapabilityInvocationContextV1) {
		_ = conn.Close()
		return &RegistrationError{Reason: "confirmation lacks invocation_context.v1"}
	}
	if err := conn.SetReadDeadline(time.Time{}); err != nil {
		_ = conn.Close()
		return &RegistrationError{Reason: "clear confirmation deadline", Err: err}
	}

	c.conn = conn
	c.closed = false
	c.started = true
	bind := protocol.WSMessage{Type: protocol.MessageTypeBind, Actions: c.actionNamesLocked()}
	if err := c.writeJSONLocked(conn, bind); err != nil {
		c.conn = nil
		c.started = false
		c.closeSocket(conn)
		return err
	}
	c.readerDone = make(chan struct{})
	c.heartbeat = time.NewTicker(heartbeatPeriod)
	c.heartbeatDone = make(chan struct{})
	c.lifecycleCtx, c.lifecycleCancel = context.WithCancel(context.Background())
	// ponytail: one worker and one queued slot bound Stage 1 dispatch leakage; Stage 3 can replace this with a cancellable scheduler.
	c.dispatchQueue = make(chan dispatchJob, 1)
	c.dispatchDone = make(chan struct{})
	readerDone := c.readerDone
	ticker := c.heartbeat
	lifecycleCtx := c.lifecycleCtx
	dispatchQueue := c.dispatchQueue
	dispatchDone := c.dispatchDone
	go c.readLoop(conn, readerDone)
	heartbeatDone := c.heartbeatDone
	go c.heartbeatLoop(conn, ticker, lifecycleCtx, heartbeatDone)
	go c.dispatchLoop(lifecycleCtx, dispatchQueue, dispatchDone)
	return nil
}

func (c *RpcClient) actionNamesLocked() []string {
	actions := make([]string, 0, len(c.handlers))
	for action := range c.handlers {
		actions = append(actions, action)
	}
	sort.Strings(actions)
	return actions
}

func (c *RpcClient) readLoop(conn *websocket.Conn, done chan struct{}) {
	defer close(done)
	defer c.cancelLifecycle()
	defer c.stopHeartbeat()
	defer c.closeSocket(conn)
	for {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return
		}
		c.handleMessage(conn, payload)
	}
}

func (c *RpcClient) dispatchLoop(ctx context.Context, queue <-chan dispatchJob, done chan struct{}) {
	defer close(done)
	for {
		select {
		case <-ctx.Done():
			return
		case job := <-queue:
			if ctx.Err() != nil {
				return
			}
			c.processInvoke(ctx, job)
		}
	}
}

func (c *RpcClient) heartbeatLoop(conn *websocket.Conn, ticker *time.Ticker, ctx context.Context, done chan struct{}) {
	defer close(done)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			c.writeMu.Lock()
			if c.closed {
				c.writeMu.Unlock()
				return
			}
			_ = conn.WriteControl(websocket.PingMessage, nil, time.Now().Add(5*time.Second))
			c.writeMu.Unlock()
		}
	}
}

func (c *RpcClient) handleMessage(conn *websocket.Conn, payload []byte) {
	var request map[string]interface{}
	if err := json.Unmarshal(payload, &request); err != nil || request == nil {
		_ = c.writeResponse(conn, "", "", "", "", nil, fmt.Errorf("invalid invoke JSON"))
		return
	}
	messageType, _ := request["type"].(string)
	if messageType == string(protocol.MessageTypeHeartbeat) || messageType != string(protocol.MessageTypeInvoke) {
		return
	}
	sequence, _ := request["__sekiro_seq__"].(string)
	if sequence == "" {
		sequence, _ = request["sequence"].(string)
	}
	group, _ := request["group"].(string)
	if group == "" {
		group = c.Group
	}
	clientID, _ := request["clientId"].(string)
	if clientID == "" {
		clientID = c.ClientID
	}
	traceID, _ := request["trace_id"].(string)
	action, _ := request["action"].(string)
	if action == "" || sequence == "" {
		_ = c.writeResponse(conn, sequence, group, clientID, traceID, nil, errors.New("invoke action and sequence are required"))
		return
	}
	contextRaw, ok := request["__rpc_context__"]
	if !ok {
		_ = c.writeResponse(conn, sequence, group, clientID, traceID, nil, errors.New("invoke context is required"))
		return
	}
	if err := validateInvocationContext(contextRaw, sequence, traceID, group, action, clientID); err != nil {
		_ = c.writeResponse(conn, sequence, group, clientID, traceID, nil, err)
		return
	}
	contextBytes, err := json.Marshal(contextRaw)
	if err != nil {
		_ = c.writeResponse(conn, sequence, group, clientID, traceID, nil, err)
		return
	}
	var wire protocol.WireInvocationContext
	if err := json.Unmarshal(contextBytes, &wire); err != nil {
		_ = c.writeResponse(conn, sequence, group, clientID, traceID, nil, fmt.Errorf("decode invoke context: %w", err))
		return
	}

	c.enqueueInvoke(dispatchJob{
		conn: conn, sequence: sequence, group: group, clientID: clientID, traceID: traceID,
		wire: wire, request: request, payload: payload, action: action,
	})
}

func validateInvocationContext(raw interface{}, sequence, traceID, group, action, clientID string) error {
	value, ok := raw.(map[string]interface{})
	if !ok || len(value) != 9 {
		return errors.New("invoke context must contain exactly nine fields")
	}
	required := []string{"sequence", "trace_id", "group", "action", "client_id", "deadline_unix_ms", "idempotent", "idempotency_key", "attempt"}
	for _, key := range required {
		if _, ok := value[key]; !ok {
			return fmt.Errorf("invoke context field %s is required", key)
		}
	}
	stringFields := map[string]string{"sequence": sequence, "trace_id": traceID, "group": group, "action": action, "client_id": clientID}
	for key, expected := range stringFields {
		got, ok := value[key].(string)
		if !ok || got != expected {
			return fmt.Errorf("invoke context field %s does not match top-level invoke", key)
		}
	}
	if _, ok := value["idempotency_key"].(string); !ok {
		return errors.New("invoke context idempotency_key must be a string")
	}
	if _, ok := value["idempotent"].(bool); !ok {
		return errors.New("invoke context idempotent must be a boolean")
	}
	deadline, ok := value["deadline_unix_ms"].(float64)
	if !ok || math.IsNaN(deadline) || math.IsInf(deadline, 0) || deadline < 0 || math.Trunc(deadline) != deadline || deadline >= float64(math.MaxInt64) {
		return errors.New("invoke context deadline_unix_ms must be a non-negative integer")
	}
	attempt, ok := value["attempt"].(float64)
	maxInt := float64(int64(^uint(0) >> 1))
	if !ok || math.IsNaN(attempt) || math.IsInf(attempt, 0) || attempt < 0 || math.Trunc(attempt) != attempt || attempt >= maxInt {
		return errors.New("invoke context attempt must be a non-negative integer")
	}
	return nil
}

func (c *RpcClient) enqueueInvoke(job dispatchJob) {
	c.mu.RLock()
	ctx := c.lifecycleCtx
	queue := c.dispatchQueue
	destroyed := c.destroyed
	c.mu.RUnlock()
	if destroyed || ctx == nil {
		return
	}
	select {
	case <-ctx.Done():
		return
	case queue <- job:
	default:
		_ = c.writeResponse(job.conn, job.sequence, job.group, job.clientID, job.traceID, nil, errors.New("invoke dispatch capacity exceeded"))
	}
}

func (c *RpcClient) processInvoke(ctx context.Context, job dispatchJob) {
	var result interface{}
	var invokeErr error
	func() {
		defer func() {
			if recovered := recover(); recovered != nil {
				invokeErr = fmt.Errorf("invoke handler panic: %v", recovered)
			}
		}()
		result, invokeErr = c.dispatch(ctx, job.wire, job.request, job.payload, job.action)
	}()
	_ = c.writeResponse(job.conn, job.sequence, job.group, job.clientID, job.traceID, result, invokeErr)
}

func (c *RpcClient) dispatch(ctx context.Context, wire protocol.WireInvocationContext, request map[string]interface{}, raw []byte, action string) (interface{}, error) {
	if wire.DeadlineUnixMS > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithDeadline(ctx, time.UnixMilli(wire.DeadlineUnixMS))
		defer cancel()
	}
	c.mu.RLock()
	entry := c.handlers[action]
	fallback := c.fallback
	c.mu.RUnlock()
	if entry.context != nil {
		return entry.context(ctx, wire, request)
	}
	if entry.plain != nil {
		return entry.plain(request)
	}
	if fallback == nil {
		return nil, fmt.Errorf("no handler registered for action %q", action)
	}
	result, err := fallback(raw)
	if err != nil {
		return nil, err
	}
	if !json.Valid(result) {
		return nil, errors.New("legacy handler returned invalid JSON")
	}
	return json.RawMessage(result), nil
}

func (c *RpcClient) writeResponse(conn *websocket.Conn, sequence, group, clientID, traceID string, data interface{}, invokeErr error) error {
	response := map[string]interface{}{
		"type":           string(protocol.MessageTypeInvokeResponse),
		"__sekiro_seq__": sequence,
		"group":          group,
		"clientId":       clientID,
		"trace_id":       traceID,
	}
	if invokeErr != nil {
		response["status"] = -1
		response["error"] = invokeErr.Error()
	} else {
		response["status"] = 0
		response["data"] = data
	}
	return c.writeJSON(conn, response)
}

func (c *RpcClient) writeJSON(conn *websocket.Conn, value interface{}) error {
	c.writeMu.Lock()
	defer c.writeMu.Unlock()
	return c.writeJSONLocked(conn, value)
}

func (c *RpcClient) writeJSONLocked(conn *websocket.Conn, value interface{}) error {
	if c.closed {
		return io.ErrClosedPipe
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return err
	}
	if err := conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return err
	}
	return conn.WriteMessage(websocket.TextMessage, payload)
}

func (c *RpcClient) stopHeartbeat() {
	c.mu.Lock()
	if c.heartbeat != nil {
		c.heartbeat.Stop()
		c.heartbeat = nil
	}
	c.mu.Unlock()
}

func (c *RpcClient) cancelLifecycle() {
	c.mu.RLock()
	cancel := c.lifecycleCancel
	c.mu.RUnlock()
	if cancel != nil {
		cancel()
	}
}

func (c *RpcClient) closeSocket(conn *websocket.Conn) {
	if conn == nil {
		return
	}
	c.writeMu.Lock()
	if !c.closed {
		c.closed = true
		_ = conn.Close()
	}
	c.writeMu.Unlock()
}

// Destroy closes the client and waits up to waitSeconds for its reader.
func (c *RpcClient) Destroy(waitSeconds int64) {
	c.mu.Lock()
	c.destroyed = true
	c.started = false
	conn := c.conn
	done := c.readerDone
	heartbeatDone := c.heartbeatDone
	cancel := c.lifecycleCancel
	if c.heartbeat != nil {
		c.heartbeat.Stop()
		c.heartbeat = nil
	}
	c.handlers = make(map[string]registeredAction)
	c.fallback = nil
	c.mu.Unlock()
	if cancel != nil {
		cancel()
	}
	c.closeSocket(conn)
	if (done == nil && heartbeatDone == nil) || waitSeconds <= 0 {
		return
	}
	timer := time.NewTimer(time.Duration(waitSeconds) * time.Second)
	defer timer.Stop()
	if done != nil {
		select {
		case <-done:
		case <-timer.C:
			return
		}
	}
	if heartbeatDone != nil {
		select {
		case <-heartbeatDone:
		case <-timer.C:
		}
	}
}

func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
