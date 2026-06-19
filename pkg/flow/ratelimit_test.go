package flow

import "testing"

func TestRateLimiterRebuildsLimiterWhenQPSChanges(t *testing.T) {
	rl := NewRateLimiter()
	defer rl.Stop()

	first := rl.getLimiter("user:1", 10)
	second := rl.getLimiter("user:1", 10)
	if first != second {
		t.Fatal("expected same limiter when qps is unchanged")
	}

	third := rl.getLimiter("user:1", 20)
	if third == first {
		t.Fatal("expected limiter to be rebuilt when qps changes")
	}
}

func TestRateLimiterAllowUnlimitedForNonPositiveQPS(t *testing.T) {
	rl := NewRateLimiter()
	defer rl.Stop()
	if !rl.Allow("user:1", 0) {
		t.Fatal("expected allow with zero qps")
	}
	if !rl.Allow("user:1", -1) {
		t.Fatal("expected allow with negative qps")
	}
}
