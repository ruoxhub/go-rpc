package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestLoginRateLimit_AllowsNormalTraffic(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	for i := 0; i < 3; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "192.168.1.1:12345"
		c.Request = req
		middleware(c)
		assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "request %d should pass", i)
	}
}

func TestLoginRateLimit_BlocksExcessive(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	var blocked bool
	for i := 0; i < 20; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "192.168.1.100:12345"
		c.Request = req
		middleware(c)
		if w.Code == http.StatusTooManyRequests {
			blocked = true
			break
		}
	}
	assert.True(t, blocked, "excessive requests should be rate limited")
}

func TestLoginRateLimit_IsolatesByIP(t *testing.T) {
	gin.SetMode(gin.TestMode)
	middleware := LoginRateLimitMiddleware()

	// Exhaust rate limit for IP-A
	for i := 0; i < 20; i++ {
		w := httptest.NewRecorder()
		c, _ := gin.CreateTestContext(w)
		req := httptest.NewRequest("POST", "/api/login", nil)
		req.RemoteAddr = "10.0.0.1:12345"
		c.Request = req
		middleware(c)
	}

	// IP-B should still be allowed
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	req := httptest.NewRequest("POST", "/api/login", nil)
	req.RemoteAddr = "10.0.0.2:12345"
	c.Request = req
	middleware(c)
	assert.NotEqual(t, http.StatusTooManyRequests, w.Code, "different IP should not be rate limited")
}
