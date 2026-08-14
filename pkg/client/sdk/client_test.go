package client

import (
	"context"
	"errors"
	"io"
	"math"
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
			"__rpc_context__": map[string]interface{}{"sequence": "seq-1", "trace_id": "trace-1", "group": "g space", "action": "echo", "client_id": "c/client", "deadline_unix_ms": deadline, "idempotent": false, "idempotency_key": "", "attempt": 1},
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
			"type": "invoke", "action": "raw", "__sekiro_seq__": "seq-raw", "group": "g", "clientId": "c", "trace_id": "trace-seq-raw",
			"__rpc_context__": validSDKContext("seq-raw", "raw"),
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

func TestRpcClientHandlerPanicReturnsErrorAndReaderSurvives(t *testing.T) {
	responses := make(chan map[string]interface{}, 2)
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		if conn.ReadJSON(&bind) != nil {
			return
		}
		writeSDKInvoke(conn, "panic", "seq-panic")
		var first map[string]interface{}
		if conn.ReadJSON(&first) != nil {
			return
		}
		responses <- first
		writeSDKInvoke(conn, "ok", "seq-ok")
		var second map[string]interface{}
		if conn.ReadJSON(&second) == nil {
			responses <- second
		}
	})
	defer server.Close()
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterActionContext("panic", func(context.Context, protocol.WireInvocationContext, map[string]interface{}) (interface{}, error) {
		panic("handler boom")
	}); err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterAction("ok", func(map[string]interface{}) (interface{}, error) { return map[string]interface{}{"ok": 1}, nil }); err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	defer client.Destroy(1)
	var first, second map[string]interface{}
	select {
	case first = <-responses:
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for panic response")
	}
	select {
	case second = <-responses:
	case <-time.After(time.Second):
		t.Fatal("reader did not survive handler panic")
	}
	if first["status"] != float64(-1) || first["__sekiro_seq__"] != "seq-panic" || first["error"] == "" {
		t.Fatalf("panic response = %#v", first)
	}
	if second["status"] != float64(0) || second["__sekiro_seq__"] != "seq-ok" {
		t.Fatalf("second response = %#v", second)
	}
}

func TestRpcClientDestroyFromHandlerDoesNotSelfWait(t *testing.T) {
	destroyReturned := make(chan time.Duration, 1)
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		if conn.ReadJSON(&bind) != nil {
			return
		}
		writeSDKInvoke(conn, "stop", "seq-stop")
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	})
	defer server.Close()
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterActionContext("stop", func(context.Context, protocol.WireInvocationContext, map[string]interface{}) (interface{}, error) {
		started := time.Now()
		client.Destroy(1)
		destroyReturned <- time.Since(started)
		return nil, nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	select {
	case elapsed := <-destroyReturned:
		if elapsed > 500*time.Millisecond {
			t.Fatalf("Destroy from handler took %v", elapsed)
		}
	case <-time.After(time.Second):
		t.Fatal("Destroy from handler did not return promptly")
	}
	client.Destroy(1)
}

func TestRpcClientDispatchCapacityAndDestroyCancellation(t *testing.T) {
	invokesSent := make(chan struct{})
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		if conn.ReadJSON(&bind) != nil {
			return
		}
		writeSDKInvoke(conn, "block", "seq-1")
		writeSDKInvoke(conn, "block", "seq-2")
		writeSDKInvoke(conn, "block", "seq-3")
		close(invokesSent)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	})
	defer server.Close()

	var started atomic.Int32
	ctxCanceled := make(chan struct{})
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.RegisterActionContext("block", func(ctx context.Context, _ protocol.WireInvocationContext, _ map[string]interface{}) (interface{}, error) {
		started.Add(1)
		<-ctx.Done()
		close(ctxCanceled)
		return nil, ctx.Err()
	}); err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	select {
	case <-invokesSent:
	case <-time.After(time.Second):
		t.Fatal("server did not send invoke burst")
	}
	deadline := time.Now().Add(time.Second)
	for started.Load() == 0 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if got := started.Load(); got != 1 {
		t.Fatalf("started handlers before destroy = %d, want 1", got)
	}
	client.Destroy(1)
	select {
	case <-ctxCanceled:
	case <-time.After(time.Second):
		t.Fatal("Destroy did not cancel active context handler")
	}
	time.Sleep(50 * time.Millisecond)
	if got := started.Load(); got != 1 {
		t.Fatalf("queued handlers started after destroy = %d, want 1", got)
	}
	client.Destroy(1)
}

func TestRpcClientHeartbeatStopsAfterDestroy(t *testing.T) {
	server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
		_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
		var bind protocol.WSMessage
		_ = conn.ReadJSON(&bind)
		for {
			if _, _, err := conn.ReadMessage(); err != nil {
				return
			}
		}
	})
	defer server.Close()
	client, err := NewRpcClientURL("g", "c", server.URL)
	if err != nil {
		t.Fatal(err)
	}
	if err := client.Start(); err != nil {
		t.Fatal(err)
	}
	done := client.heartbeatDone
	client.Destroy(1)
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("heartbeat loop did not stop after destroy")
	}
}

func TestRpcClientRejectsInvalidInvocationContexts(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(map[string]interface{})
	}{
		{name: "missing field", mutate: func(ctx map[string]interface{}) { delete(ctx, "attempt") }},
		{name: "extra field", mutate: func(ctx map[string]interface{}) { ctx["extra"] = true }},
		{name: "wrong type", mutate: func(ctx map[string]interface{}) { ctx["idempotent"] = 1 }},
		{name: "numeric field bool", mutate: func(ctx map[string]interface{}) { ctx["attempt"] = true }},
		{name: "negative deadline", mutate: func(ctx map[string]interface{}) { ctx["deadline_unix_ms"] = int64(-1) }},
		{name: "deadline overflow", mutate: func(ctx map[string]interface{}) { ctx["deadline_unix_ms"] = math.MaxFloat64 }},
		{name: "top level mismatch", mutate: func(ctx map[string]interface{}) { ctx["group"] = "other" }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			responseCh := make(chan map[string]interface{}, 1)
			server := newSDKWebSocketServer(t, func(_ *http.Request, conn *websocket.Conn) {
				_ = conn.WriteJSON(protocol.WSMessage{Type: protocol.MessageTypeRegistered, ProtocolVersion: 1, Capabilities: []string{protocol.CapabilityInvocationContextV1}})
				var bind protocol.WSMessage
				if conn.ReadJSON(&bind) != nil {
					return
				}
				ctx := validSDKContext("seq-invalid", "echo")
				tc.mutate(ctx)
				message := map[string]interface{}{"type": "invoke", "action": "echo", "__sekiro_seq__": "seq-invalid", "group": "g", "clientId": "c", "trace_id": "trace-invalid", "__rpc_context__": ctx}
				_ = conn.WriteJSON(message)
				var response map[string]interface{}
				if conn.ReadJSON(&response) == nil {
					responseCh <- response
				}
			})
			defer server.Close()
			client, err := NewRpcClientURL("g", "c", server.URL)
			if err != nil {
				t.Fatal(err)
			}
			var calls atomic.Int32
			if err := client.RegisterActionContext("echo", func(context.Context, protocol.WireInvocationContext, map[string]interface{}) (interface{}, error) {
				calls.Add(1)
				return "unexpected", nil
			}); err != nil {
				t.Fatal(err)
			}
			if err := client.Start(); err != nil {
				t.Fatal(err)
			}
			defer client.Destroy(1)
			select {
			case response := <-responseCh:
				if response["status"] != float64(-1) || response["__sekiro_seq__"] != "seq-invalid" {
					t.Fatalf("invalid context response = %#v", response)
				}
			case <-time.After(time.Second):
				t.Fatal("timed out waiting for invalid context response")
			}
			if calls.Load() != 0 {
				t.Fatalf("handler calls = %d, want 0", calls.Load())
			}
		})
	}
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

func writeSDKInvoke(conn *websocket.Conn, action, sequence string) {
	ctx := validSDKContext(sequence, action)
	_ = conn.WriteJSON(map[string]interface{}{
		"type":           "invoke",
		"action":         action,
		"__sekiro_seq__": sequence,
		"group":          "g",
		"clientId":       "c",
		"trace_id":       "trace-" + sequence, "__rpc_context__": ctx,
	})
}

func validSDKContext(sequence, action string) map[string]interface{} {
	return map[string]interface{}{"sequence": sequence, "trace_id": "trace-" + sequence, "group": "g", "action": action, "client_id": "c", "deadline_unix_ms": time.Now().Add(time.Minute).UnixMilli(), "idempotent": false, "idempotency_key": "", "attempt": 1}
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
