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

func randomHex(nBytes int) string {
	b := make([]byte, nBytes)
	if _, err := rand.Read(b); err != nil {
		return hex.EncodeToString([]byte(fmt.Sprintf("%d", time.Now().UnixNano())))
	}
	return hex.EncodeToString(b)
}

func Generate() string {
	return randomHex(16)
}

func WithTraceID(ctx context.Context, traceID string) context.Context {
	return context.WithValue(ctx, traceIDKey, traceID)
}

func FromContext(ctx context.Context) (string, bool) {
	id, ok := ctx.Value(traceIDKey).(string)
	return id, ok
}

func SpanID() string {
	return randomHex(8)
}
