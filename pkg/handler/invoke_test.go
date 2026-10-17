package handler

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/handler/errorcode"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/router"
	ws "github.com/mrh30000/go-rpc/pkg/websocket"
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

// testAnonGroupRepo reports every group as unregistered (anonymous).
// Embeds repository.GroupRepository (nil): unexpected method calls panic,
// so interface growth does not require updating this mock.
type testAnonGroupRepo struct {
	repository.GroupRepository
}

func (testAnonGroupRepo) FindGroupByName(string) (*model.GroupConfig, error) { return nil, nil }
func (testAnonGroupRepo) IsGroupRegistered(string) (bool, error)             { return false, nil }
func (testAnonGroupRepo) EnsureGroup(groupName, userName string) (*model.GroupConfig, error) {
	return &model.GroupConfig{GroupName: groupName, UserName: userName}, nil
}

func newTestAPIHandler(mockManager *MockClientManager) *APIHandler {
	anonRepo := testAnonGroupRepo{}
	tm := forwarder.NewTimeoutManager(nil)
	return &APIHandler{
		clientManager:  mockManager,
		router:         nil,
		wsHandler:      ws.NewHandler(nil, tm, nil, nil, nil),
		timeoutManager: tm,
		// Fail-closed auth requires non-nil groupRepo/authMW. Tests default to
		// an anonymous-only repo so existing invoke/list cases keep working.
		groupRepo: anonRepo,
		authMW: middleware.NewAuthMiddleware(
			nil,
			func(string) (*model.GroupConfig, error) { return nil, nil },
			middleware.DefaultTokenCache(),
			middleware.DefaultGroupCache(),
			nil,
		),
	}
}

func TestAuthorizeRegisteredGroupAccessDBLessExplicitMode(t *testing.T) {
	gin.SetMode(gin.TestMode)
	for _, tc := range []struct {
		name   string
		dbLess bool
		want   int
	}{
		{name: "fail closed by default", dbLess: false, want: http.StatusInternalServerError},
		{name: "explicit db less allows", dbLess: true, want: http.StatusOK},
	} {
		t.Run(tc.name, func(t *testing.T) {
			h := &APIHandler{dbLessMode: tc.dbLess}
			recorder := httptest.NewRecorder()
			context, _ := gin.CreateTestContext(recorder)
			context.Request = httptest.NewRequest(http.MethodPost, "/business/invoke", nil)
			if !h.authorizeRegisteredGroupAccess(context, "registered") {
				if tc.want == http.StatusOK {
					t.Fatal("explicit DB-less mode should allow")
				}
			}
			if tc.want != http.StatusOK && recorder.Code != tc.want {
				t.Fatalf("status=%d, want %d", recorder.Code, tc.want)
			}
		})
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

	if int(result["code"].(float64)) != 0 {
		t.Error("Expected response code 0")
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
	if int(result["code"].(float64)) != 1000 {
		t.Errorf("Expected code 1000 (BadRequest) when group parameter missing, got %v", result["code"])
	}

	w = performRequest(router, http.MethodGet, "/business/clientQueue?group=test-group", nil)

	json.NewDecoder(w.Body).Decode(&result)
	if int(result["code"].(float64)) != 0 {
		t.Errorf("Expected success code 0, got %v", result["code"])
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
	if int(result["code"].(float64)) != 1000 {
		t.Errorf("Expected code 1000 (BadRequest) when group parameter missing, got %v", result["code"])
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

func TestFilterAccessibleGroupsWithoutDatabaseReturnsEmpty(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())
	handler.groupRepo = nil // simulate missing repository

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/groupList", nil)

	groups := []string{"g1", "g2"}
	filtered, err := handler.filterAccessibleGroups(c, groups)
	if err != nil {
		t.Fatalf("filterAccessibleGroups() error = %v", err)
	}
	// Fail closed: without groupRepo, do not leak online group names.
	if len(filtered) != 0 {
		t.Fatalf("filtered len = %d, want 0", len(filtered))
	}
}

func TestAuthorizeRegisteredGroupAccessWithoutDatabaseDeniesRequest(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())
	handler.groupRepo = nil // simulate missing repository

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/business/invoke?group=g1", nil)

	if handler.authorizeRegisteredGroupAccess(c, "g1") {
		t.Fatal("expected authorizeRegisteredGroupAccess to deny when database is unavailable")
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
	return router.NewRouter(nil)
}

func TestHandleKickClient_Single(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c := client.NewRpcClient("g1", "c1", nil)
	c.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c)

	handler := newTestAPIHandler(mockManager)
	handler.eventBus = eventbus.New()

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick?group=g1&clientId=c1", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d, body=%s", w.Code, w.Body.String())
	}

	// 客户端应被注销
	if mockManager.GetClient("g1", "c1") != nil {
		t.Error("expected client to be unregistered after kick")
	}
}

func TestHandleKickClient_GroupNotFound(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())
	handler.eventBus = eventbus.New()

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick?group=missing&clientId=c1", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

func TestHandleKickClient_MissingGroup(t *testing.T) {
	gin.SetMode(gin.TestMode)
	handler := newTestAPIHandler(newMockClientManager())

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleKickClient_WholeGroup(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	c1 := client.NewRpcClient("g1", "c1", nil)
	c1.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c1)

	c2 := client.NewRpcClient("g1", "c2", nil)
	c2.SetStatus(client.StatusOnline)
	mockManager.AddClient("g1", c2)

	handler := newTestAPIHandler(mockManager)
	handler.eventBus = eventbus.New()

	router := gin.New()
	router.DELETE("/business/kick", handler.HandleKickClient)

	req, _ := http.NewRequest(http.MethodDelete, "/business/kick?group=g1", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d, body=%s", w.Code, w.Body.String())
	}

	// 所有客户端应被注销
	if mockManager.GetClient("g1", "c1") != nil {
		t.Error("expected c1 to be unregistered")
	}
	if mockManager.GetClient("g1", "c2") != nil {
		t.Error("expected c2 to be unregistered")
	}

	// group 仍存在（goroutine 未销毁）
	if mockManager.GetGroup("g1") == nil {
		t.Error("expected group g1 to still exist")
	}
}

func TestExtendWriteDeadline(t *testing.T) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodPost, "/business/invoke", bytes.NewReader(nil))

	// httptest.ResponseRecorder 不实现 SetWriteDeadline，ResponseController 会返回
	// ErrNotSupported；这里断言不 panic 且不写出响应体。
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("extendWriteDeadline panicked: %v", r)
		}
	}()
	extendWriteDeadline(c, 30*time.Second)

	if w.Body.Len() != 0 {
		t.Fatalf("extendWriteDeadline wrote body: %s", w.Body.String())
	}
}

// 证明延长写超时确实能突破 http.Server.WriteTimeout：不调用 extendWriteDeadline
// 时 500ms 的写预算会让 1.2s 后的响应写不出去。
func TestExtendWriteDeadlineExceedsServerWriteTimeout(t *testing.T) {
	gin.SetMode(gin.TestMode)
	engine := gin.New()
	engine.POST("/slow", func(c *gin.Context) {
		extendWriteDeadline(c, 2*time.Second)
		time.Sleep(1200 * time.Millisecond)
		c.String(http.StatusOK, "done")
	})

	srv := httptest.NewUnstartedServer(engine)
	srv.Config.WriteTimeout = 500 * time.Millisecond
	srv.Start()
	defer srv.Close()

	resp, err := http.Post(srv.URL+"/slow", "application/json", nil)
	if err != nil {
		t.Fatalf("request failed despite extended deadline: %v", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK || string(body) != "done" {
		t.Fatalf("status=%d body=%q, want 200 done", resp.StatusCode, string(body))
	}
}

// 反向对照：不延长时，同样的处理函数会被 WriteTimeout 截断。
func TestServerWriteTimeoutTruncatesWithoutExtension(t *testing.T) {
	gin.SetMode(gin.TestMode)
	engine := gin.New()
	engine.POST("/slow", func(c *gin.Context) {
		time.Sleep(1200 * time.Millisecond)
		c.String(http.StatusOK, "done")
	})

	srv := httptest.NewUnstartedServer(engine)
	srv.Config.WriteTimeout = 500 * time.Millisecond
	srv.Start()
	defer srv.Close()

	resp, err := http.Post(srv.URL+"/slow", "application/json", nil)
	if err == nil {
		resp.Body.Close()
		t.Fatalf("expected truncation without extension, got status %d", resp.StatusCode)
	}
}

func TestHandleInvoke_ExecutorTypeFilter(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	b1 := client.NewRpcClient("test-group", "browser-1", nil)
	b1.SetStatus(client.StatusOnline)
	b1.SetExecutorType("browser")
	p1 := client.NewRpcClient("test-group", "python-1", nil)
	p1.SetStatus(client.StatusOnline)
	p1.SetExecutorType("python")

	mockManager.AddClient("test-group", b1)
	mockManager.AddClient("test-group", p1)

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()

	router := gin.New()
	router.Any("/business/invoke", handler.HandleInvoke)

	// 1. 指定 executor_type=browser
	w1 := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test&executor_type=browser", nil)
	var result1 map[string]interface{}
	json.NewDecoder(w1.Body).Decode(&result1)
	if result1["clientId"] != "browser-1" {
		t.Fatalf("Expected browser-1, got %v", result1["clientId"])
	}

	// 2. 指定 executor_type=python (POST JSON)
	body := json.RawMessage(`{"group":"test-group","action":"test","executor_type":"python"}`)
	w2 := performRequest(router, http.MethodPost, "/business/invoke", body)
	var result2 map[string]interface{}
	json.NewDecoder(w2.Body).Decode(&result2)
	if result2["clientId"] != "python-1" {
		t.Fatalf("Expected python-1, got %v", result2["clientId"])
	}

	// 3. 指定不存在的 executor_type=mobile
	w3 := performRequest(router, http.MethodGet, "/business/invoke?group=test-group&action=test&executor_type=mobile", nil)
	var result3 map[string]interface{}
	json.NewDecoder(w3.Body).Decode(&result3)
	if result3["code"] != float64(errorcode.NoClientAvailable) {
		t.Fatalf("Expected NoClientAvailable code, got %v", result3)
	}
}
