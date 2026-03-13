package forwarder

import (
	"sync"
	"time"
)

// InvokeRecord tracks a single invoke request with timeout management
type InvokeRecord struct {
	// ID is the unique identifier for this invoke request
	ID string
	// Group is the target group name
	Group string
	// ClientID is the target client ID
	ClientID string
	// Data is the request payload
	Data []byte
	// CreatedAt is the time when this record was created
	CreatedAt time.Time
	// Timeout is the timeout duration for this request
	Timeout time.Duration
	// ResponseChan is the channel to receive response
	ResponseChan chan *InvokeResponse
	// timedOut indicates if the request has timed out
	timedOut bool
	// mu protects concurrent access
	mu sync.Mutex
}

// InvokeResponse represents the response of an invoke request
type InvokeResponse struct {
	// Data is the response payload
	Data []byte
	// Error is the error message if any
	Error string
	// Status is the response status code
	Status int
}

// IsTimedOut returns true if the request has timed out
func (r *InvokeRecord) IsTimedOut() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.timedOut
}

// SetTimedOut marks the request as timed out
func (r *InvokeRecord) SetTimedOut() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.timedOut = true
}

// IsExpired checks if the request has expired based on timeout
func (r *InvokeRecord) IsExpired() bool {
	return time.Since(r.CreatedAt) > r.Timeout
}

// Close closes the response channel
func (r *InvokeRecord) Close() {
	r.mu.Lock()
	defer r.mu.Unlock()
	select {
	case <-r.ResponseChan:
	default:
		close(r.ResponseChan)
	}
}

// TimeoutManager manages invoke request timeouts
type TimeoutManager struct {
	// records stores all active invoke records
	records map[string]*InvokeRecord
	// mu protects concurrent access
	mu sync.RWMutex
	// defaultTimeout is the default timeout for requests
	defaultTimeout time.Duration
	// cleanupInterval is the interval for cleaning up expired requests
	cleanupInterval time.Duration
	// stopChan signals the cleanup goroutine to stop
	stopChan chan struct{}
	// wg waits for cleanup goroutine to finish
	wg sync.WaitGroup
}

// TimeoutManagerConfig holds configuration for TimeoutManager
type TimeoutManagerConfig struct {
	// DefaultTimeout is the default timeout for requests
	DefaultTimeout time.Duration
	// CleanupInterval is the interval for cleaning up expired requests
	CleanupInterval time.Duration
}

// DefaultTimeoutManagerConfig returns default timeout manager configuration
func DefaultTimeoutManagerConfig() *TimeoutManagerConfig {
	return &TimeoutManagerConfig{
		DefaultTimeout:  30 * time.Second,
		CleanupInterval: 10 * time.Second,
	}
}

// NewTimeoutManager creates a new TimeoutManager
func NewTimeoutManager(config *TimeoutManagerConfig) *TimeoutManager {
	if config == nil {
		config = DefaultTimeoutManagerConfig()
	}

	m := &TimeoutManager{
		records:         make(map[string]*InvokeRecord),
		defaultTimeout:  config.DefaultTimeout,
		cleanupInterval: config.CleanupInterval,
		stopChan:        make(chan struct{}),
	}

	m.wg.Add(1)
	go m.cleanupLoop()

	return m
}

// cleanupLoop periodically cleans up expired requests
func (m *TimeoutManager) cleanupLoop() {
	defer m.wg.Done()

	ticker := time.NewTicker(m.cleanupInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			m.cleanupExpired()
		case <-m.stopChan:
			return
		}
	}
}

// cleanupExpired removes expired requests
func (m *TimeoutManager) cleanupExpired() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for id, record := range m.records {
		if record.IsExpired() {
			record.SetTimedOut()
			record.Close()
			delete(m.records, id)
		}
	}
}

// Add adds a new invoke record
func (m *TimeoutManager) Add(id, group, clientID string, data []byte) *InvokeRecord {
	m.mu.Lock()
	defer m.mu.Unlock()

	record := &InvokeRecord{
		ID:           id,
		Group:        group,
		ClientID:     clientID,
		Data:         data,
		CreatedAt:    time.Now(),
		Timeout:      m.defaultTimeout,
		ResponseChan: make(chan *InvokeResponse, 1),
	}

	m.records[id] = record
	return record
}

// Get gets an invoke record by ID
func (m *TimeoutManager) Get(id string) *InvokeRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.records[id]
}

// Remove removes an invoke record by ID
func (m *TimeoutManager) Remove(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if record, ok := m.records[id]; ok {
		record.Close()
		delete(m.records, id)
	}
}

// Complete completes an invoke request with a response
func (m *TimeoutManager) Complete(id string, response *InvokeResponse) bool {
	m.mu.RLock()
	record, ok := m.records[id]
	m.mu.RUnlock()

	if !ok {
		return false
	}

	// Check if already timed out
	if record.IsTimedOut() {
		return false
	}

	// Send response (non-blocking)
	select {
	case record.ResponseChan <- response:
		return true
	default:
		return false
	}
}

// Wait waits for a response with timeout
func (m *TimeoutManager) Wait(id string) (*InvokeResponse, error) {
	record := m.Get(id)
	if record == nil {
		return nil, ErrRecordNotFound
	}

	// Calculate remaining timeout
	remaining := record.Timeout - time.Since(record.CreatedAt)
	if remaining <= 0 {
		record.SetTimedOut()
		m.Remove(id)
		return nil, ErrTimeout
	}

	select {
	case response, ok := <-record.ResponseChan:
		if !ok {
			return nil, ErrChannelClosed
		}
		m.Remove(id)
		return response, nil
	case <-time.After(remaining):
		record.SetTimedOut()
		m.Remove(id)
		return nil, ErrTimeout
	}
}

// Shutdown shuts down the timeout manager
func (m *TimeoutManager) Shutdown() {
	close(m.stopChan)
	m.wg.Wait()

	// Close all remaining records
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, record := range m.records {
		record.Close()
	}
	m.records = make(map[string]*InvokeRecord)
}

// Count returns the number of active records
func (m *TimeoutManager) Count() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.records)
}

// Timeout errors
var (
	ErrTimeout        = &timeoutError{"request timeout"}
	ErrRecordNotFound = &timeoutError{"invoke record not found"}
	ErrChannelClosed  = &timeoutError{"response channel closed"}
)

type timeoutError struct {
	msg string
}

func (e *timeoutError) Error() string {
	return e.msg
}
