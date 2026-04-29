package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

func TestChatCompletionContract(t *testing.T) {
	gin.SetMode(gin.TestMode)
	body := `{"model":"sekiro-chat","messages":[{"role":"user","content":"hello"}],"tools":[{"type":"function"}],"metadata":{"trace":"1"}}`

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/v1/chat/completions?group=g1", strings.NewReader(body))

	req, err := parseChatCompletionRequest(c)
	if err != nil {
		t.Fatalf("parseChatCompletionRequest() error = %v", err)
	}
	if req.Stream {
		t.Fatal("stream should default to false")
	}
	if req.Group != "g1" {
		t.Fatalf("group = %q, want g1", req.Group)
	}
	if _, ok := req.Params["tools"]; !ok {
		t.Fatal("unknown OpenAI fields should be preserved")
	}
	if _, ok := req.Params["metadata"]; !ok {
		t.Fatal("metadata should be preserved")
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
		{name: "missing group", body: `{"model":"sekiro-chat","messages":[{"role":"user","content":"hello"}]}`, path: "/v1/chat/completions"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gin.SetMode(gin.TestMode)
			w := httptest.NewRecorder()
			c, _ := gin.CreateTestContext(w)
			c.Request = httptest.NewRequest(http.MethodPost, tt.path, strings.NewReader(tt.body))

			if _, err := parseChatCompletionRequest(c); err == nil {
				t.Fatal("expected validation error")
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
	req := &ChatCompletionRequest{Model: "sekiro-chat"}
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
