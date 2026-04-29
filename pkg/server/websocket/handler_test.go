package websocket

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

func TestSekiroMessage_Marshal(t *testing.T) {
	msg := SekiroMessage{
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
	var unmarshaled SekiroMessage
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

	handler := NewHandler(manager, timeoutMgr, nil)
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

	handler := NewHandler(manager, nil, nil)
	defer handler.Shutdown()

	if handler.timeoutManager == nil {
		t.Error("Expected timeoutManager to be created")
	}
}

func TestHandler_GetTimeoutManager(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	handler := NewHandler(manager, timeoutMgr, nil)
	defer handler.Shutdown()

	got := handler.GetTimeoutManager()
	if got != timeoutMgr {
		t.Error("Expected same timeout manager")
	}
}

func TestHandler_Shutdown(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)

	handler := NewHandler(manager, timeoutMgr, nil)

	// Shutdown should not panic
	handler.Shutdown()

	// TimeoutManager should be shut down
	// Try to add a record - should work but manager should be in stopped state
	timeoutMgr.Add("test", "group", "client", nil)
}

func TestSekiroMessage_WithAllFields(t *testing.T) {
	data := []byte(`{
		"type": "invoke",
		"sequence": "seq-456",
		"group": "test-group",
		"clientId": "client-1",
		"data": {"key": "value"},
		"status": 200,
		"error": "",
		"timestamp": 1234567890
	}`)

	var msg SekiroMessage
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

	// Verify data field
	var dataMap map[string]interface{}
	if err := json.Unmarshal(msg.Data, &dataMap); err != nil {
		t.Fatalf("Failed to unmarshal data: %v", err)
	}
	if dataMap["key"] != "value" {
		t.Errorf("Expected data.key=value, got %v", dataMap["key"])
	}
}

func TestSekiroMessage_MinimalFields(t *testing.T) {
	data := []byte(`{"type": "heartbeat"}`)

	var msg SekiroMessage
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

func TestSekiroMessage_ErrorResponse(t *testing.T) {
	data := []byte(`{
		"type": "invoke_response",
		"sequence": "seq-789",
		"error": "client not found",
		"status": 404
	}`)

	var msg SekiroMessage
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

func TestDefaultHandlerConfig(t *testing.T) {
	config := DefaultHandlerConfig()

	if config.HeartbeatTimeout != 60*time.Second {
		t.Errorf("Expected HeartbeatTimeout 60s, got %v", config.HeartbeatTimeout)
	}
}
