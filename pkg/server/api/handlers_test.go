package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
)

// MockClientManager provides mock implementation for testing
type MockClientManager struct {
	groups  []string
	clients map[string][]*client.SekiroClient
}

func (m *MockClientManager) GetAllGroups() []string {
	return m.groups
}

func (m *MockClientManager) GetClientsByGroup(group string) []*client.SekiroClient {
	return m.clients[group]
}

func (m *MockClientManager) GetClient(group, clientID string) *client.SekiroClient {
	if clients, ok := m.clients[group]; ok {
		for _, c := range clients {
			if c.ClientID == clientID {
				return c
			}
		}
	}
	return nil
}

func (m *MockClientManager) Register(c *client.SekiroClient) {}
func (m *MockClientManager) Unregister(group, clientID string) {}
func (m *MockClientManager) AllocateClient(group string) *client.SekiroClient {
	if clients, ok := m.clients[group]; ok && len(clients) > 0 {
		return clients[0]
	}
	return nil
}
func (m *MockClientManager) CleanupAll() {}

func newTestAPIHandler(mockManager *MockClientManager) *APIHandler {
	return &APIHandler{
		clientManager:  mockManager,
		wsHandler:      nil,
		timeoutManager: forwarder.NewTimeoutManager(nil),
	}
}

func performRequest(r *gin.Engine, method, path string, body interface{}) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()

	var req *http.Request

	if body != nil {
		jsonBody, _ := json.Marshal(body)
		req, _ = http.NewRequest(method, path, bytes.NewBuffer(jsonBody))
		req.Header.Set("Content-Type", "application/json")
	} else {
		req, _ = http.NewRequest(method, path, nil)
	}

	r.ServeHTTP(w, req)
	return w
}

func TestHandleGroupList(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := &MockClientManager{
		groups: []string{"group1", "group2", "group3"},
	}

	handler := newTestAPIHandler(mockManager)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.GET("/business/groupList", handler.HandleGroupList)

	// 执行请求
	w := performRequest(router, http.MethodGet, "/business/groupList", nil)

	// 验证响应
	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(w.Body).Decode(&result); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	if int(result["status"].(float64)) != 0 {
		t.Error("Expected status code 0")
	}

	data := result["data"].([]interface{})
	if len(data) != 3 {
		t.Errorf("Expected 3 groups, got %d", len(data))
	}
}

func TestHandleClientQueue(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := &MockClientManager{
		clients: map[string][]*client.SekiroClient{
			"test-group": {
				{ClientID: "client-1"},
				{ClientID: "client-2"},
			},
		},
	}

	handler := newTestAPIHandler(mockManager)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.GET("/business/clientQueue", handler.HandleClientQueue)

	// 测试缺少 group 参数
	w := performRequest(router, http.MethodGet, "/business/clientQueue", nil)

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}

	// 测试正常请求
	w = performRequest(router, http.MethodGet, "/business/clientQueue?group=test-group", nil)

	json.NewDecoder(w.Body).Decode(&result)
	if int(result["status"].(float64)) != 0 {
		t.Error("Expected success status")
	}

	data := result["data"].([]interface{})
	if len(data) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(data))
	}
}

func TestHandleInvoke(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := &MockClientManager{}
	handler := newTestAPIHandler(mockManager)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	// 测试缺少 group 参数
	w := performRequest(router, http.MethodPost, "/business/invoke", nil)

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}
}

func TestHandleInvoke_GET(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := &MockClientManager{
		clients: map[string][]*client.SekiroClient{
			"test-group": {
				client.NewSekiroClient("test-group", "client-1", nil),
			},
		},
	}
	handler := newTestAPIHandler(mockManager)

	// 创建 gin engine 并注册路由
	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	// 测试 GET 方法
	w := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test", nil)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)
	// 由于没有实际的 WebSocket 连接，应该返回错误
	// 但状态码应该是 200（业务逻辑错误通过 status 字段返回）
	t.Logf("Response: %v", result)
}
