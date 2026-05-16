package router

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/mrh30000/go-rpc/pkg/server/client"
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
	// HashKey is the key to use for consistent hashing (for ConsistentHash strategy).
	// If empty and ConstantInvoke is true, HashKey will be auto-built from Action + Payload.
	HashKey string
	// ConstantInvoke enables consistent hash routing when set to a truthy value ("true"/"1").
	// When enabled without an explicit HashKey, the key is built from Action + Payload.
	ConstantInvoke string
	// Action is the RPC action name, used to build the hash key when ConstantInvoke is enabled.
	Action string
	// Payload is the serializable request payload, used to build the hash key when ConstantInvoke is enabled.
	Payload interface{}
}

// cachedRing stores a hash ring alongside a fingerprint of the client list.
// The ring is reused as long as the client list fingerprint matches.
type cachedRing struct {
	ring        *ConsistentHashRing
	fingerprint string
}

// Router handles routing decisions using different strategies
type Router struct {
	// roundRobinCounter tracks per-group round-robin progress.
	roundRobinCounter map[string]*uint64
	mu                sync.Mutex
	// ringCache caches consistent hash rings per group, invalidated on client list change.
	ringCache map[string]*cachedRing
}

// NewRouter creates a new Router instance
func NewRouter() *Router {
	return &Router{
		roundRobinCounter: make(map[string]*uint64),
		ringCache:         make(map[string]*cachedRing),
	}
}

// Route selects a client from the group based on the routing strategy
// Priority: SpecifiedClient > ConsistentHash > RoundRobin
// If ClientID is specified, only that client is selected (no fallback)
// If ConstantInvoke is truthy (and no ClientID), uses consistent hash with round-robin fallback
// If HashKey is explicitly set (and no ClientID), uses consistent hash with round-robin fallback
// If neither is specified, uses round-robin
func (r *Router) Route(group *client.RpcGroup, params RouteParams) *client.RpcClient {
	if group == nil {
		return nil
	}

	// 1. If ClientID is specified, only try specified client (no fallback)
	if params.ClientID != "" {
		return r.routeBySpecifiedClient(group, params.ClientID)
	}

	// 2. Resolve hash key: if ConstantInvoke is enabled and no explicit HashKey, build it.
	hashKey := params.HashKey
	if hashKey == "" && shouldUseConsistentHash(params.ConstantInvoke) {
		hashKey = buildConsistentHashKey(params.GroupName, params.Action, params.Payload)
	}

	// 3. If hash key is available (explicit or auto-built), try consistent hash
	if hashKey != "" {
		if client := r.routeByConsistentHash(group, hashKey); client != nil {
			return client
		}
		// Fallback to round-robin if consistent hash returns nil
		return r.routeByRoundRobin(group)
	}

	// 4. Default to round-robin
	return r.routeByRoundRobin(group)
}

// routeBySpecifiedClient routes to a specific client by ID
func (r *Router) routeBySpecifiedClient(group *client.RpcGroup, clientID string) *client.RpcClient {
	return group.GetClient(clientID)
}

// routeByConsistentHash routes based on consistent hash of the key, with ring caching.
func (r *Router) routeByConsistentHash(group *client.RpcGroup, hashKey string) *client.RpcClient {
	// Get all clients from the group
	clients := group.GetAllClients()
	if len(clients) == 0 {
		return nil
	}

	// Build fingerprint from sorted client IDs to detect changes
	fingerprint := clientListFingerprint(clients)

	ring := r.getOrBuildRing(group.Name(), clients, fingerprint)

	// Get the target physical client ID from hash ring
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

// getOrBuildRing returns a cached ring if the fingerprint matches, otherwise rebuilds.
func (r *Router) getOrBuildRing(groupName string, clients []*client.RpcClient, fingerprint string) *ConsistentHashRing {
	r.mu.Lock()
	defer r.mu.Unlock()

	if cached, ok := r.ringCache[groupName]; ok && cached.fingerprint == fingerprint {
		return cached.ring
	}

	ring := NewConsistentHashRing()
	for _, c := range clients {
		ring.Add(c.ClientID)
	}

	r.ringCache[groupName] = &cachedRing{
		ring:        ring,
		fingerprint: fingerprint,
	}

	return ring
}

// InvalidateRingCache clears the cached hash ring for a specific group.
// Called when clients register/unregister to prevent stale routing.
func (r *Router) InvalidateRingCache(groupName string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.ringCache, groupName)
}

// InvalidateAllRingCaches clears all cached hash rings.
func (r *Router) InvalidateAllRingCaches() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.ringCache = make(map[string]*cachedRing)
}

// clientListFingerprint produces a deterministic hash of sorted client IDs.
func clientListFingerprint(clients []*client.RpcClient) string {
	ids := make([]string, len(clients))
	for i, c := range clients {
		ids[i] = c.ClientID
	}
	sort.Strings(ids)
	h := sha256.Sum256([]byte(strings.Join(ids, "|")))
	return fmt.Sprintf("%x", h[:8])
}

// routeByRoundRobin routes to clients in round-robin order
func (r *Router) routeByRoundRobin(group *client.RpcGroup) *client.RpcClient {
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

func filterEligibleClients(clients []*client.RpcClient, requireHealthy bool) []*client.RpcClient {
	filtered := make([]*client.RpcClient, 0, len(clients))
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

// shouldUseConsistentHash checks whether constant invoke (consistent hash) is enabled.
func shouldUseConsistentHash(value string) bool {
	if value == "" {
		return false
	}
	enabled, err := strconv.ParseBool(value)
	return err == nil && enabled
}

// buildConsistentHashKey builds a deterministic hash key from group, action, and payload.
func buildConsistentHashKey(groupName, action string, payload interface{}) string {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return groupName + ":" + action
	}
	return groupName + ":" + action + ":" + string(encoded)
}
