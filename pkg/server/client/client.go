package client

import (
	"sync"
	"time"
)

// ClientStatus represents client connection status
type ClientStatus int

const (
	StatusConnected ClientStatus = iota
	StatusOnline
	StatusOffline
)

// RpcClient represents a connected Rpc client
type RpcClient struct {
	Group      string
	ClientID   string
	Connection interface{} // WebSocket connection handler or similar
	Status     ClientStatus
	LastActive time.Time
	// Health check fields
	IsHealthy bool // whether the client is healthy
	FailCount int  // consecutive failure count
	mu        sync.RWMutex
	writeMu   sync.Mutex // protects WebSocket writes from concurrent access
}

// NewRpcClient creates a new RpcClient
func NewRpcClient(group, clientID string, conn interface{}) *RpcClient {
	return &RpcClient{
		Group:      group,
		ClientID:   clientID,
		Connection: conn,
		Status:     StatusConnected,
		LastActive: time.Now(),
		IsHealthy:  true, // default to healthy
		FailCount:  0,
	}
}

// UpdateActive updates the last active timestamp
func (c *RpcClient) UpdateActive() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.LastActive = time.Now()
}

// SetStatus sets the client status
func (c *RpcClient) SetStatus(status ClientStatus) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.Status = status
}

// GetStatus returns the client status
func (c *RpcClient) GetStatus() ClientStatus {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.Status
}

// Close closes the client connection
func (c *RpcClient) Close() {
	if c.Connection != nil {
		// Type assertion to close the connection
		if closer, ok := c.Connection.(interface{ Close() error }); ok {
			_ = closer.Close()
		}
	}
}

// MarkSuccess marks a successful operation and resets failure count
func (c *RpcClient) MarkSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount = 0
	c.IsHealthy = true
}

// MarkFailure marks a failed operation and increments failure count
func (c *RpcClient) MarkFailure() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount++
	// Consider client unhealthy after 3 consecutive failures
	if c.FailCount >= 3 {
		c.IsHealthy = false
	}
}

// IsHealthy returns whether the client is healthy
func (c *RpcClient) GetHealthStatus() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.IsHealthy
}

// GetFailCount returns the current failure count
func (c *RpcClient) GetFailCount() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.FailCount
}

// ResetHealth resets the health status
func (c *RpcClient) ResetHealth() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount = 0
	c.IsHealthy = true
}

// AcquireWriteLock acquires the write lock for WebSocket operations
func (c *RpcClient) AcquireWriteLock() {
	c.writeMu.Lock()
}

// ReleaseWriteLock releases the write lock
func (c *RpcClient) ReleaseWriteLock() {
	c.writeMu.Unlock()
}

// GetWriteLock returns the write mutex for use with defer
func (c *RpcClient) GetWriteLock() *sync.Mutex {
	return &c.writeMu
}
