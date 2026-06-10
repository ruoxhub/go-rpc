package router

import (
	"fmt"
	"sort"
)

// defaultVirtualNodeCount is the default number of virtual nodes per physical node.
const defaultVirtualNodeCount = 5

// murmurHash implements a simple hash function similar to Java's MurmurHash
func murmurHash(key string) uint64 {
	const (
		seed = 0x123456789abcdef0
		m    = 0xc6a4a7935bd1e995
		r    = 47
	)

	var h uint64 = seed ^ (uint64(len(key)) * m)

	for i := 0; i < len(key)-len(key)%8; i += 8 {
		k := uint64(key[i]) | uint64(key[i+1])<<8 | uint64(key[i+2])<<16 | uint64(key[i+3])<<24 |
			uint64(key[i+4])<<32 | uint64(key[i+5])<<40 | uint64(key[i+6])<<48 | uint64(key[i+7])<<56

		k *= m
		k ^= k >> r
		k *= m

		h ^= k
		h *= m
	}

	// Handle remaining bytes (less than 8)
	remaining := len(key) % 8
	switch remaining {
	case 0:
	case 1:
		h ^= uint64(key[len(key)-1])
		h *= m
	case 2:
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	case 3:
		h ^= uint64(key[len(key)-3]) << 16
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	case 4:
		h ^= uint64(key[len(key)-4]) << 24
		h ^= uint64(key[len(key)-3]) << 16
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	case 5:
		h ^= uint64(key[len(key)-5]) << 32
		h ^= uint64(key[len(key)-4]) << 24
		h ^= uint64(key[len(key)-3]) << 16
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	case 6:
		h ^= uint64(key[len(key)-6]) << 40
		h ^= uint64(key[len(key)-5]) << 32
		h ^= uint64(key[len(key)-4]) << 24
		h ^= uint64(key[len(key)-3]) << 16
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	case 7:
		h ^= uint64(key[len(key)-7]) << 48
		h ^= uint64(key[len(key)-6]) << 40
		h ^= uint64(key[len(key)-5]) << 32
		h ^= uint64(key[len(key)-4]) << 24
		h ^= uint64(key[len(key)-3]) << 16
		h ^= uint64(key[len(key)-2]) << 8
		h ^= uint64(key[len(key)-1])
		h *= m
	}

	h ^= h >> r
	h *= m
	h ^= h >> r

	return h
}

// ConsistentHashNode represents a virtual node in the consistent hash ring.
// Each virtual node maps to a physical client via PhysicalClientID.
type ConsistentHashNode struct {
	Hash             uint64
	ClientID         string
	PhysicalClientID string
}

// ConsistentHashRing implements consistent hashing with virtual node support.
type ConsistentHashRing struct {
	nodes            []ConsistentHashNode
	virtualNodeCount int
}

// NewConsistentHashRing creates a new consistent hash ring with default virtual node count.
func NewConsistentHashRing() *ConsistentHashRing {
	return &ConsistentHashRing{
		nodes:            make([]ConsistentHashNode, 0),
		virtualNodeCount: defaultVirtualNodeCount,
	}
}

// NewConsistentHashRingWithVirtualNodes creates a new consistent hash ring with the specified
// number of virtual nodes per physical node. Use vnodeCount=1 to disable virtual nodes
// (one physical node = one ring entry).
func NewConsistentHashRingWithVirtualNodes(vnodeCount int) *ConsistentHashRing {
	if vnodeCount < 1 {
		vnodeCount = 1
	}
	return &ConsistentHashRing{
		nodes:            make([]ConsistentHashNode, 0),
		virtualNodeCount: vnodeCount,
	}
}

// virtualNodeKey generates a deterministic virtual node key for a given physical client ID
// and virtual node index.
func virtualNodeKey(clientID string, idx int) string {
	return fmt.Sprintf("%s:v%d", clientID, idx)
}

// Add adds a physical client to the ring, creating virtualNodeCount virtual nodes.
func (r *ConsistentHashRing) Add(clientID string) {
	for i := 0; i < r.virtualNodeCount; i++ {
		vKey := virtualNodeKey(clientID, i)
		hash := murmurHash(vKey)
		r.nodes = append(r.nodes, ConsistentHashNode{
			Hash:             hash,
			ClientID:         vKey,
			PhysicalClientID: clientID,
		})
	}
	// Keep sorted by hash
	sort.Slice(r.nodes, func(i, j int) bool {
		return r.nodes[i].Hash < r.nodes[j].Hash
	})
}

// Remove removes all virtual nodes for a physical client from the ring.
func (r *ConsistentHashRing) Remove(clientID string) {
	filtered := make([]ConsistentHashNode, 0, len(r.nodes))
	for _, node := range r.nodes {
		if node.PhysicalClientID != clientID {
			filtered = append(filtered, node)
		}
	}
	r.nodes = filtered
}

// Get returns the physical client ID responsible for the key.
func (r *ConsistentHashRing) Get(key string) string {
	if len(r.nodes) == 0 {
		return ""
	}

	hash := murmurHash(key)

	// Binary search for first node >= hash
	idx := sort.Search(len(r.nodes), func(i int) bool {
		return r.nodes[i].Hash >= hash
	})

	// If not found, wrap around to first node
	if idx >= len(r.nodes) {
		idx = 0
	}

	return r.nodes[idx].PhysicalClientID
}

// Len returns the total number of virtual nodes in the ring.
func (r *ConsistentHashRing) Len() int {
	return len(r.nodes)
}

// PhysicalNodeCount returns the number of unique physical clients in the ring.
func (r *ConsistentHashRing) PhysicalNodeCount() int {
	seen := make(map[string]struct{})
	for _, node := range r.nodes {
		seen[node.PhysicalClientID] = struct{}{}
	}
	return len(seen)
}

// HashKey returns the hash value for a key (for testing)
func HashKey(key string) uint64 {
	return murmurHash(key)
}
