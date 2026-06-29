package forwarder

import (
	"sync"
	"time"
)

var streamPushTimeout = 5 * time.Second

// InvokeRecord tracks an in-flight invoke request.
type InvokeRecord struct {
	ID           string
	Group        string
	ClientID     string
	Data         []byte
	CreatedAt    time.Time
	Timeout      time.Duration
	ResponseChan chan *InvokeResponse
	timedOut     bool
	closed       bool
	closeOnce    sync.Once
	mu           sync.Mutex
}

// InvokeResponse holds the result of an invoke request.
type InvokeResponse struct {
	Data   []byte
	Error  string
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
	done      chan struct{}
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
	close(r.done)
	close(r.ChunkChan)
}

func (r *StreamRecord) TerminalError() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.closeErr
}

func (r *StreamRecord) Push(chunk *StreamChunk) (ok bool) {
	r.mu.Lock()
	if r.closed {
		r.mu.Unlock()
		return false
	}
	r.mu.Unlock()

	defer func() {
		if recover() != nil {
			ok = false
		}
	}()

	timer := time.NewTimer(streamPushTimeout)
	defer timer.Stop()
	select {
	case r.ChunkChan <- chunk:
		return true
	case <-r.done:
		return false
	case <-timer.C:
		r.SetTimedOut()
		r.CloseWithError("stream backpressure timeout")
		return false
	}
}

func (r *InvokeRecord) IsTimedOut() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.timedOut
}

func (r *InvokeRecord) SetTimedOut() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.timedOut = true
}

func (r *InvokeRecord) IsExpired() bool {
	return time.Since(r.CreatedAt) > r.Timeout
}

// Close 关闭响应 channel,多次调用安全。用 sync.Once 保证只关闭一次,
// 消除之前 select+default 写法在并发场景下的歧义。
func (r *InvokeRecord) Close() {
	r.closeOnce.Do(func() {
		r.mu.Lock()
		r.closed = true
		r.mu.Unlock()
		close(r.ResponseChan)
	})
}

// TimeoutManager tracks in-flight invoke and stream requests with timeout and cleanup.
type TimeoutManager struct {
	records         map[string]*InvokeRecord
	streams         map[string]*StreamRecord
	mu              sync.RWMutex
	defaultTimeout  time.Duration
	cleanupInterval time.Duration
	stopChan        chan struct{}
	wg              sync.WaitGroup
	shutdownOnce    sync.Once
}

// TimeoutManagerConfig holds configuration for TimeoutManager.
type TimeoutManagerConfig struct {
	DefaultTimeout  time.Duration
	CleanupInterval time.Duration
}

func DefaultTimeoutManagerConfig() *TimeoutManagerConfig {
	return &TimeoutManagerConfig{
		DefaultTimeout:  30 * time.Second,
		CleanupInterval: 10 * time.Second,
	}
}

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

func (m *TimeoutManager) Get(id string) *InvokeRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.records[id]
}

func (m *TimeoutManager) Remove(id string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if record, ok := m.records[id]; ok {
		record.Close()
		delete(m.records, id)
	}
}

func (m *TimeoutManager) Complete(id string, response *InvokeResponse) bool {
	m.mu.Lock()
	record, ok := m.records[id]
	if !ok {
		m.mu.Unlock()
		return false
	}

	if record.IsTimedOut() {
		m.mu.Unlock()
		return false
	}

	// Remove before sending so cleanup cannot race.
	delete(m.records, id)
	m.mu.Unlock()

	// Safe: we hold the only reference after delete.
	select {
	case record.ResponseChan <- response:
		return true
	default:
		return false
	}
}

func (m *TimeoutManager) Wait(id string) (*InvokeResponse, error) {
	record := m.Get(id)
	if record == nil {
		return nil, ErrRecordNotFound
	}

	remaining := record.Timeout - time.Since(record.CreatedAt)
	if remaining <= 0 {
		record.SetTimedOut()
		m.Remove(id)
		return nil, ErrTimeout
	}

	timer := time.NewTimer(remaining)
	defer timer.Stop()

	select {
	case response, ok := <-record.ResponseChan:
		if !ok {
			return nil, ErrChannelClosed
		}
		m.Remove(id)
		return response, nil
	case <-timer.C:
		record.SetTimedOut()
		m.Remove(id)
		return nil, ErrTimeout
	}
}

func (m *TimeoutManager) Shutdown() {
	m.shutdownOnce.Do(func() {
		close(m.stopChan)
		m.wg.Wait()
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
	})
}

func (m *TimeoutManager) Count() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.records)
}

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
		done:      make(chan struct{}),
	}
	m.streams[id] = record
	return record
}

func (m *TimeoutManager) GetStream(id string) *StreamRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.streams[id]
}

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

func (m *TimeoutManager) RemoveStream(id string) {
	_ = m.CompleteStream(id)
}

func (m *TimeoutManager) StreamCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.streams)
}

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
