package traceid

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"
)

type contextKey string

const traceIDKey contextKey = "trace_id"

// Generate 生成新的 TraceID (32 字符 hex 字符串)
func Generate() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		// Fallback 使用时间戳
		return hex.EncodeToString([]byte(fmt.Sprintf("%d", time.Now().UnixNano())))
	}
	return hex.EncodeToString(b)
}

// WithTraceID 将 TraceID 存入 context
func WithTraceID(ctx context.Context, traceID string) context.Context {
	return context.WithValue(ctx, traceIDKey, traceID)
}

// FromContext 从 context 获取 TraceID
func FromContext(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(traceIDKey).(string)
	return id, ok
}

// SpanID 生成 SpanID (16 字符 hex 字符串)
func SpanID() string {
	b := make([]byte, 8)
	if _, err := rand.Read(b); err != nil {
		return hex.EncodeToString([]byte(fmt.Sprintf("%d", time.Now().UnixNano())))
	}
	return hex.EncodeToString(b)
}
