package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/sekiro-go/sekiro-go/pkg/server/client"
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

func TestHandleGroupList(t *testing.T) {
	mockManager := &MockClientManager{
		groups: []string{"group1", "group2", "group3"},
	}

	handler := newAPIHandler(mockManager)

	// 创建测试请求
	req := httptest.NewRequest(http.MethodGet, "/business/groupList", nil)
	w := httptest.NewRecorder()

	// 执行请求
	handler.HandleGroupList(w, req)

	// 验证响应
	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
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
	mockManager := &MockClientManager{
		clients: map[string][]*client.SekiroClient{
			"test-group": {
				{ClientID: "client-1"},
				{ClientID: "client-2"},
			},
		},
	}

	handler := newAPIHandler(mockManager)

	// 测试缺少 group 参数
	req := httptest.NewRequest(http.MethodGet, "/business/clientQueue", nil)
	w := httptest.NewRecorder()
	handler.HandleClientQueue(w, req)

	resp := w.Result()
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}

	// 测试正常请求
	req = httptest.NewRequest(http.MethodGet, "/business/clientQueue?group=test-group", nil)
	w = httptest.NewRecorder()
	handler.HandleClientQueue(w, req)

	resp = w.Result()
	json.NewDecoder(resp.Body).Decode(&result)
	if int(result["status"].(float64)) != 0 {
		t.Error("Expected success status")
	}

	data := result["data"].([]interface{})
	if len(data) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(data))
	}
}

func TestHandleInvoke(t *testing.T) {
	mockManager := &MockClientManager{}
	handler := newAPIHandler(mockManager)

	// 测试缺少 group 参数
	req := httptest.NewRequest(http.MethodPost, "/business/invoke", nil)
	w := httptest.NewRecorder()
	handler.HandleInvoke(w, req)

	resp := w.Result()
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}

	// 测试有效请求（返回 not implemented）
	req = httptest.NewRequest(http.MethodPost, "/business/invoke", nil)
	w = httptest.NewRecorder()
	handler.HandleInvoke(w, req)

	resp = w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}
}

func TestHandleInvoke_GET(t *testing.T) {
	mockManager := &MockClientManager{
		clients: map[string][]*client.SekiroClient{
			"test-group": {
				client.NewSekiroClient("test-group", "client-1", nil),
			},
		},
	}
	handler := newAPIHandler(mockManager)

	// 测试 GET 方法
	req := httptest.NewRequest(http.MethodGet, "/business/invoke?group=test-group&action=test", nil)
	w := httptest.NewRecorder()
	handler.HandleInvoke(w, req)

	resp := w.Result()
	if resp.StatusCode != http.StatusOK {
		t.Errorf("Expected status 200, got %d", resp.StatusCode)
	}

	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	// 应该返回成功消息
	if result["status"].(float64) != 0 {
		t.Errorf("Expected status 0, got %v", result["status"])
	}
}

func TestSendJSONResponse(t *testing.T) {
	w := httptest.NewRecorder()
	handler := &APIHandler{}

	data := map[string]interface{}{
		"status":  0,
		"message": "test",
		"count":   42,
	}

	handler.sendJSONResponse(w, data)

	resp := w.Result()

	// 验证 Content-Type
	contentType := resp.Header.Get("Content-Type")
	if contentType != "application/json" {
		t.Errorf("Expected Content-Type application/json, got %s", contentType)
	}

	// 验证响应体
	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)

	if int(result["status"].(float64)) != 0 {
		t.Error("Expected status 0")
	}
	if result["message"] != "test" {
		t.Errorf("Expected message 'test', got %v", result["message"])
	}
	if int(result["count"].(float64)) != 42 {
		t.Errorf("Expected count 42, got %v", result["count"])
	}
}
