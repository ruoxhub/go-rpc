package client

import (
	"sync"
	"sync/atomic"
	"time"
)

// CircuitState represents the state of a circuit breaker.
type CircuitState int32

const (
	CircuitClosed   CircuitState = 0
	CircuitOpen     CircuitState = 1
	CircuitHalfOpen CircuitState = 2
)

func (s CircuitState) String() string {
	switch s {
	case CircuitClosed:
		return "closed"
	case CircuitOpen:
		return "open"
	case CircuitHalfOpen:
		return "half_open"
	default:
		return "unknown"
	}
}

// CircuitBreaker implements a three-state circuit breaker:
//
//	Closed → Open (after failureThreshold consecutive failures)
//	Open → HalfOpen (after recoveryTimeout elapses, checked lazily)
//	HalfOpen → Closed (on probe success)
//	HalfOpen → Open (on probe failure)
type CircuitBreaker struct {
	state            atomic.Int32
	failureCount     int
	failureThreshold int
	recoveryTimeout  time.Duration
	lastFailureAt    time.Time
	halfOpenProbe    atomic.Int32
	OnStateChange    func(from, to CircuitState)
	lastTransition   transition
	mu               sync.Mutex
}

type transition struct {
	from CircuitState
	to   CircuitState
	ok   bool
}

func NewCircuitBreaker(threshold int, timeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		failureThreshold: threshold,
		recoveryTimeout:  timeout,
	}
}

// Allow reports whether a request is permitted through the circuit breaker.
//
// Closed: always allowed.
// Open: transitions to HalfOpen if recoveryTimeout has elapsed, then allows one probe.
// HalfOpen: allows one probe via CAS; subsequent callers are rejected until the probe completes.
func (cb *CircuitBreaker) Allow() bool {
	state := CircuitState(cb.state.Load())

	switch state {
	case CircuitClosed:
		return true
	case CircuitOpen:
		cb.mu.Lock()
		if CircuitState(cb.state.Load()) != CircuitOpen {
			cb.mu.Unlock()
			return cb.Allow()
		}
		if time.Since(cb.lastFailureAt) < cb.recoveryTimeout {
			cb.mu.Unlock()
			return false
		}
		cb.transitionToLocked(CircuitHalfOpen)
		cb.mu.Unlock()
		cb.fireCallback()
		return cb.halfOpenProbe.CompareAndSwap(0, 1)
	case CircuitHalfOpen:
		return cb.halfOpenProbe.CompareAndSwap(0, 1)
	default:
		return false
	}
}

// RecordSuccess records a successful request.
// HalfOpen → Closed (probe succeeded); Open → Closed (e.g. heartbeat recovery); Closed resets failure count.
func (cb *CircuitBreaker) RecordSuccess() {
	cb.mu.Lock()
	state := CircuitState(cb.state.Load())
	switch state {
	case CircuitClosed:
		cb.failureCount = 0
		cb.mu.Unlock()
	case CircuitOpen, CircuitHalfOpen:
		cb.failureCount = 0
		cb.halfOpenProbe.Store(0)
		cb.transitionToLocked(CircuitClosed)
		cb.mu.Unlock()
		cb.fireCallback()
	}
}

// RecordFailure records a failed request.
// Closed: increments failure count; transitions to Open when threshold is reached.
// HalfOpen: transitions back to Open immediately (probe failed).
func (cb *CircuitBreaker) RecordFailure() {
	cb.mu.Lock()
	state := CircuitState(cb.state.Load())
	cb.lastFailureAt = time.Now()

	switch state {
	case CircuitClosed:
		cb.failureCount++
		if cb.failureCount >= cb.failureThreshold {
			cb.transitionToLocked(CircuitOpen)
			cb.mu.Unlock()
			cb.fireCallback()
			return
		}
		cb.mu.Unlock()
	case CircuitHalfOpen:
		cb.halfOpenProbe.Store(0)
		cb.transitionToLocked(CircuitOpen)
		cb.mu.Unlock()
		cb.fireCallback()
	}
}

// State returns the current circuit breaker state, performing lazy timeout checks.
func (cb *CircuitBreaker) State() CircuitState {
	state := CircuitState(cb.state.Load())
	if state == CircuitOpen {
		cb.mu.Lock()
		if CircuitState(cb.state.Load()) == CircuitOpen && time.Since(cb.lastFailureAt) >= cb.recoveryTimeout {
			cb.transitionToLocked(CircuitHalfOpen)
			cb.mu.Unlock()
			cb.fireCallback()
			return CircuitHalfOpen
		}
		cb.mu.Unlock()
	}
	return CircuitState(cb.state.Load())
}

// FailureCount returns the current consecutive failure count.
func (cb *CircuitBreaker) FailureCount() int {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	return cb.failureCount
}

// pendingTransition stores a deferred state change callback invocation.
// Set by transitionToLocked while holding the mutex, consumed by fireCallback after release.

// transitionToLocked atomically updates the state and records the transition for later callback.
// Must be called while holding cb.mu.
func (cb *CircuitBreaker) transitionToLocked(to CircuitState) {
	from := CircuitState(cb.state.Load())
	if from == to {
		cb.lastTransition = transition{}
		return
	}
	cb.state.Store(int32(to))
	cb.lastTransition = transition{from: from, to: to, ok: true}
}

// fireCallback invokes the OnStateChange callback if a transition was recorded.
// Must be called AFTER releasing cb.mu.
func (cb *CircuitBreaker) fireCallback() {
	t := cb.lastTransition
	if !t.ok {
		return
	}
	cb.lastTransition = transition{}
	if cb.OnStateChange != nil {
		cb.OnStateChange(t.from, t.to)
	}
}
