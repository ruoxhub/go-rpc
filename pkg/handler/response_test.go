package handler

import (
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestTraceIDGeneratesStableFallbackWithoutMiddleware(t *testing.T) {
	request := httptest.NewRequest("GET", "/health", nil)
	context, _ := gin.CreateTestContext(httptest.NewRecorder())
	context.Request = request
	first := traceID(context)
	second := traceID(context)
	if first == "" || first != second {
		t.Fatalf("traceID fallback not stable/non-empty: first=%q second=%q", first, second)
	}
}
