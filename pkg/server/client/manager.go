package client

import (
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/pkg/eventbus"
)

// ClientManager manages all RpcGroups
type ClientManager struct {
	groups   map[string]*RpcGroup
	mu       sync.RWMutex
	eventBus *eventbus.EventBus
}

// NewClientManager creates a new ClientManager
func NewClientManager() *ClientManager {
	return &ClientManager{
		groups: make(map[string]*RpcGroup),
	}
}

// SetEventBus sets the event bus for publishing client lifecycle events.
// If nil, events are not published.
func (m *ClientManager) SetEventBus(eb *eventbus.EventBus) {
	m.eventBus = eb
}

// getOrCreateGroup gets or creates a group
func (m *ClientManager) getOrCreateGroup(groupName string) *RpcGroup {
	m.mu.RLock()
	group, ok := m.groups[groupName]
	m.mu.RUnlock()

	if ok {
		return group
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	// Double-check after acquiring write lock
	if group, ok := m.groups[groupName]; ok {
		return group
	}

	group = NewRpcGroup(groupName)
	m.groups[groupName] = group
	return group
}

// Register registers a client
func (m *ClientManager) Register(client *RpcClient) {
	group := m.getOrCreateGroup(client.Group)
	group.Register(client)

	if m.eventBus != nil {
		m.eventBus.Publish(eventbus.EventClientConnect, &eventbus.ClientConnectEvent{
			Group:     client.Group,
			ClientID:  client.ClientID,
			Timestamp: time.Now(),
		})
	}
}

// Unregister unregisters a client
func (m *ClientManager) Unregister(groupName, clientID string) {
	m.mu.RLock()
	group, ok := m.groups[groupName]
	m.mu.RUnlock()

	if ok {
		group.Unregister(clientID)
		if group.ClientCount() == 0 {
			m.mu.Lock()
			delete(m.groups, groupName)
			m.mu.Unlock()
			group.Close()
		}
	}

	if m.eventBus != nil {
		m.eventBus.Publish(eventbus.EventClientDisconnect, &eventbus.ClientDisconnectEvent{
			Group:     groupName,
			ClientID:  clientID,
			Timestamp: time.Now(),
		})
	}
}

// GetClient gets a client by group and clientID
func (m *ClientManager) GetClient(group, clientID string) *RpcClient {
	m.mu.RLock()
	groupInst, ok := m.groups[group]
	m.mu.RUnlock()

	if !ok {
		return nil
	}
	return groupInst.GetClient(clientID)
}

// GetClientsByGroup gets all clients in a group
func (m *ClientManager) GetClientsByGroup(group string) []*RpcClient {
	m.mu.RLock()
	groupInst, ok := m.groups[group]
	m.mu.RUnlock()

	if !ok {
		return nil
	}
	return groupInst.GetAllClients()
}

// GetAllGroups returns all group names
func (m *ClientManager) GetAllGroups() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	groups := make([]string, 0, len(m.groups))
	for name := range m.groups {
		groups = append(groups, name)
	}
	return groups
}

// AllocateClient allocates a client for invocation
func (m *ClientManager) AllocateClient(group string) *RpcClient {
	groupInst := m.getOrCreateGroup(group)
	return groupInst.AllocateClient()
}

// CleanupAll cleans up all clients
func (m *ClientManager) CleanupAll() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for _, group := range m.groups {
		group.Close()
	}
	m.groups = make(map[string]*RpcGroup)
}

// GroupCount returns the number of groups
func (m *ClientManager) GroupCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.groups)
}

// ClientCount returns the total number of clients
func (m *ClientManager) ClientCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()

	count := 0
	for _, group := range m.groups {
		count += group.ClientCount()
	}
	return count
}

// GetGroup gets a group by name
func (m *ClientManager) GetGroup(groupName string) *RpcGroup {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.groups[groupName]
}

// HasGroup checks if a group exists
func (m *ClientManager) HasGroup(groupName string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	_, ok := m.groups[groupName]
	return ok
}
