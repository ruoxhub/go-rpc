package invocation

import (
	"testing"
	"time"
)

func TestContextWire(t *testing.T) {
	deadline := time.UnixMilli(1786636800000)
	ctx := New("seq-1", "trace-1", "g", "echo", "c", deadline)
	got := ctx.Wire()
	if got.Sequence != "seq-1" || got.DeadlineUnixMS != deadline.UnixMilli() ||
		got.Attempt != 1 || got.Idempotent || got.IdempotencyKey != "" {
		t.Fatalf("wire context = %#v", got)
	}
}
