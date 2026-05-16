package client

import (
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/pkg/server/transport"
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
	Group             string
	ClientID          string
	Connection        transport.Connection
	Status            ClientStatus
	LastActive        time.Time
	IsHealthy         bool
	FailCount         int
	OnHealthDegraded  func(client *RpcClient)
	mu                sync.RWMutex
	writeMu           sync.Mutex
}

// NewRpcClient creates a new RpcClient
func NewRpcClient(group, clientID string, conn transport.Connection) *RpcClient {
	return &RpcClient{
		Group:      group,
		ClientID:   clientID,
		Connection: conn,
		Status:     StatusConnected,
		LastActive: time.Now(),
		IsHealthy:  true,
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
		_ = c.Connection.Close()
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
	wasHealthy := c.IsHealthy
	c.FailCount++
	if c.FailCount >= 3 {
		c.IsHealthy = false
	}
	c.mu.Unlock()

	if wasHealthy && !c.IsHealthy && c.OnHealthDegraded != nil {
		c.OnHealthDegraded(c)
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
