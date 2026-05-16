package api

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	wsHandler "github.com/mrh30000/go-rpc/pkg/server/websocket"
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
	gin.SetMode(gin.TestMode)
	mockManager := client.NewClientManager()
	mockRpcHandler := wsHandler.NewHandler(mockManager, nil, nil, nil)
	handler := NewWebSocketHandler(mockRpcHandler)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.GET("/register", handler.HandleRegister)

	// 测试缺少 group 参数
	w := performRequest(router, http.MethodGet, "/register?clientId=test", nil)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}

	// 测试缺少 clientId 参数
	w = performRequest(router, http.MethodGet, "/register?group=test", nil)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}
}

func TestHandleRegister_ValidParams(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := client.NewClientManager()
	mockRpcHandler := wsHandler.NewHandler(mockManager, nil, nil, nil)
	handler := NewWebSocketHandler(mockRpcHandler)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.GET("/register", handler.HandleRegister)

	// 测试有效参数（但不是真正的 WebSocket 升级）
	w := performRequest(router, http.MethodGet, "/register?group=test&clientId=testClient", nil)

	// 由于 httptest 不支持真正的 WebSocket 升级，会返回 500 或成功
	// 这里只验证参数验证通过
	body := w.Body.String()
	if w.Code == http.StatusBadRequest && strings.Contains(body, "parameters required") {
		t.Error("Expected valid params to pass validation")
	}
}
