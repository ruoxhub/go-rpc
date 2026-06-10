package flow

import (
	"sync"
	"time"
)

type BackoffConfig struct {
	InitialDelay time.Duration
	MaxDelay     time.Duration
	Multiplier   float64
	ResetTimeout time.Duration
}

func DefaultBackoffConfig() *BackoffConfig {
	return &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     20 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
}

type BackoffState struct {
	currentDelay time.Duration
	lastAttempt  time.Time
	lastSuccess  time.Time
	mu           sync.Mutex
}

// DelayBackoff manages delay backoff for empty client queues.
type DelayBackoff struct {
	config   *BackoffConfig
	states   map[string]*BackoffState
	statesMu sync.RWMutex
}

func NewDelayBackoff(config *BackoffConfig) *DelayBackoff {
	if config == nil {
		config = DefaultBackoffConfig()
	}
	return &DelayBackoff{
		config: config,
		states: make(map[string]*BackoffState),
	}
}

func (d *DelayBackoff) GetState(groupName string) *BackoffState {
	d.statesMu.RLock()
	state, ok := d.states[groupName]
	d.statesMu.RUnlock()

	if ok {
		return state
	}

	d.statesMu.Lock()
	defer d.statesMu.Unlock()

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

func (d *DelayBackoff) GetDelay(groupName string) time.Duration {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	if time.Since(state.lastSuccess) > d.config.ResetTimeout {
		state.currentDelay = d.config.InitialDelay
	}

	return state.currentDelay
}

func (d *DelayBackoff) RecordEmpty(groupName string) {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	state.lastAttempt = time.Now()

	newDelay := time.Duration(float64(state.currentDelay) * d.config.Multiplier)
	if newDelay > d.config.MaxDelay {
		newDelay = d.config.MaxDelay
	}
	state.currentDelay = newDelay
}

func (d *DelayBackoff) RecordSuccess(groupName string) {
	state := d.GetState(groupName)
	state.mu.Lock()
	defer state.mu.Unlock()

	state.lastSuccess = time.Now()
	state.currentDelay = d.config.InitialDelay
}

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

func (d *DelayBackoff) Remove(groupName string) {
	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	delete(d.states, groupName)
}

func (d *DelayBackoff) Cleanup() {
	d.statesMu.Lock()
	defer d.statesMu.Unlock()

	d.states = make(map[string]*BackoffState)
}
