package flow

import (
	"sync"
	"time"
)

// BackoffConfig holds configuration for delay backoff
type BackoffConfig struct {
	// InitialDelay is the initial delay duration
	InitialDelay time.Duration
	// MaxDelay is the maximum delay duration
	MaxDelay time.Duration
	// Multiplier is the factor to increase delay
	Multiplier float64
	// ResetTimeout is the timeout to reset backoff state
	ResetTimeout time.Duration
}

// DefaultBackoffConfig returns default backoff configuration
func DefaultBackoffConfig() *BackoffConfig {
	return &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     20 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
}

// BackoffState tracks the current backoff state for a group
type BackoffState struct {
	// currentDelay is the current delay duration
	currentDelay time.Duration
	// lastAttempt is the time of last attempt
	lastAttempt time.Time
	// lastSuccess is the time of last successful operation
	lastSuccess time.Time
	// mu protects concurrent access
	mu sync.Mutex
}

// DelayBackoff manages delay backoff for empty client queues
type DelayBackoff struct {
	config  *BackoffConfig
	states  map[string]*BackoffState
	statesMu sync.RWMutex
}

// NewDelayBackoff creates a new DelayBackoff instance
func NewDelayBackoff(config *BackoffConfig) *DelayBackoff {
	if config == nil {
		config = DefaultBackoffConfig()
	}
	return &DelayBackoff{
		config: config,
		states: make(map[string]*BackoffState),
	}
}

// GetState gets or creates backoff state for a group
func (d *DelayBackoff) GetState(groupName string) *BackoffState {
	d.statesMu.RLock()
	state, ok := d.states[groupName]
	d.statesMu.RUnlock()

	if ok {
		return state
	}

	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	// Double-check
	if state, ok := d.states[groupName]; ok {
		return state
	}

	state = &BackoffState{
		currentDelay: d.config.InitialDelay,
		lastAttempt:  time.Time{},
		lastSuccess:  time.Now(),
	}
	d.states[groupName] = state
	return state
}

// GetDelay returns the current delay for a group
func (d *DelayBackoff) GetDelay(groupName string) time.Duration {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	// Check if reset timeout has passed
	if time.Since(state.lastSuccess) > d.config.ResetTimeout {
		state.currentDelay = d.config.InitialDelay
	}

	return state.currentDelay
}

// RecordEmpty records an empty queue attempt and increases backoff
func (d *DelayBackoff) RecordEmpty(groupName string) {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	state.lastAttempt = time.Now()

	// Increase delay with multiplier
	newDelay := time.Duration(float64(state.currentDelay) * d.config.Multiplier)
	if newDelay > d.config.MaxDelay {
		newDelay = d.config.MaxDelay
	}
	state.currentDelay = newDelay
}

// RecordSuccess records a successful operation and resets backoff
func (d *DelayBackoff) RecordSuccess(groupName string) {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	state.lastSuccess = time.Now()
	state.currentDelay = d.config.InitialDelay
}

// Reset resets backoff state for a group
func (d *DelayBackoff) Reset(groupName string) {
	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	if state, ok := d.states[groupName]; ok {
		state.mu.Lock()
		state.currentDelay = d.config.InitialDelay
		state.lastSuccess = time.Now()
		state.mu.Unlock()
	}
}

// Remove removes backoff state for a group
func (d *DelayBackoff) Remove(groupName string) {
	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	delete(d.states, groupName)
}

// Cleanup cleans up all backoff states
func (d *DelayBackoff) Cleanup() {
	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	d.states = make(map[string]*BackoffState)
}
