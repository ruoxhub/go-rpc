package client

import (
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestCircuitBreaker_InitialState(t *testing.T) {
	cb := NewCircuitBreaker(3, 100*time.Millisecond)
	if cb.State() != CircuitClosed {
		t.Fatalf("expected Closed, got %s", cb.State())
	}
	if !cb.Allow() {
		t.Fatal("Allow() should return true in Closed state")
	}
}

// TestCircuitBreaker_AllowNoSpuriousCallback ensures that when Open is
// re-checked under lock and the state is already Closed, OnStateChange is
// not fired (allowLocked returns transitioned=false).
func TestCircuitBreaker_AllowNoSpuriousCallback(t *testing.T) {
	cb := NewCircuitBreaker(1, time.Hour)
	cb.RecordFailure() // → Open
	if cb.State() != CircuitOpen {
		t.Fatalf("expected Open, got %s", cb.State())
	}

	// Concurrent recovery to Closed without going through Allow's Open path.
	cb.RecordSuccess()
	if cb.State() != CircuitClosed {
		t.Fatalf("expected Closed after RecordSuccess, got %s", cb.State())
	}

	var calls atomic.Int32
	cb.OnStateChange = func(from, to CircuitState) {
		calls.Add(1)
	}

	// Force the Open branch entry then re-check sees Closed.
	// Simulate by setting state Open briefly then Closed under race is hard;
	// instead call allowLocked path via state already Closed: Allow short-circuits.
	if !cb.Allow() {
		t.Fatal("Allow should succeed in Closed")
	}
	if calls.Load() != 0 {
		t.Fatalf("spurious OnStateChange calls: %d", calls.Load())
	}

	// Now exercise the re-check path: set Open, then flip to Closed while holding
	// the same sequence Allow uses after Load sees Open.
	cb.RecordFailure() // Closed → Open (threshold=1)
	cb.state.Store(int32(CircuitOpen))
	// Another goroutine recovers:
	cb.mu.Lock()
	cb.transitionToLocked(CircuitClosed)
	cb.mu.Unlock()
	// Clear lastTransition so fireCallback from transition above is consumed.
	cb.fireCallback()
	calls.Store(0)

	// Manually run the Open re-check branch body:
	cb.mu.Lock()
	// state is Closed now
	allowed, transitioned := cb.allowLocked()
	cb.mu.Unlock()
	if !allowed || transitioned {
		t.Fatalf("allowLocked on Closed: allowed=%v transitioned=%v", allowed, transitioned)
	}
	if transitioned {
		cb.fireCallback()
	}
	if calls.Load() != 0 {
		t.Fatalf("expected no callback when transitioned=false, got %d", calls.Load())
	}
}

func TestCircuitBreaker_ClosedToOpen(t *testing.T) {
	cb := NewCircuitBreaker(3, 100*time.Millisecond)

	cb.RecordFailure()
	cb.RecordFailure()
	if cb.State() != CircuitClosed {
		t.Fatalf("expected Closed after 2 failures, got %s", cb.State())
	}

	cb.RecordFailure()
	if cb.State() != CircuitOpen {
		t.Fatalf("expected Open after 3 failures, got %s", cb.State())
	}
}

func TestCircuitBreaker_OpenRejectsRequests(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Hour)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}

	if cb.Allow() {
		t.Fatal("Allow() should return false in Open state")
	}
}

func TestCircuitBreaker_OpenToHalfOpen(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	if cb.State() != CircuitOpen {
		t.Fatal("expected Open")
	}

	time.Sleep(60 * time.Millisecond)

	if cb.State() != CircuitHalfOpen {
		t.Fatalf("expected HalfOpen after timeout, got %s", cb.State())
	}
}

func TestCircuitBreaker_HalfOpenProbeSuccess(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	if !cb.Allow() {
		t.Fatal("Allow() should return true in HalfOpen (first probe)")
	}
	cb.RecordSuccess()

	if cb.State() != CircuitClosed {
		t.Fatalf("expected Closed after probe success, got %s", cb.State())
	}
	if cb.FailureCount() != 0 {
		t.Fatalf("expected failure count 0, got %d", cb.FailureCount())
	}
}

func TestCircuitBreaker_HalfOpenProbeFailure(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	if !cb.Allow() {
		t.Fatal("Allow() should return true for first probe")
	}
	cb.RecordFailure()

	if cb.State() != CircuitOpen {
		t.Fatalf("expected Open after probe failure, got %s", cb.State())
	}
}

func TestCircuitBreaker_HalfOpenSingleProbe(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	if !cb.Allow() {
		t.Fatal("first Allow() in HalfOpen should succeed")
	}
	if cb.Allow() {
		t.Fatal("second Allow() in HalfOpen should be rejected")
	}
}

func TestCircuitBreaker_HalfOpenProbeReleaseOnFailure(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	cb.Allow()
	cb.RecordFailure()

	time.Sleep(60 * time.Millisecond)
	if !cb.Allow() {
		t.Fatal("should allow probe after second HalfOpen cycle")
	}
}

func TestCircuitBreaker_StateChangeCallback(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	var transitions []struct{ from, to CircuitState }
	cb.OnStateChange = func(from, to CircuitState) {
		transitions = append(transitions, struct{ from, to CircuitState }{from, to})
	}

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	if len(transitions) != 1 || transitions[0].from != CircuitClosed || transitions[0].to != CircuitOpen {
		t.Fatalf("expected Closed→Open, got %v", transitions)
	}

	time.Sleep(60 * time.Millisecond)
	cb.State()
	if len(transitions) != 2 || transitions[1].from != CircuitOpen || transitions[1].to != CircuitHalfOpen {
		t.Fatalf("expected Open→HalfOpen, got %v", transitions)
	}

	cb.Allow()
	cb.RecordSuccess()
	if len(transitions) != 3 || transitions[2].from != CircuitHalfOpen || transitions[2].to != CircuitClosed {
		t.Fatalf("expected HalfOpen→Closed, got %v", transitions)
	}
}

func TestCircuitBreaker_ConcurrentHalfOpenProbe(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	var allowed atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if cb.Allow() {
				allowed.Add(1)
			}
		}()
	}
	wg.Wait()

	if allowed.Load() != 1 {
		t.Fatalf("expected exactly 1 probe allowed, got %d", allowed.Load())
	}
}

func TestCircuitBreaker_SuccessResetsFailureCount(t *testing.T) {
	cb := NewCircuitBreaker(3, time.Hour)

	cb.RecordFailure()
	cb.RecordFailure()
	if cb.FailureCount() != 2 {
		t.Fatalf("expected 2, got %d", cb.FailureCount())
	}

	cb.RecordSuccess()
	if cb.FailureCount() != 0 {
		t.Fatalf("expected 0 after success, got %d", cb.FailureCount())
	}

	cb.RecordFailure()
	cb.RecordFailure()
	cb.RecordFailure()
	if cb.State() != CircuitOpen {
		t.Fatal("expected Open after 3 consecutive failures post-reset")
	}
}

func TestCircuitBreaker_HalfOpenRecoveryRequiresNewTimeout(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}
	time.Sleep(60 * time.Millisecond)

	cb.Allow()
	cb.RecordFailure()

	if cb.Allow() {
		t.Fatal("should be Open immediately after probe failure")
	}

	time.Sleep(60 * time.Millisecond)
	if cb.State() != CircuitHalfOpen {
		t.Fatalf("expected HalfOpen after second timeout, got %s", cb.State())
	}
}

func TestRpcClient_CircuitBreakerIntegration(t *testing.T) {
	c := NewRpcClient("g", "c1", nil)

	if !c.GetHealthStatus() {
		t.Fatal("new client should be healthy")
	}

	c.MarkFailure()
	c.MarkFailure()
	if !c.GetHealthStatus() {
		t.Fatal("should still be healthy after 2 failures")
	}

	c.MarkFailure()
	if c.GetHealthStatus() {
		t.Fatal("should be unhealthy after 3 failures")
	}
	if c.GetFailCount() != 3 {
		t.Fatalf("expected fail count 3, got %d", c.GetFailCount())
	}

	c.MarkSuccess()
	if !c.GetHealthStatus() {
		t.Fatal("should be healthy after success")
	}
	if c.GetFailCount() != 0 {
		t.Fatalf("expected fail count 0, got %d", c.GetFailCount())
	}
}

func TestRpcClient_CircuitBreakerCallbackIntegration(t *testing.T) {
	c := NewRpcClient("g", "c1", nil)

	var called bool
	c.SetCircuitBreakerCallback(func(from, to CircuitState) {
		called = true
		if from != CircuitClosed || to != CircuitOpen {
			t.Fatalf("expected Closed→Open, got %s→%s", from, to)
		}
	})

	for i := 0; i < 3; i++ {
		c.MarkFailure()
	}
	if !called {
		t.Fatal("callback should have been called")
	}
}

func TestCircuitBreaker_NoDeadlockWhenCallbackReadsState(t *testing.T) {
	cb := NewCircuitBreaker(3, 50*time.Millisecond)

	done := make(chan struct{})
	cb.OnStateChange = func(from, to CircuitState) {
		// This would deadlock if OnStateChange is called while holding cb.mu,
		// since FailureCount() also acquires cb.mu.
		_ = cb.FailureCount()
		_ = cb.State()
		close(done)
	}

	for i := 0; i < 3; i++ {
		cb.RecordFailure()
	}

	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("deadlock: callback blocked on FailureCount/State")
	}
}

func TestCircuitState_String(t *testing.T) {
	tests := []struct {
		state CircuitState
		want  string
	}{
		{CircuitClosed, "closed"},
		{CircuitOpen, "open"},
		{CircuitHalfOpen, "half_open"},
		{CircuitState(99), "unknown"},
	}
	for _, tt := range tests {
		if got := tt.state.String(); got != tt.want {
			t.Errorf("CircuitState(%d).String() = %q, want %q", tt.state, got, tt.want)
		}
	}
}
