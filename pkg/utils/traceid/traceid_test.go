package traceid

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestGenerate(t *testing.T) {
	id := Generate()
	assert.NotEmpty(t, id)
	assert.Len(t, id, 32) // 16 字节 hex = 32 字符
}

func TestGenerateUnique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 1000; i++ {
		id := Generate()
		assert.False(t, ids[id], "重复的 TraceID: %s", id)
		ids[id] = true
	}
}

func TestFromContext(t *testing.T) {
	// 测试从 context 获取 TraceID
	ctx := context.Background()
	ctx = WithTraceID(ctx, "test-trace-id")
	traceID, ok := FromContext(ctx)
	assert.True(t, ok)
	assert.Equal(t, "test-trace-id", traceID)
}

func TestFromContextNotFound(t *testing.T) {
	ctx := context.Background()
	traceID, ok := FromContext(ctx)
	assert.False(t, ok)
	assert.Empty(t, traceID)
}

func TestSpanID(t *testing.T) {
	id := SpanID()
	assert.NotEmpty(t, id)
	assert.Len(t, id, 16) // 8 字节 hex = 16 字符
}

func TestSpanIDUnique(t *testing.T) {
	ids := make(map[string]bool)
	for i := 0; i < 1000; i++ {
		id := SpanID()
		assert.False(t, ids[id], "重复的 SpanID: %s", id)
		ids[id] = true
	}
}
