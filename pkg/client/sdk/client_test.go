package client

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

func TestRpcClientWebSocket(t *testing.T) {
	var requestValues struct {
		path, group, clientID, token string
		bindActions                  []string
	}
	responseCh := make(chan map[string]interface{}, 1)
	server := newSDKWebSocketServer(t, func(r *http.Request, conn *websocket.Conn) {
		requestValues.path = r.URL.Path
		requestValues.group = r.URL.Query().Get("group")
		requestValues.clientID = r.URL.Query().Get("clientId")
		requestValues.token = r.Header.Get("Authorization")
		if r.URL.Query().Get("protocol_version") != "1" || r.URL.Query().Get("capabilities") != protocol.CapabilityInvocationContextV1 {
			t.Errorf("registration query = %#v", r.URL.Query())
		}
		_ = conn.WriteJSON(protocol.WSMessage{
			Type:            protocol.MessageTypeRegistered,
			ProtocolVersion: 1,
			Capabilities:    []string{protocol.CapabilityInvocationContextV1},
		})
		var bind protocol.WSMessage
		if err := conn.ReadJSON(&bind); err != nil {
			t.Errorf("read bind: %v", err)
			return
		}
		requestValues.bindActions = bind.Actions
		deadline := time.Now().Add(5 * time.Second).UnixMilli()
		_ = conn.WriteJSON(map[string]interface{}{
			"type":            "invoke",
			"action":          "echo",
			"__sekiro_seq__":  "seq-1",
			"group":           "g space",
			"clientId":        "c/client",
			"trace_id":        "trace-1",
			"__rpc_context__": map[string]interface{}{"sequence": "seq-1", "trace_id": "trace-1", "group": "g space", "action": "echo", "client_id": "c/client", "deadline_unix_ms": deadline, "attempt": 1},
		})
		var response map[string]interface{}
		if err := conn.ReadJSON(&response); err != nil {
			t.Errorf("read invoke response: %v", err)
			return
		}
		responseCh <- response
	})
	defer server.Close()

	client, err := NewRpcClientURL("g space", "c/client", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	client.SetToken("token-1")
	if err := client.RegisterActionContext("echo", func(ctx context.Context, wire protocol.WireInvocationContext, request map[string]interface{}) (interface{}, error) {
		if wire.Sequence != "seq-1" || wire.Action != "echo" || wire.Group != "g space" || wire.DeadlineUnixMS <= time.Now().UnixMilli() {
			t.Errorf("wire context = %#v", wire)
		}
		return map[string]interface{}{"echo": 1}, nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterAction("zeta", func(map[string]interface{}) (interface{}, error) { return nil, nil }); err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterAction("alpha", func(map[string]interface{}) (interface{}, error) { return nil, nil }); err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	defer client.Destroy(1)

	select {
	case response := <-responseCh:
		if response["type"] != "invoke_response" || response["status"] != float64(0) || response["__sekiro_seq__"] != "seq-1" || response["group"] != "g space" || response["clientId"] != "c/client" || response["trace_id"] != "trace-1" {
			t.Fatalf("invoke response = %#v", response)
		}
		data, ok := response["data"].(map[string]interface{})
		if !ok || data["echo"] != float64(1) {
			t.Fatalf("invoke response data = %#v", response["data"])
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for invoke response")
	}
	if requestValues.path != "/business/register" || requestValues.group != "g space" || requestValues.clientID != "c/client" || requestValues.token != "Bearer token-1" {
		t.Fatalf("registration request = %#v", requestValues)
	}
	if !reflect.DeepEqual(requestValues.bindActions, []string{"alpha", "echo", "zeta"}) {
		t.Fatalf("bind actions = %#v", requestValues.bindActions)
	}
}

func TestRpcClientRawFallbackDoesNotBase64Encode(t *testing.T) {
	responseCh := make(chan map[string]interface{}, 1)
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		_ = conn.ReadJSON(&bind)
		_ = conn.WriteJSON(map[string]interface{}{
			"type": "invoke", "action": "raw", "__sekiro_seq__": "seq-raw", "group": "g", "clientId": "c",
			"__rpc_context__": map[string]interface{}{"sequence": "seq-raw", "action": "raw", "group": "g", "client_id": "c"},
		})
		var response map[string]interface{}
		if err := conn.ReadJSON(&response); err == nil {
			responseCh <- response
		}
	})
	defer server.Close()
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	client.Register(func([]byte) ([]byte, error) { return []byte(`{"echo":1}`), nil })
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	defer client.Destroy(1)
	select {
	case response := <-responseCh:
		data, ok := response["data"].(map[string]interface{})
		if !ok || data["echo"] != float64(1) {
			t.Fatalf("raw response data = %#v", response["data"])
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for raw response")
	}
}

func TestRpcClientLifecycleCompatibility(t *testing.T) {
	var connections atomic.Int32
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		connections.Add(1)
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		_ = conn.ReadJSON(&bind)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	})
	defer server.CloseClientConnections()
	defer server.Close()

	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	time.Sleep(20 * time.Millisecond)
	if got := connections.Load(); got != 1 {
		t.Fatalf("connections = %d, want 1", got)
	}
	client.Destroy(1)
	client.Destroy(1)
	if err := client.Start(); !errors.Is(err, io.ErrClosedPipe) {
		t.Fatalf("Start after Destroy error = %v", err)
	}
}

func TestRpcClientRequiresConfirmedCapability(t *testing.T) {
	tests := []struct {
		name string
		msg  protocol.WSMessage
	}{
		{name: "wrong type", msg: protocol.WSMessage{Type: protocol.MessageTypeHeartbeat, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}}},
		{name: "missing capability", msg: protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) { _ = conn.WriteJSON(tt.msg) })
			defer server.Close()
			client, err := NewRpcClientURL("g", "c", server.URL)
			if err != nil {
				t.Fatal(err)
			}
			if err := client.Start(); err == nil {
				t.Fatal("Start() error = nil, want registration failure")
			} else {
				var registrationErr *RegistrationError
				if !errors.As(err, &registrationErr) {
					t.Fatalf("Start() error = %T %v, want RegistrationError", err, err)
				}
			}
			client.Destroy(0)
		})
	}
}

func TestRpcClientRegistrationWaitsBeforeBind(t *testing.T) {
	release := make(chan struct{})
	bindSeen := make(chan struct{}, 1)
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		<-release
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		if conn.ReadJSON(&bind) == nil {
			bindSeen <- struct{}{}
		}
	})
	defer server.Close()
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	startDone := make(chan error, 1)
	go func() { startDone <- client.Start() }()
	select {
	case <-bindSeen:
		t.Fatal("bind sent before registered confirmation")
	case <-time.After(30 * time.Millisecond):
	}
	close(release)
	if err := <-startDone; err != nil {
		t.Fatal(err)
	}
	client.Destroy(1)
}

func newSDKWebSocketServer(t *testing.T, handler func(*http.Request, *websocket.Conn)) *httptest.Server {
	t.Helper()
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Errorf("upgrade: %v", err)
			return
		}
		defer conn.Close()
		handler(r, conn)
	}))
}

func TestRpcClientURLConversion(t *testing.T) {
	client, err := NewRpcClientURL("g", "c", "https://example.test/root/")
	if err != nil {
		t.Fatal(err)
	}
	if got := client.serverURL.String(); got != "wss://example.test/root/" {
		t.Fatalf("server URL = %q", got)
	}
}

func TestRegisterActionValidation(t *testing.T) {
	client := NewRpcClient("g", "c", "localhost", 5612)
	if err := client.RegisterAction("", func(map[string]interface{}) (interface{}, error) { return nil, nil }); err == nil {
		t.Fatal("empty action registration unexpectedly succeeded")
	}
	if err := client.RegisterAction("echo", nil); err == nil {
		t.Fatal("nil action registration unexpectedly succeeded")
	}
	if err := client.RegisterActionContext("echo", nil); err == nil {
		t.Fatal("nil context action registration unexpectedly succeeded")
	}
}
