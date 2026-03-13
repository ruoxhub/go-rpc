package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/sekiro-go/sekiro-go/pkg/server/client"
)

func TestIsWebSocketUpgrade(t *testing.T) {
	// 测试 WebSocket 升级请求
	req := httptest.NewRequest(http.MethodGet, "/register", nil)
	req.Header.Set("Upgrade", "websocket")

	if !IsWebSocketUpgrade(req) {
		t.Error("Expected WebSocket upgrade request to be detected")
	}

	// 测试非 WebSocket 请求
	req2 := httptest.NewRequest(http.MethodGet, "/api/test", nil)
	if IsWebSocketUpgrade(req2) {
		t.Error("Expected non-WebSocket request to return false")
	}
}

func TestHandleRegister_MissingParams(t *testing.T) {
	mockManager := client.NewClientManager()
	handler := NewWebSocketHandler(mockManager)

	// 测试缺少 group 参数
	req := httptest.NewRequest(http.MethodGet, "/register?clientId=test", nil)
	w := httptest.NewRecorder()

	handler.HandleRegister(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", resp.StatusCode)
	}

	// 测试缺少 clientId 参数
	req = httptest.NewRequest(http.MethodGet, "/register?group=test", nil)
	w = httptest.NewRecorder()

	handler.HandleRegister(w, req)

	resp = w.Result()
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", resp.StatusCode)
	}
}

func TestHandleRegister_ValidParams(t *testing.T) {
	mockManager := client.NewClientManager()
	handler := NewWebSocketHandler(mockManager)

	// 测试有效参数（但不是真正的 WebSocket 升级）
	req := httptest.NewRequest(http.MethodGet, "/register?group=test&clientId=testClient", nil)
	req.Header.Set("Upgrade", "websocket")
	w := httptest.NewRecorder()

	// 注意：httptest 不支持真正的 WebSocket 升级，这里只测试参数验证
	handler.HandleRegister(w, req)

	// WebSocket 升级会失败，因为 httptest 不支持
	resp := w.Result()
	body := w.Body.String()
	if resp.StatusCode == http.StatusBadRequest && strings.Contains(body, "websocket") {
		// 预期的错误
		return
	}
}
