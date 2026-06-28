package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

type mockConfigSvcForRL struct{}

func (m *mockConfigSvcForRL) GetConfig(key string) string                    { return "" }
func (m *mockConfigSvcForRL) GetConfigBool(key string, def bool) bool        { return def }
func (m *mockConfigSvcForRL) GetConfigFloat(key string, def float64) float64 { return def }
func (m *mockConfigSvcForRL) GetConfigInt(key string, def int) int           { return def }
func (m *mockConfigSvcForRL) GetAllConfigs() map[string]string               { return nil }
func (m *mockConfigSvcForRL) SetDependencies(repo repository.SysConfigRepository, eb *eventbus.EventBus) {}
func (m *mockConfigSvcForRL) Refresh() error                                  { return nil }

func TestRateLimitMiddleware_AnonymousUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigSvcForRL{}
	middleware := RateLimitMiddleware(cfg, nil)

	var blocked bool
	for i := 0; i < 30; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("GET", "/test", nil)
		req.RemoteAddr = "192.168.1.50:12345"
		c.Request = req
		middleware(c)
		if w.Code == http.StatusTooManyRequests {
			blocked = true
			break
		}
	}
	assert.True(t, blocked, "anonymous user should eventually be rate limited")
}

func TestRateLimitMiddleware_AuthenticatedUser(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigSvcForRL{}
	middleware := RateLimitMiddleware(cfg, nil)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("GET", "/test", nil)
	c.Request = req
	c.Set(ContextUserKey, &model.UserInfo{ID: 42, QuotaQps: 100.0})
	middleware(c)
	assert.NotEqual(t, http.StatusTooManyRequests, w.Code)
}

func TestRateLimitMiddleware_ZeroQPSAllowsAll(t *testing.T) {
	gin.SetMode(gin.TestMode)
	cfg := &mockConfigSvcForRL{}
	middleware := RateLimitMiddleware(cfg, nil)

	for i := 0; i < 100; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("GET", "/test", nil)
		req.RemoteAddr = "10.0.0.99:12345"
		c.Request = req
		c.Set(ContextUserKey, &model.UserInfo{ID: 1, QuotaQps: 0})
		middleware(c)
		assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "QPS=0 should allow all")
	}
}
