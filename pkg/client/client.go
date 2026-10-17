package client

import (
	"sort"
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
	protocolVersion int
	capabilities    map[string]struct{}
	executorType    string
}

// SetProtocol stores the negotiated protocol metadata.
func (c *RpcClient) SetProtocol(version int, capabilities []string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.protocolVersion = version
	c.capabilities = make(map[string]struct{}, len(capabilities))
	for _, capability := range capabilities {
		c.capabilities[capability] = struct{}{}
	}
}

// ProtocolVersion returns the negotiated protocol version.
func (c *RpcClient) ProtocolVersion() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.protocolVersion
}

// Capabilities returns a sorted copy of the negotiated capabilities.
func (c *RpcClient) Capabilities() []string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	capabilities := make([]string, 0, len(c.capabilities))
	for capability := range c.capabilities {
		capabilities = append(capabilities, capability)
	}
	sort.Strings(capabilities)
	return capabilities
}

// SupportsCapability reports whether the client negotiated a capability.
func (c *RpcClient) SupportsCapability(capability string) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	_, ok := c.capabilities[capability]
	return ok
}

// NewRpcClient creates a new RpcClient
func NewRpcClient(group, clientID string, conn transport.Connection) *RpcClient {
	return &RpcClient{
		Group:      group,
		ClientID:   clientID,
		Connection: conn,
		Status:     StatusConnected,
		LastActive: time.Now(),
		cb:         NewCircuitBreaker(3, 15*time.Second),
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

// SetExecutorType sets the executor type of the client (e.g., "browser", "python").
func (c *RpcClient) SetExecutorType(executorType string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.executorType = executorType
}

// GetExecutorType returns the executor type of the client.
func (c *RpcClient) GetExecutorType() string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.executorType
}
