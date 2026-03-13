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

// SekiroClient represents a connected Sekiro client
type SekiroClient struct {
	Group      string
	ClientID   string
	Connection interface{} // WebSocket connection handler or similar
	Status     ClientStatus
	LastActive time.Time
	// Health check fields
	IsHealthy bool // whether the client is healthy
	FailCount int  // consecutive failure count
	mu        sync.RWMutex
}

// NewSekiroClient creates a new SekiroClient
func NewSekiroClient(group, clientID string, conn interface{}) *SekiroClient {
	return &SekiroClient{
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
func (c *SekiroClient) UpdateActive() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.LastActive = time.Now()
}

// SetStatus sets the client status
func (c *SekiroClient) SetStatus(status ClientStatus) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.Status = status
}

// GetStatus returns the client status
func (c *SekiroClient) GetStatus() ClientStatus {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.Status
}

// Close closes the client connection
func (c *SekiroClient) Close() {
	if c.Connection != nil {
		// Type assertion to close the connection
		if closer, ok := c.Connection.(interface{ Close() error }); ok {
			_ = closer.Close()
		}
	}
}

// MarkSuccess marks a successful operation and resets failure count
func (c *SekiroClient) MarkSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount = 0
	c.IsHealthy = true
}

// MarkFailure marks a failed operation and increments failure count
func (c *SekiroClient) MarkFailure() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount++
	// Consider client unhealthy after 3 consecutive failures
	if c.FailCount >= 3 {
		c.IsHealthy = false
	}
}

// IsHealthy returns whether the client is healthy
func (c *SekiroClient) GetHealthStatus() bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.IsHealthy
}

// GetFailCount returns the current failure count
func (c *SekiroClient) GetFailCount() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.FailCount
}

// ResetHealth resets the health status
func (c *SekiroClient) ResetHealth() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.FailCount = 0
	c.IsHealthy = true
}
