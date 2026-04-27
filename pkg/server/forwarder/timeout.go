package forwarder

import (
	"sync"
	"time"
)

var streamPushTimeout = 5 * time.Second

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

// StreamChunk represents one streaming response chunk.
type StreamChunk struct {
	Data   []byte
	Error  string
	Status int
	Done   bool
}

// StreamRecord tracks a streaming invoke request.
type StreamRecord struct {
	ID        string
	Group     string
	ClientID  string
	CreatedAt time.Time
	Timeout   time.Duration
	ChunkChan chan *StreamChunk
	timedOut  bool
	closed    bool
	closeErr  string
	mu        sync.Mutex
}

func (r *StreamRecord) IsExpired() bool {
	return time.Since(r.CreatedAt) > r.Timeout
}

func (r *StreamRecord) SetTimedOut() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.timedOut = true
}

func (r *StreamRecord) Close() {
	r.CloseWithError("")
}

func (r *StreamRecord) CloseWithError(err string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closed {
		return
	}
	r.closed = true
	r.closeErr = err
	close(r.ChunkChan)
}

func (r *StreamRecord) TerminalError() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.closeErr
}

func (r *StreamRecord) Push(chunk *StreamChunk) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closed {
		return false
	}
	timer := time.NewTimer(streamPushTimeout)
	defer timer.Stop()
	select {
	case r.ChunkChan <- chunk:
		return true
	case <-timer.C:
		r.closed = true
		r.closeErr = "stream backpressure timeout"
		close(r.ChunkChan)
		return false
	}
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
	// streams stores all active stream records
	streams map[string]*StreamRecord
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
		streams:         make(map[string]*StreamRecord),
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
	for id, stream := range m.streams {
		if stream.IsExpired() {
			stream.SetTimedOut()
			stream.Close()
			delete(m.streams, id)
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
	m.mu.Lock()
	record, ok := m.records[id]
	if !ok {
		m.mu.Unlock()
		return false
	}

	// Check if already timed out
	if record.IsTimedOut() {
		m.mu.Unlock()
		return false
	}

	// Remove record under write lock to prevent concurrent cleanup
	delete(m.records, id)
	m.mu.Unlock()

	// Send response (safe now since we hold the only reference)
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
	for _, stream := range m.streams {
		stream.Close()
	}
	m.records = make(map[string]*InvokeRecord)
	m.streams = make(map[string]*StreamRecord)
}

// Count returns the number of active records
func (m *TimeoutManager) Count() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.records)
}

// RegisterStream registers a streaming invoke request.
func (m *TimeoutManager) RegisterStream(id, group, clientID string, timeout time.Duration) *StreamRecord {
	m.mu.Lock()
	defer m.mu.Unlock()

	if timeout <= 0 {
		timeout = m.defaultTimeout
	}

	record := &StreamRecord{
		ID:        id,
		Group:     group,
		ClientID:  clientID,
		CreatedAt: time.Now(),
		Timeout:   timeout,
		ChunkChan: make(chan *StreamChunk, 16),
	}
	m.streams[id] = record
	return record
}

// GetStream gets a stream record by ID.
func (m *TimeoutManager) GetStream(id string) *StreamRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.streams[id]
}

// PushStreamChunk sends a chunk to a registered stream.
func (m *TimeoutManager) PushStreamChunk(id string, chunk *StreamChunk) bool {
	m.mu.RLock()
	record := m.streams[id]
	m.mu.RUnlock()
	if record == nil {
		return false
	}
	if record.Push(chunk) {
		return true
	}
	m.mu.Lock()
	if m.streams[id] == record {
		delete(m.streams, id)
	}
	m.mu.Unlock()
	return false
}

// CompleteStream closes and removes a registered stream.
func (m *TimeoutManager) CompleteStream(id string) bool {
	m.mu.Lock()
	record, ok := m.streams[id]
	if ok {
		delete(m.streams, id)
	}
	m.mu.Unlock()
	if !ok {
		return false
	}
	record.Close()
	return true
}

// RemoveStream removes a stream record by ID.
func (m *TimeoutManager) RemoveStream(id string) {
	_ = m.CompleteStream(id)
}

// StreamCount returns the number of active stream records.
func (m *TimeoutManager) StreamCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.streams)
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
