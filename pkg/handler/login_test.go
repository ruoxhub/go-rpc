package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// TestMain 测试主函数，初始化数据库
// 注意：此测试需要 PostgreSQL 数据库运行
// 运行测试前请确保数据库可用，或跳过此测试
func setupTestDB(t *testing.T) {
	previousDB := database.DB
	database.DB = nil
	t.Cleanup(func() {
		database.DB = previousDB
	})

	// 尝试连接测试数据库
	err := database.InitFromConfig("localhost", 5432, "postgres", "postgres", "sekiro_test", "disable")
	if err != nil {
		t.Skipf("跳过测试：无法连接数据库 - %v", err)
	}
	err = database.AutoMigrate()
	if err != nil {
		t.Skipf("跳过测试：无法迁移数据库 - %v", err)
	}
}

func performLoginRequest(r *gin.Engine, method, path string, body interface{}) *httptest.ResponseRecorder {
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

func TestHandleRegister_Success(t *testing.T) {
	gin.SetMode(gin.TestMode)
	setupTestDB(t)

	// 清理测试数据
	database.GetDB().Where("user_name = ?", "testuser").Delete(&model.UserInfo{})

	// 创建测试路由器
	router := gin.New()
	router.POST("/rpc-api/user-info/register", HandleRegister)

	// 准备注册请求
	req := RegisterRequest{
		UserName: "testuser",
		Password: "testpass123",
	}

	w := performLoginRequest(router, http.MethodPost, "/rpc-api/user-info/register", req)

	// 验证响应状态码
	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(w.Body).Decode(&result); err != nil {
		t.Fatalf("Failed to decode response: %v", err)
	}

	// 验证响应数据
	if int(result["status"].(float64)) != 0 {
		t.Errorf("Expected status 0, got %v", result["status"])
	}

	// 验证用户已创建
	var user model.UserInfo
	database.GetDB().Where("user_name = ?", "testuser").First(&user)
	if user.ID == 0 {
		t.Error("Expected user to be created in database")
	}
}

func TestHandleRegister_DuplicateUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	setupTestDB(t)

	// 先创建一个同名用户
	database.GetDB().Where("user_name = ?", "existinguser").Delete(&model.UserInfo{})
	database.GetDB().Create(&model.UserInfo{
		UserName:   "existinguser",
		Password:   "password123",
		ApiToken:   "test-token",
		LoginToken: "test-login-token",
	})

	router := gin.New()
	router.POST("/rpc-api/user-info/register", HandleRegister)

	req := RegisterRequest{
		UserName: "existinguser",
		Password: "newpass123",
	}

	w := performLoginRequest(router, http.MethodPost, "/rpc-api/user-info/register", req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}

	var result map[string]interface{}
	json.NewDecoder(w.Body).Decode(&result)

	// 应该返回错误状态
	if int(result["status"].(float64)) != -1 {
		t.Errorf("Expected status -1 for duplicate user, got %v", result["status"])
	}

	if !strings.Contains(result["message"].(string), "已存在") {
		t.Errorf("Expected 'already exists' message, got %v", result["message"])
	}
}

func TestHandleRegister_InvalidInput(t *testing.T) {
	gin.SetMode(gin.TestMode)
	setupTestDB(t)

	router := gin.New()
	router.POST("/rpc-api/user-info/register", HandleRegister)

	// 测试空用户名
	req := RegisterRequest{
		UserName: "",
		Password: "testpass123",
	}

	w := performLoginRequest(router, http.MethodPost, "/rpc-api/user-info/register", req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w.Code)
	}

	// 测试空密码
	req2 := RegisterRequest{
		UserName: "validuser",
		Password: "",
	}

	w2 := performLoginRequest(router, http.MethodPost, "/rpc-api/user-info/register", req2)

	if w2.Code != http.StatusBadRequest {
		t.Errorf("Expected status 400, got %d", w2.Code)
	}
}
