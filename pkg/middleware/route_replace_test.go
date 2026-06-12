package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
)

func TestRouteReplaceMiddlewareDisabledPassesThrough(t *testing.T) {
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/prefix/health", nil)

	RouteReplaceMiddleware(false, "/prefix")(c)

	assert.Equal(t, "/prefix/health", c.Request.URL.Path)
}

func TestRouteReplaceMiddlewareStripsPrefix(t *testing.T) {
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/prefix/health", nil)

	RouteReplaceMiddleware(true, "/prefix")(c)

	assert.Equal(t, "/health", c.Request.URL.Path)
}

func TestRouteReplaceMiddlewareRootWhenPrefixIsWholePath(t *testing.T) {
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	c.Request = httptest.NewRequest(http.MethodGet, "/prefix", nil)

	RouteReplaceMiddleware(true, "/prefix")(c)

	assert.Equal(t, "/", c.Request.URL.Path)
}
