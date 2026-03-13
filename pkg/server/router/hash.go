package router

import (
	"sort"
)

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
		// Empty or exact multiple of 8 - nothing to add
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

// ConsistentHashNode represents a node in consistent hash ring
type ConsistentHashNode struct {
	Hash     uint64
	ClientID string
}

// ConsistentHashRing implements consistent hashing
type ConsistentHashRing struct {
	nodes []ConsistentHashNode
}

// NewConsistentHashRing creates a new consistent hash ring
func NewConsistentHashRing() *ConsistentHashRing {
	return &ConsistentHashRing{
		nodes: make([]ConsistentHashNode, 0),
	}
}

// Add adds a node to the ring
func (r *ConsistentHashRing) Add(clientID string) {
	hash := murmurHash(clientID)
	r.nodes = append(r.nodes, ConsistentHashNode{
		Hash:     hash,
		ClientID: clientID,
	})
	// Keep sorted by hash
	sort.Slice(r.nodes, func(i, j int) bool {
		return r.nodes[i].Hash < r.nodes[j].Hash
	})
}

// Remove removes a node from the ring
func (r *ConsistentHashRing) Remove(clientID string) {
	for i, node := range r.nodes {
		if node.ClientID == clientID {
			r.nodes = append(r.nodes[:i], r.nodes[i+1:]...)
			break
		}
	}
}

// Get returns the node responsible for the key
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

	return r.nodes[idx].ClientID
}

// Len returns the number of nodes in the ring
func (r *ConsistentHashRing) Len() int {
	return len(r.nodes)
}

// HashKey returns the hash value for a key (for testing)
func HashKey(key string) uint64 {
	return murmurHash(key)
}
