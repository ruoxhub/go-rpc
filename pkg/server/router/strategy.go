package router

import (
	"sync"
	"sync/atomic"

	"github.com/sekiro-go/sekiro-go/pkg/server/client"
)

// RoutingStrategy defines the routing strategy type
type RoutingStrategy int

const (
	// RoundRobin routes to clients in round-robin order
	RoundRobin RoutingStrategy = iota
	// SpecifiedClient routes to a specific client by ID
	SpecifiedClient
	// ConsistentHash routes based on consistent hash of a key
	ConsistentHash
)

// RouteParams holds parameters for routing decisions
type RouteParams struct {
	// GroupName is the target group name
	GroupName string
	// ClientID is the specific client ID (for SpecifiedClient strategy)
	ClientID string
	// HashKey is the key to use for consistent hashing (for ConsistentHash strategy)
	HashKey string
}

// Router handles routing decisions using different strategies
type Router struct {
	// roundRobinCounter tracks per-group round-robin progress.
	roundRobinCounter map[string]*uint64
	mu                sync.Mutex
}

// NewRouter creates a new Router instance
func NewRouter() *Router {
	return &Router{
		roundRobinCounter: make(map[string]*uint64),
	}
}

// Route selects a client from the group based on the routing strategy
// Priority: SpecifiedClient > ConsistentHash > RoundRobin
// If ClientID is specified, only that client is selected (no fallback)
// If HashKey is specified without ClientID, uses consistent hash with round-robin fallback
// If neither is specified, uses round-robin
func (r *Router) Route(group *client.SekiroGroup, params RouteParams) *client.SekiroClient {
	if group == nil {
		return nil
	}

	// 1. If ClientID is specified, only try specified client (no fallback)
	if params.ClientID != "" {
		return r.routeBySpecifiedClient(group, params.ClientID)
	}

	// 2. If HashKey is specified, try consistent hash
	if params.HashKey != "" {
		if client := r.routeByConsistentHash(group, params.HashKey); client != nil {
			return client
		}
		// Fallback to round-robin if consistent hash returns nil
		return r.routeByRoundRobin(group)
	}

	// 3. Default to round-robin
	return r.routeByRoundRobin(group)
}

// routeBySpecifiedClient routes to a specific client by ID
func (r *Router) routeBySpecifiedClient(group *client.SekiroGroup, clientID string) *client.SekiroClient {
	return group.GetClient(clientID)
}

// routeByConsistentHash routes based on consistent hash of the key
func (r *Router) routeByConsistentHash(group *client.SekiroGroup, hashKey string) *client.SekiroClient {
	// Get all clients from the group
	clients := group.GetAllClients()
	if len(clients) == 0 {
		return nil
	}

	// Build a hash ring for current clients
	ring := NewConsistentHashRing()
	for _, c := range clients {
		ring.Add(c.ClientID)
	}

	// Get the target client ID from hash ring
	targetID := ring.Get(hashKey)
	if targetID == "" {
		return nil
	}

	selected := group.GetClient(targetID)
	if selected == nil {
		return nil
	}
	if selected.GetStatus() != client.StatusOnline {
		return nil
	}
	return selected
}

// routeByRoundRobin routes to clients in round-robin order
func (r *Router) routeByRoundRobin(group *client.SekiroGroup) *client.SekiroClient {
	clients := group.GetAllClients()
	if len(clients) == 0 {
		return nil
	}

	eligible := filterEligibleClients(clients, true)
	if len(eligible) == 0 {
		eligible = filterEligibleClients(clients, false)
	}
	if len(eligible) == 0 {
		eligible = clients
	}

	counter := r.counterForGroup(group.Name())
	index := int(atomic.AddUint64(counter, 1)-1) % len(eligible)

	return eligible[index]
}

func filterEligibleClients(clients []*client.SekiroClient, requireHealthy bool) []*client.SekiroClient {
	filtered := make([]*client.SekiroClient, 0, len(clients))
	for _, c := range clients {
		if c.GetStatus() != client.StatusOnline {
			continue
		}
		if requireHealthy && !c.GetHealthStatus() {
			continue
		}
		filtered = append(filtered, c)
	}
	return filtered
}

func (r *Router) counterForGroup(groupName string) *uint64 {
	r.mu.Lock()
	defer r.mu.Unlock()

	if counter, ok := r.roundRobinCounter[groupName]; ok {
		return counter
	}

	counter := new(uint64)
	r.roundRobinCounter[groupName] = counter
	return counter
}
