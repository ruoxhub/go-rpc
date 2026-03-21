package middleware

import (
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/sekiro-go/sekiro-go/pkg/utils/traceid"
	"github.com/stretchr/testify/assert"
)

func TestTraceMiddleware(t *testing.T) {
	// 设置 Gin 为测试模式
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	// 创建测试请求
	c.Request = httptest.NewRequest("POST", "/business/invoke?group=test-group&clientId=test-client", nil)

	// 应用中间件
	TraceMiddleware()(c)

	// 验证 TraceID 被设置到响应头
	traceID := w.Header().Get("X-Trace-ID")
	assert.NotEmpty(t, traceID)
	assert.Len(t, traceID, 32)

	// 验证 SpanID 被设置到响应头
	spanID := w.Header().Get("X-Span-ID")
	assert.NotEmpty(t, spanID)
	assert.Len(t, spanID, 16)

	// 验证 TraceID 被设置到 context
	traceIDFromCtx, ok := traceid.FromContext(c.Request.Context())
	assert.True(t, ok)
	assert.Equal(t, traceID, traceIDFromCtx)
}

func TestTraceMiddleware_WithExistingTraceID(t *testing.T) {
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	customTraceID := "custom-trace-id-123456789012345"
	c.Request = httptest.NewRequest("POST", "/business/invoke", nil)
	c.Request.Header.Set("X-Trace-ID", customTraceID)

	TraceMiddleware()(c)

	// 验证自定义 TraceID 被使用
	assert.Equal(t, customTraceID, w.Header().Get("X-Trace-ID"))
}

func TestTraceMiddleware_StatusTracking(t *testing.T) {
	gin.SetMode(gin.TestMode)

	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)

	c.Request = httptest.NewRequest("GET", "/test", nil)

	// 应用中间件并设置状态
	TraceMiddleware()(c)
	c.Status(200)

	// 验证响应状态
	assert.Equal(t, 200, w.Code)
}
