package client

import (
	"sync"
	"time"

	"github.com/mrh30000/go-rpc/pkg/eventbus"
)

// defaultDebounceDuration 是客户端生命周期事件的默认去抖窗口。
// 高频上下线场景下 (group, clientID, eventType) 三元组在窗口内的多次触发只发布最后一次。
const defaultDebounceDuration = 10 * time.Millisecond

// debounceKey 标识一个去抖单元：同一客户端、同一事件类型在窗口内合并。
type debounceKey struct {
	group     string
	clientID  string
	eventType string
}

// debouncedEvent 持有 pending timer 与最新 payload。
type debouncedEvent struct {
	timer   *time.Timer
	payload interface{}
}

// ClientManager manages all RpcGroups
type ClientManager struct {
	groups   map[string]*RpcGroup
	mu       sync.RWMutex
	eventBus *eventbus.EventBus

	debounceMu       sync.Mutex
	debounceDuration time.Duration
	pendingEvents    map[debounceKey]*debouncedEvent
	stopped          bool
}

// NewClientManager creates a new ClientManager
func NewClientManager() *ClientManager {
	return &ClientManager{
		groups:           make(map[string]*RpcGroup),
		debounceDuration: defaultDebounceDuration,
		pendingEvents:    make(map[debounceKey]*debouncedEvent),
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

	m.publishDebounced(eventbus.EventClientConnect, client.Group, client.ClientID, func() interface{} {
		// 事件约定为值类型发布（见 docs/superpowers/specs/2026-06-28-arch-optimization-design.md），
		// 订阅方 SubscribeTyped[T] 为值类型 T，发指针会导致类型断言 panic。
		return eventbus.ClientConnectEvent{
			Group:     client.Group,
			ClientID:  client.ClientID,
			Timestamp: time.Now(),
		}
	})
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

	m.publishDebounced(eventbus.EventClientDisconnect, groupName, clientID, func() interface{} {
		return eventbus.ClientDisconnectEvent{
			Group:     groupName,
			ClientID:  clientID,
			Timestamp: time.Now(),
		}
	})
}

// publishDebounced 在 (group, clientID, eventType) 维度对事件发布做 trailing-only 去抖。
// 状态更新已经发生，这里只压制下游通知噪音。
// payloadFn 在每次调用时重新生成 payload，确保 timer 触发时的 Timestamp 反映最近一次事件时间。
func (m *ClientManager) publishDebounced(eventType, group, clientID string, payloadFn func() interface{}) {
	if m.eventBus == nil {
		return
	}

	key := debounceKey{group: group, clientID: clientID, eventType: eventType}
	payload := payloadFn()

	m.debounceMu.Lock()
	if m.stopped {
		m.debounceMu.Unlock()
		return
	}

	if existing, ok := m.pendingEvents[key]; ok {
		existing.payload = payload
		existing.timer.Reset(m.debounceDuration)
		m.debounceMu.Unlock()
		return
	}

	pending := &debouncedEvent{payload: payload}
	m.pendingEvents[key] = pending
	pending.timer = time.AfterFunc(m.debounceDuration, func() {
		m.debounceMu.Lock()
		current, ok := m.pendingEvents[key]
		if !ok || current != pending {
			m.debounceMu.Unlock()
			return
		}
		delete(m.pendingEvents, key)
		toPublish := current.payload
		bus := m.eventBus
		m.debounceMu.Unlock()

		if bus != nil {
			bus.Publish(eventType, toPublish)
		}
	})
	m.debounceMu.Unlock()
}

// Stop 取消所有待触发的去抖事件，丢弃未发布的最终事件。
// 设计为关停路径调用：状态更新链路独立，调用 Stop 后再调 CleanupAll。
// 多次调用是幂等的。
func (m *ClientManager) Stop() {
	m.debounceMu.Lock()
	defer m.debounceMu.Unlock()

	if m.stopped {
		return
	}
	m.stopped = true

	for key, pending := range m.pendingEvents {
		pending.timer.Stop()
		delete(m.pendingEvents, key)
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
