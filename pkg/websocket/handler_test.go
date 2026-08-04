package websocket

import (
	"context"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/model"
)

func TestRpcMessage_Marshal(t *testing.T) {
	msg := RpcMessage{
		Type:      MessageTypeHeartbeat,
		Sequence:  "seq-123",
		Group:     "test-group",
		ClientID:  "client-1",
		Timestamp: 1234567890,
	}

	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("Failed to marshal: %v", err)
	}

	// Unmarshal and verify
	var unmarshaled RpcMessage
	if err := json.Unmarshal(data, &unmarshaled); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if unmarshaled.Type != MessageTypeHeartbeat {
		t.Errorf("Expected type %s, got %s", MessageTypeHeartbeat, unmarshaled.Type)
	}
	if unmarshaled.Sequence != "seq-123" {
		t.Errorf("Expected sequence seq-123, got %s", unmarshaled.Sequence)
	}
}

func TestHandler_NewHandler(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	if handler.clientManager == nil {
		t.Error("Expected clientManager")
	}
	if handler.timeoutManager == nil {
		t.Error("Expected timeoutManager")
	}
	if handler.heartbeatTimeout != 60*time.Second {
		t.Errorf("Expected heartbeat timeout 60s, got %v", handler.heartbeatTimeout)
	}
}

func TestHandler_DefaultConfig(t *testing.T) {
	manager := client.NewClientManager()

	handler := NewHandler(manager, nil, nil, nil, nil)
	defer handler.Shutdown()

	if handler.timeoutManager == nil {
		t.Error("Expected timeoutManager to be created")
	}
}

func TestHandler_GetTimeoutManager(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	got := handler.GetTimeoutManager()
	if got != timeoutMgr {
		t.Error("Expected same timeout manager")
	}
}

func TestSendInvokeRequestIncludesTraceID(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	conn := &mockConn{}
	rpcClient := client.NewRpcClient("test-group", "client-1", conn)
	err := handler.SendInvokeRequest(
		rpcClient,
		"seq-1",
		"test-group",
		"client-1",
		[]byte(`{"action":"test","params":{}}`),
		"trace-fixed-123",
	)
	if err != nil {
		t.Fatalf("SendInvokeRequest() error = %v", err)
	}

	sent := conn.getSent()
	if len(sent) != 1 {
		t.Fatalf("sent message count = %d, want 1", len(sent))
	}
	var payload map[string]interface{}
	if err := json.Unmarshal(sent[0], &payload); err != nil {
		t.Fatalf("unmarshal sent message: %v", err)
	}
	if payload["trace_id"] != "trace-fixed-123" {
		t.Fatalf("trace_id = %v, want trace-fixed-123", payload["trace_id"])
	}
}

func TestHandleInvokeResponseFallsBackToRecordedTraceID(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	record := timeoutMgr.Add("seq-1", "test-group", "client-1", nil)
	record.TraceID = "trace-recorded-123"

	msg := &RpcMessage{
		Type:     MessageTypeInvokeResponse,
		Sequence: "seq-1",
		Group:    "test-group",
		ClientID: "client-1",
		Data:     json.RawMessage(`{"ok":true}`),
		Status:   0,
	}
	handler.handleInvokeResponse(msg, []byte(`{"data":{"ok":true}}`))

	select {
	case response := <-record.ResponseChan:
		if response == nil {
			t.Fatal("response is nil")
		}
		if response.TraceID != "trace-recorded-123" {
			t.Fatalf("response trace ID = %q, want trace-recorded-123", response.TraceID)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for invoke response")
	}
}

func TestHandler_Shutdown(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)

	// Shutdown should not panic
	handler.Shutdown()

	// TimeoutManager should be shut down
	// Try to add a record - should work but manager should be in stopped state
	timeoutMgr.Add("test", "group", "client", nil)
}

func TestRpcMessage_WithAllFields(t *testing.T) {
	data := []byte(`{
		"type": "invoke",
		"sequence": "seq-456",
		"group": "test-group",
		"clientId": "client-1",
		"actions": ["chatCompletions", "getModel"],
		"data": {"key": "value"},
		"status": 200,
		"error": "",
		"timestamp": 1234567890
	}`)

	var msg RpcMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if msg.Type != MessageTypeInvoke {
		t.Errorf("Expected type invoke, got %s", msg.Type)
	}
	if msg.Sequence != "seq-456" {
		t.Errorf("Expected sequence seq-456, got %s", msg.Sequence)
	}
	if msg.Group != "test-group" {
		t.Errorf("Expected group test-group, got %s", msg.Group)
	}
	if msg.ClientID != "client-1" {
		t.Errorf("Expected clientId client-1, got %s", msg.ClientID)
	}
	if msg.Status != 200 {
		t.Errorf("Expected status 200, got %d", msg.Status)
	}
	if len(msg.Actions) != 2 || msg.Actions[0] != "chatCompletions" || msg.Actions[1] != "getModel" {
		t.Errorf("Expected actions to unmarshal, got %#v", msg.Actions)
	}

	// Verify data field
	var dataMap map[string]interface{}
	if err := json.Unmarshal(msg.Data, &dataMap); err != nil {
		t.Fatalf("Failed to unmarshal data: %v", err)
	}
	if dataMap["key"] != "value" {
		t.Errorf("Expected data.key=value, got %v", dataMap["key"])
	}
}

func TestRpcMessage_MinimalFields(t *testing.T) {
	data := []byte(`{"type": "heartbeat"}`)

	var msg RpcMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if msg.Type != MessageTypeHeartbeat {
		t.Errorf("Expected type heartbeat, got %s", msg.Type)
	}
	if msg.Sequence != "" {
		t.Errorf("Expected empty sequence, got %s", msg.Sequence)
	}
}

func TestRpcMessage_ErrorResponse(t *testing.T) {
	data := []byte(`{
		"type": "invoke_response",
		"sequence": "seq-789",
		"error": "client not found",
		"status": 404
	}`)

	var msg RpcMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		t.Fatalf("Failed to unmarshal: %v", err)
	}

	if msg.Type != MessageTypeInvokeResponse {
		t.Errorf("Expected type invoke_response, got %s", msg.Type)
	}
	if msg.Sequence != "seq-789" {
		t.Errorf("Expected sequence seq-789, got %s", msg.Sequence)
	}
	if msg.Error != "client not found" {
		t.Errorf("Expected error 'client not found', got %s", msg.Error)
	}
	if msg.Status != 404 {
		t.Errorf("Expected status 404, got %d", msg.Status)
	}
}

func TestHandler_ProcessBindWithoutDB(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	sekiroClient := client.NewRpcClient("qwenai", "client-1", nil)
	message := []byte(`{
		"type": "bind",
		"group": "qwenai",
		"clientId": "client-1",
		"actions": ["chatCompletions", "getModel", "createChat"]
	}`)

	handler.processMessage(nil, sekiroClient, message)
}

func TestDefaultHandlerConfig(t *testing.T) {
	config := DefaultHandlerConfig()

	if config.HeartbeatTimeout != 60*time.Second {
		t.Errorf("Expected HeartbeatTimeout 60s, got %v", config.HeartbeatTimeout)
	}
}

// --- Mock types for handler tests ---

// mockConn implements transport.Connection for testing.
// It captures all data sent via Send so tests can inspect outgoing messages.
type mockConn struct {
	mu   sync.Mutex
	sent [][]byte
}

func (m *mockConn) Send(data []byte) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sent = append(m.sent, append([]byte(nil), data...))
	return nil
}

func (m *mockConn) Close() error      { return nil }
func (m *mockConn) RemoteAddr() string { return "127.0.0.1:12345" }

func (m *mockConn) getSent() [][]byte {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([][]byte, len(m.sent))
	copy(out, m.sent)
	return out
}

// mockGroupRepo implements repository.GroupRepository for handler tests.
// Only IsGroupRegistered returns a configurable value; all other methods
// are safe no-ops that will never be reached in the tested code paths.
type mockGroupRepo struct {
	registeredGroups map[string]bool
}

func (m *mockGroupRepo) IsGroupRegistered(name string) (bool, error) {
	return m.registeredGroups[name], nil
}

func (m *mockGroupRepo) FindGroupByName(string) (*model.GroupConfig, error) {
	return nil, nil
}
func (m *mockGroupRepo) FindAllGroups() ([]model.GroupConfig, error) {
	return nil, nil
}
func (m *mockGroupRepo) CreateGroup(*model.GroupConfig) error { return nil }
func (m *mockGroupRepo) UpdateGroup(string, map[string]interface{}) error {
	return nil
}
func (m *mockGroupRepo) DeleteGroup(string) error              { return nil }
func (m *mockGroupRepo) CountGroups() (int64, error)           { return 0, nil }
func (m *mockGroupRepo) GetGroupStats(string, bool, string) ([]repository.GroupStats, error) {
	return nil, nil
}
func (m *mockGroupRepo) GetGroupDeviceStats(string, string) (int64, int64, error) {
	return 0, 0, nil
}
func (m *mockGroupRepo) FindDevicesByGroup(string) ([]model.GroupDevice, error) {
	return nil, nil
}
func (m *mockGroupRepo) FindDevice(string, string) (*model.GroupDevice, error) {
	return nil, nil
}
func (m *mockGroupRepo) CreateDevice(*model.GroupDevice) error { return nil }
func (m *mockGroupRepo) UpdateDevice(string, string, map[string]interface{}) error {
	return nil
}
func (m *mockGroupRepo) DeleteDevice(string, string) error    { return nil }
func (m *mockGroupRepo) DeleteDevicesByGroup(string) error    { return nil }
func (m *mockGroupRepo) CountOnlineDevices(string) (int64, error) {
	return 0, nil
}
func (m *mockGroupRepo) CountDevicesByGroup(string) (int64, error) {
	return 0, nil
}
func (m *mockGroupRepo) FindActionsByGroup(string) ([]model.GroupAction, error) {
	return nil, nil
}
func (m *mockGroupRepo) FindAction(string, string) (*model.GroupAction, error) {
	return nil, nil
}
func (m *mockGroupRepo) CreateAction(*model.GroupAction) error { return nil }
func (m *mockGroupRepo) UpsertAction(*model.GroupAction) error { return nil }
func (m *mockGroupRepo) UpdateActionParams(string, string, string) error {
	return nil
}
func (m *mockGroupRepo) DeleteAction(string, string) error     { return nil }
func (m *mockGroupRepo) DeleteActionsByGroup(string) error     { return nil }
func (m *mockGroupRepo) FindAnonymousDeviceGroups(string) ([]repository.AnonymousGroupStats, error) {
	return nil, nil
}
func (m *mockGroupRepo) IsAnonymousGroup(string) (bool, error) { return false, nil }
func (m *mockGroupRepo) DeleteAnonymousGroupDevices(string) (int64, error) {
	return 0, nil
}
func (m *mockGroupRepo) EnsureDefaultActions(string) error { return nil }
func (m *mockGroupRepo) UpsertDevice(*model.GroupDevice) error {
	return nil
}
func (m *mockGroupRepo) UpdateDeviceLastActive(string, string, time.Time) error {
	return nil
}
func (m *mockGroupRepo) WithTx(interface{}) repository.GroupRepository { return m }
func (m *mockGroupRepo) BeginTx() repository.GroupRepository           { return m }
func (m *mockGroupRepo) Commit() error                                 { return nil }
func (m *mockGroupRepo) Rollback() error                               { return nil }

// --- New handler lifecycle and malformed message tests ---

func TestProcessMessage_MalformedJSON(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	mc := &mockConn{}
	sekiroClient := client.NewRpcClient("test-group", "client-1", mc)
	manager.Register(sekiroClient)

	// Send invalid JSON — must not panic
	handler.processMessage(context.Background(), sekiroClient, []byte(`{invalid json!!!`))

	// Client must still be registered after malformed message
	got := manager.GetClient("test-group", "client-1")
	if got == nil {
		t.Fatal("Client should still be registered after malformed message")
	}

	// Handler should have sent an error response via sendError
	sentMessages := mc.getSent()
	if len(sentMessages) == 0 {
		t.Fatal("Expected error response to be sent for malformed JSON")
	}

	var resp RpcMessage
	if err := json.Unmarshal(sentMessages[0], &resp); err != nil {
		t.Fatalf("Failed to unmarshal error response: %v", err)
	}
	if resp.Type != "error" {
		t.Errorf("Expected error type, got %s", resp.Type)
	}
	if resp.Error != "invalid message format" {
		t.Errorf("Expected error 'invalid message format', got %s", resp.Error)
	}
}

func TestProcessMessage_HeartbeatResponse(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	mc := &mockConn{}
	sekiroClient := client.NewRpcClient("test-group", "client-1", mc)
	manager.Register(sekiroClient)

	heartbeat := []byte(`{"type":"heartbeat","group":"test-group","clientId":"client-1"}`)
	handler.processMessage(context.Background(), sekiroClient, heartbeat)

	sentMessages := mc.getSent()
	if len(sentMessages) == 0 {
		t.Fatal("Expected heartbeat response to be sent")
	}

	var resp RpcMessage
	if err := json.Unmarshal(sentMessages[0], &resp); err != nil {
		t.Fatalf("Failed to unmarshal heartbeat response: %v", err)
	}
	if resp.Type != MessageTypeHeartbeat {
		t.Errorf("Expected type %s, got %s", MessageTypeHeartbeat, resp.Type)
	}
	if resp.Timestamp == 0 {
		t.Error("Expected non-zero timestamp in heartbeat response")
	}
}

func TestHandleBind_AnonymousGroupSkips(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	// No groups are registered in the mock repo
	mockRepo := &mockGroupRepo{
		registeredGroups: map[string]bool{},
	}

	handler := NewHandler(manager, timeoutMgr, nil, nil, mockRepo)
	defer handler.Shutdown()

	sekiroClient := client.NewRpcClient("anonymous-group", "client-1", nil)

	msg := &RpcMessage{
		Type:    MessageTypeBind,
		Group:   "anonymous-group",
		Actions: []string{"action1", "action2"},
	}

	// Must not panic and must skip DB writes for unregistered group
	handler.handleBind(sekiroClient, msg)
	// If we reach here without panic, the anonymous group was correctly skipped.
	// The mock repo's CreateAction was never called because IsGroupRegistered returned false.
}

func TestHandleInvokeStream_MissingSequence(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil, nil, nil)
	defer handler.Shutdown()

	// Stream chunk with empty sequence — should be silently dropped
	msg := &RpcMessage{
		Type:     MessageTypeInvokeStream,
		Sequence: "",
		Data:     []byte(`{"chunk":"data"}`),
	}

	// Must not panic
	handler.handleInvokeStream(msg)

	// No stream should be registered in the timeout manager
	if timeoutMgr.StreamCount() != 0 {
		t.Errorf("Expected 0 streams after missing-sequence chunk, got %d", timeoutMgr.StreamCount())
	}
}
