package client

import (
	"net"
	"sync"
	"testing"
	"time"
)

func TestNewRpcInvoker(t *testing.T) {
	serverList := []string{"localhost:5612", "192.168.1.100:5612"}
	invoker := NewRpcInvoker(serverList)

	if invoker == nil {
		t.Fatal("NewRpcInvoker() returned nil")
	}
	if invoker.serverClients == nil {
		t.Error("serverClients not initialized")
	}
}

func TestNewRpcInvokerWithToken(t *testing.T) {
	serverList := []string{"localhost:5612"}
	invoker := NewRpcInvokerWithToken("test-token", serverList)

	if invoker == nil {
		t.Fatal("NewRpcInvokerWithToken() returned nil")
	}
	if invoker.apiToken != "test-token" {
		t.Errorf("apiToken = %s, want 'test-token'", invoker.apiToken)
	}
}

func TestNewRpcInvokerEmptyServerList(t *testing.T) {
	invoker := NewRpcInvoker([]string{})

	if invoker == nil {
		t.Fatal("NewRpcInvoker() returned nil for empty server list")
	}
	if len(invoker.serverClients) != 0 {
		t.Errorf("Expected 0 server clients, got %d", len(invoker.serverClients))
	}
}

func TestInvokeRequestStruct(t *testing.T) {
	req := &InvokeRequest{
		Group:   "test-group",
		Api:     "test-api",
		Params:  map[string]interface{}{"key": "value"},
		Timeout: 30 * time.Second,
	}

	if req.Group != "test-group" {
		t.Errorf("Group = %s, want 'test-group'", req.Group)
	}
	if req.Api != "test-api" {
		t.Errorf("Api = %s, want 'test-api'", req.Api)
	}
	if req.Timeout != 30*time.Second {
		t.Errorf("Timeout = %v, want 30s", req.Timeout)
	}
}

func TestInvokeResponseStruct(t *testing.T) {
	resp := &InvokeResponse{
		Code:    200,
		Message: "success",
		Data:    map[string]interface{}{"result": "ok"},
	}

	if resp.Code != 200 {
		t.Errorf("Code = %d, want 200", resp.Code)
	}
	if resp.Message != "success" {
		t.Errorf("Message = %s, want 'success'", resp.Message)
	}
}

func TestInvokerDestroy(t *testing.T) {
	invoker := NewRpcInvoker([]string{})

	// Destroy should not panic
	invoker.Destroy()

	// After destroy, serverClients should be nil
	if invoker.serverClients != nil {
		t.Error("serverClients should be nil after Destroy()")
	}
}

func TestGetNextClientEmptyList(t *testing.T) {
	invoker := &RpcInvoker{
		serverClients: []*invokerClient{},
	}

	client := invoker.getNextClient()
	if client != nil {
		t.Error("getNextClient() should return nil for empty list")
	}
}

func TestGetNextClientRoundRobin(t *testing.T) {
	invoker := &RpcInvoker{
		serverClients: []*invokerClient{
			{serverAddr: "server1", alive: true},
			{serverAddr: "server2", alive: true},
			{serverAddr: "server3", alive: true},
		},
	}

	// Test round-robin cycles through servers
	seenServers := make(map[string]bool)
	for i := 0; i < 6; i++ {
		client := invoker.getNextClient()
		if client == nil {
			t.Fatal("getNextClient() returned nil unexpectedly")
		}
		seenServers[client.serverAddr] = true
	}

	// All servers should have been seen
	if len(seenServers) != 3 {
		t.Errorf("Expected to see all 3 servers, got %d", len(seenServers))
	}
}

func TestGenerateSerialNumber(t *testing.T) {
	invoker := &RpcInvoker{
		serialCounter: 0,
	}

	// Serial numbers should be incremental
	prev := invoker.generateSerialNumber()
	for i := 0; i < 100; i++ {
		curr := invoker.generateSerialNumber()
		if curr <= prev {
			t.Errorf("Serial number not incrementing: %d <= %d", curr, prev)
		}
		prev = curr
	}
}

func TestGenerateSerialNumberConcurrent(t *testing.T) {
	invoker := &RpcInvoker{
		serialCounter: 0,
	}

	serials := make(map[int32]bool)
	var mu sync.Mutex

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				serial := invoker.generateSerialNumber()
				mu.Lock()
				if serials[serial] {
					mu.Unlock()
					t.Errorf("Duplicate serial number: %d", serial)
				}
				serials[serial] = true
				mu.Unlock()
			}
		}()
	}
	wg.Wait()

	if len(serials) != 1000 {
		t.Errorf("Expected 1000 unique serial numbers, got %d", len(serials))
	}
}

func TestHelperFunctions(t *testing.T) {
	tests := []struct {
		name     string
		fn       func() interface{}
		expected interface{}
	}{
		{
			name: "indexOf found",
			fn: func() interface{} {
				return indexOf("host:port", ':')
			},
			expected: 4,
		},
		{
			name: "indexOf not found",
			fn: func() interface{} {
				return indexOf("host", ':')
			},
			expected: -1,
		},
		{
			name: "parseInt",
			fn: func() interface{} {
				return parseInt("5612")
			},
			expected: 5612,
		},
		{
			name: "parseInt empty",
			fn: func() interface{} {
				return parseInt("")
			},
			expected: 0,
		},
		{
			name: "net.JoinHostPort",
			fn: func() interface{} {
				return net.JoinHostPort("localhost", "5612")
			},
			expected: "localhost:5612",
		},
		{
			name: "formatDuration",
			fn: func() interface{} {
				return formatDuration(30 * time.Second)
			},
			expected: "30s",
		},
		{
			name: "encodeJSON",
			fn: func() interface{} {
				return string(encodeJSON(map[string]string{"key": "value"}))
			},
			expected: `{"key":"value"}`,
		},
		{
			name: "encodeJSON nil",
			fn: func() interface{} {
				return string(encodeJSON(nil))
			},
			expected: "null",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := tt.fn()
			if got != tt.expected {
				t.Errorf("%s = %v, want %v", tt.name, got, tt.expected)
			}
		})
	}
}

func TestParseInvokeResponse(t *testing.T) {
	data := []byte(`{"code": 200, "message": "success"}`)
	resp, err := parseInvokeResponse(data)

	if err != nil {
		t.Errorf("parseInvokeResponse() error = %v", err)
	}
	if resp == nil {
		t.Fatal("parseInvokeResponse() returned nil")
	}
	if resp.Code != 0 {
		t.Errorf("Code = %d, want 0 (default)", resp.Code)
	}
	if resp.Message != "success" {
		t.Errorf("Message = %s, want 'success'", resp.Message)
	}
}
