package api

import (
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

func TestChatCompletionContract(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()
	handler.timeoutManager = forwarder.NewTimeoutManager(nil)
	defer handler.timeoutManager.Shutdown()

	router := gin.New()
	router.POST("/v1/chat/completions", handler.HandleChatCompletions)

	body := `{"model":"sekiro-chat","messages":[{"role":"user","content":"hello"}],"tools":[{"type":"function"}],"metadata":{"trace":"1"}}`
	w := performRequest(router, http.MethodPost, "/v1/chat/completions?group=g1", json.RawMessage(body))

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("unmarshal response error = %v", err)
	}

	errMap, ok := resp["error"].(map[string]interface{})
	if !ok {
		t.Fatalf("expected error wrapper in response: %v", resp)
	}
	if errMap["message"] != "no client available" {
		t.Fatalf("expected 'no client available', got %q", errMap["message"])
	}
}

func TestChatCompletionContractRejectsInvalidRequests(t *testing.T) {
	tests := []struct {
		name string
		body string
		path string
	}{
		{name: "invalid json", body: `{`, path: "/v1/chat/completions?group=g1"},
		{name: "missing model", body: `{"messages":[{"role":"user","content":"hello"}]}`, path: "/v1/chat/completions?group=g1"},
		{name: "missing messages", body: `{"model":"sekiro-chat"}`, path: "/v1/chat/completions?group=g1"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gin.SetMode(gin.TestMode)
			mockManager := newMockClientManager()
			defer mockManager.Close()

			handler := newTestAPIHandler(mockManager)
			handler.router = newDefaultTestRouter()
			handler.timeoutManager = forwarder.NewTimeoutManager(nil)
			defer handler.timeoutManager.Shutdown()

			router := gin.New()
			router.POST("/v1/chat/completions", handler.HandleChatCompletions)

			w := performRequest(router, http.MethodPost, tt.path, json.RawMessage(tt.body))

			if w.Code != http.StatusBadRequest {
				t.Fatalf("status = %d, want 400", w.Code)
			}
		})
	}
}


func TestChatCompletionNonStreamInvalidConnectionCleansRecord(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c1 := client.NewRpcClient("g1", "c1", nil)
	c1.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c1)

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()
	handler.timeoutManager = forwarder.NewTimeoutManager(nil)
	defer handler.timeoutManager.Shutdown()

	router := gin.New()
	router.POST("/v1/chat/completions", handler.HandleChatCompletions)

	body := `{"model":"sekiro-chat","messages":[{"role":"user","content":"hello"}]}`
	w := performRequest(router, http.MethodPost, "/v1/chat/completions?group=g1", json.RawMessage(body))

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	if handler.timeoutManager.Count() != 0 {
		t.Fatalf("timeout records = %d, want 0", handler.timeoutManager.Count())
	}
}

func TestChatCompletionStreamInvalidConnectionCleansStream(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c1 := client.NewRpcClient("g1", "c1", nil)
	c1.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c1)

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()
	handler.timeoutManager = forwarder.NewTimeoutManager(nil)
	defer handler.timeoutManager.Shutdown()

	router := gin.New()
	router.POST("/v1/chat/completions", handler.HandleChatCompletions)

	body := `{"model":"sekiro-chat","stream":true,"messages":[{"role":"user","content":"hello"}]}`
	w := performRequest(router, http.MethodPost, "/v1/chat/completions?group=g1", json.RawMessage(body))

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	if handler.timeoutManager.StreamCount() != 0 {
		t.Fatalf("stream records = %d, want 0", handler.timeoutManager.StreamCount())
	}
}

func TestNormalizeChatCompletionChunkPreservesStructuredDelta(t *testing.T) {
	req := &ChatCompletionRequest{ChatCompletionRequest: model.ChatCompletionRequest{Model: "sekiro-chat"}}
	chunk := normalizeChatCompletionChunk(
		req,
		[]byte(`{"delta":{"role":"assistant","tool_calls":[{"id":"call-1"}]},"finish_reason":null}`),
		"seq-1",
		time.Now(),
	).(map[string]interface{})

	choices := chunk["choices"].([]map[string]interface{})
	delta := choices[0]["delta"].(map[string]interface{})
	if delta["role"] != "assistant" {
		t.Fatalf("delta role = %v, want assistant", delta["role"])
	}
	if _, ok := delta["content"]; ok {
		t.Fatal("structured delta should not be wrapped inside content")
	}
}
