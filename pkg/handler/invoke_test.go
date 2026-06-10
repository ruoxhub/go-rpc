package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/router"
)

// MockClientManager provides mock implementation for testing.
type MockClientManager struct {
	groups   []string
	clients  map[string][]*client.RpcClient
	groupMap map[string]*client.RpcGroup
}

func newMockClientManager() *MockClientManager {
	return &MockClientManager{
		clients:  make(map[string][]*client.RpcClient),
		groupMap: make(map[string]*client.RpcGroup),
	}
}

func (m *MockClientManager) AddClient(groupName string, c *client.RpcClient) {
	m.clients[groupName] = append(m.clients[groupName], c)
	group, ok := m.groupMap[groupName]
	if !ok {
		group = client.NewRpcGroup(groupName)
		m.groupMap[groupName] = group
		m.groups = append(m.groups, groupName)
	}
	group.Register(c)
}

func (m *MockClientManager) Close() {
	for _, group := range m.groupMap {
		group.Close()
	}
}

func (m *MockClientManager) GetAllGroups() []string {
	return m.groups
}

func (m *MockClientManager) GetClientsByGroup(group string) []*client.RpcClient {
	return m.clients[group]
}

func (m *MockClientManager) GetClient(group, clientID string) *client.RpcClient {
	groupInst := m.groupMap[group]
	if groupInst == nil {
		return nil
	}
	return groupInst.GetClient(clientID)
}

func (m *MockClientManager) GetGroup(groupName string) *client.RpcGroup {
	return m.groupMap[groupName]
}

func (m *MockClientManager) Register(c *client.RpcClient)                  {}
func (m *MockClientManager) Unregister(group, clientID string)             {}
func (m *MockClientManager) AllocateClient(group string) *client.RpcClient { return nil }
func (m *MockClientManager) CleanupAll()                                   {}

func newTestAPIHandler(mockManager *MockClientManager) *APIHandler {
	return &APIHandler{
		clientManager:  mockManager,
		router:         nil,
		wsHandler:      nil,
		timeoutManager: forwarder.NewTimeoutManager(nil),
	}
}

func performRequest(r *gin.Engine, method, path string, body interface{}) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()

	var req *http.Request

	if body != nil {
		jsonBody, ok := body.(json.RawMessage)
		if !ok {
			jsonBody, _ = json.Marshal(body)
		}
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
	mockManager := newMockClientManager()
	defer mockManager.Close()

	mockManager.groups = []string{"group1", "group2", "group3"}
	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.GET("/business/groupList", handler.HandleGroupList)

	w := performRequest(router, http.MethodGet, "/business/groupList", nil)

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
	mockManager := newMockClientManager()
	defer mockManager.Close()

	mockManager.clients["test-group"] = []*client.RpcClient{
		{ClientID: "client-1"},
		{ClientID: "client-2"},
	}

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.GET("/business/clientQueue", handler.HandleClientQueue)

	w := performRequest(router, http.MethodGet, "/business/clientQueue", nil)

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}

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

func TestHandleInvoke_MissingGroup(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	w := performRequest(router, http.MethodPost, "/business/invoke", nil)

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)
	if int(result["status"].(float64)) != -1 {
		t.Error("Expected error when group parameter missing")
	}
}

func TestHandleInvoke_RoundRobinSelectsDifferentClients(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c1 := client.NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(client.StatusOnline)
	c2 := client.NewRpcClient("test-group", "client-2", nil)
	c2.SetStatus(client.StatusOnline)
	mockManager.AddClient("test-group", c1)
	mockManager.AddClient("test-group", c2)

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	w1 := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test", nil)
	w2 := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test", nil)

	var result1 map[string]interface{}
	var result2 map[string]interface{}
	json.NewDecoder(w1.Body).Decode(&result1)
	json.NewDecoder(w2.Body).Decode(&result2)

	if result1["message"] != "Failed to send request: invalid client connection" || result2["message"] != "Failed to send request: invalid client connection" {
		t.Fatalf("Expected invalid connection responses, got %v and %v", result1, result2)
	}
	if result1["clientId"] == result2["clientId"] {
		t.Fatalf("Expected round robin to select different clients, got %v and %v", result1["clientId"], result2["clientId"])
	}
}

func TestHandleInvoke_ConstantInvokePinsClient(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c1 := client.NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(client.StatusOnline)
	c2 := client.NewRpcClient("test-group", "client-2", nil)
	c2.SetStatus(client.StatusOnline)
	mockManager.AddClient("test-group", c1)
	mockManager.AddClient("test-group", c2)

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	path := "/business/invoke?group=test-group&action=test&constantInvoke=true"
	w1 := performRequest(router, http.MethodGet, path, nil)
	w2 := performRequest(router, http.MethodGet, path, nil)

	var result1 map[string]interface{}
	var result2 map[string]interface{}
	json.NewDecoder(w1.Body).Decode(&result1)
	json.NewDecoder(w2.Body).Decode(&result2)

	if result1["clientId"] != result2["clientId"] {
		t.Fatalf("Expected constantInvoke to pin the same client, got %v and %v", result1["clientId"], result2["clientId"])
	}
}

func TestHandleInvoke_SpecifiedClientNotFound(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()
	mockManager.AddClient("test-group", &client.RpcClient{ClientID: "other-client"})

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	w := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test&clientId=missing", nil)

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)

	if result["message"] != "client missing not found in group test-group" {
		t.Fatalf("Unexpected error response: %v", result)
	}
}

func TestFilterAccessibleGroupsWithoutDatabaseReturnsOriginalGroups(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/groupList", nil)

	groups := []string{"g1", "g2"}
	filtered, err := handler.filterAccessibleGroups(c, groups)
	if err != nil {
		t.Fatalf("filterAccessibleGroups() error = %v", err)
	}
	if len(filtered) != len(groups) {
		t.Fatalf("filtered len = %d, want %d", len(filtered), len(groups))
	}
}

func TestAuthorizeRegisteredGroupAccessWithoutDatabaseAllowsRequest(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/invoke?group=g1", nil)

	if !handler.authorizeRegisteredGroupAccess(c, "g1") {
		t.Fatal("expected authorizeRegisteredGroupAccess to allow when database is unavailable")
	}
}

func TestHandleGroupListAccessibleGroupsUsesContextUserWhenPresent(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/groupList", nil)
	c.Set(middleware.ContextUserKey, &model.UserInfo{ID: 1, UserName: "alice", IsAdmin: true})

	groups := []string{"g1"}
	filtered, err := handler.filterAccessibleGroups(c, groups)
	if err != nil {
		t.Fatalf("filterAccessibleGroups() error = %v", err)
	}
	if len(filtered) != 1 || filtered[0] != "g1" {
		t.Fatalf("unexpected filtered groups: %v", filtered)
	}
}

func newDefaultTestRouter() *router.Router {
	return router.NewRouter()
}
