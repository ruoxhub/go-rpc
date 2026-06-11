package client

import (
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/pkg/transport"
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
	Group           string
	ClientID        string
	Connection      transport.Connection
	Status          ClientStatus
	LastActive      time.Time
	RegisteredGroup bool
	cb              *CircuitBreaker
	mu              sync.RWMutex
	writeMu         sync.Mutex
}

// NewRpcClient creates a new RpcClient
func NewRpcClient(group, clientID string, conn transport.Connection) *RpcClient {
	return &RpcClient{
		Group:      group,
		ClientID:   clientID,
		Connection: conn,
		Status:     StatusConnected,
		LastActive: time.Now(),
		cb:         NewCircuitBreaker(3, 30*time.Second),
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

// GetLastActive returns the last activity timestamp.
func (c *RpcClient) GetLastActive() time.Time {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.LastActive
}

// SetRegisteredGroup records whether the client belongs to a configured group.
func (c *RpcClient) SetRegisteredGroup(registered bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.RegisteredGroup = registered
}

// IsRegisteredGroup returns whether the client belongs to a configured group.
func (c *RpcClient) IsRegisteredGroup() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.RegisteredGroup
}

// Close closes the client connection
func (c *RpcClient) Close() {
	if c.Connection != nil {
		_ = c.Connection.Close()
	}
}

// MarkSuccess marks a successful operation and resets failure count
func (c *RpcClient) MarkSuccess() {
	c.cb.RecordSuccess()
}

// MarkFailure marks a failed operation and increments failure count
func (c *RpcClient) MarkFailure() {
	c.cb.RecordFailure()
}

// GetHealthStatus returns whether the client is healthy (circuit not open)
func (c *RpcClient) GetHealthStatus() bool {
	return c.cb.State() != CircuitOpen
}

// GetFailCount returns the current failure count
func (c *RpcClient) GetFailCount() int {
	return c.cb.FailureCount()
}

// SetCircuitBreakerCallback sets a callback for circuit breaker state changes.
func (c *RpcClient) SetCircuitBreakerCallback(fn func(from, to CircuitState)) {
	c.cb.OnStateChange = fn
}
