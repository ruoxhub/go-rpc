package router

import (
	"testing"
)

func TestMurmurHash(t *testing.T) {
	// Verify same input produces same output
	h1 := murmurHash("test-key")
	h2 := murmurHash("test-key")
	if h1 != h2 {
		t.Errorf("Expected same hash, got %d and %d", h1, h2)
	}

	// Verify different inputs produce different hashes (most likely)
	h3 := murmurHash("different-key")
	if h1 == h3 {
		t.Error("Expected different hashes for different keys")
	}

	// Verify hash is non-zero
	if h1 == 0 {
		t.Error("Expected non-zero hash")
	}
}

func TestConsistentHashRing_Add(t *testing.T) {
	ring := NewConsistentHashRing()

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	if ring.Len() != 3 {
		t.Errorf("Expected 3 nodes, got %d", ring.Len())
	}

	// Verify nodes are sorted by hash
	if ring.nodes[0].Hash > ring.nodes[1].Hash {
		t.Error("Nodes should be sorted by hash")
	}
	if ring.nodes[1].Hash > ring.nodes[2].Hash {
		t.Error("Nodes should be sorted by hash")
	}
}

func TestConsistentHashRing_Remove(t *testing.T) {
	ring := NewConsistentHashRing()

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	// Remove middle node
	ring.Remove("client-2")

	if ring.Len() != 2 {
		t.Errorf("Expected 2 nodes after removal, got %d", ring.Len())
	}

	// Verify client-2 is removed
	for _, node := range ring.nodes {
		if node.ClientID == "client-2" {
			t.Error("client-2 should be removed")
		}
	}
}

func TestConsistentHashRing_Get(t *testing.T) {
	ring := NewConsistentHashRing()

	// Empty ring should return empty string
	result := ring.Get("test-key")
	if result != "" {
		t.Errorf("Expected empty string for empty ring, got %s", result)
	}

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	// Same key should always route to same node
	key := "test-key"
	node1 := ring.Get(key)
	node2 := ring.Get(key)
	if node1 != node2 {
		t.Errorf("Expected same node, got %s and %s", node1, node2)
	}

	// Different keys should (likely) route to different nodes
	node3 := ring.Get("different-key")
	if node3 == node1 {
		// This is technically okay due to hash collisions, but unlikely
		t.Log("Warning: Different keys routed to same node (hash collision)")
	}
}

func TestConsistentHashRing_WrapAround(t *testing.T) {
	ring := NewConsistentHashRing()

	ring.Add("client-1")

	// With only one node, all keys should route to it
	for i := 0; i < 10; i++ {
		key := string(rune('a' + i))
		result := ring.Get(key)
		if result != "client-1" {
			t.Errorf("Expected client-1, got %s", result)
		}
	}
}

func TestConsistentHashRing_Removal_Reroute(t *testing.T) {
	ring := NewConsistentHashRing()

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	key := "test-key"
	initialNode := ring.Get(key)

	// Remove the node responsible for this key
	if initialNode != "" {
		ring.Remove(initialNode)

		// Key should now route to a different node
		newNode := ring.Get(key)
		if newNode == initialNode {
			t.Error("Key should route to different node after removal")
		}
		if newNode == "" {
			t.Error("Key should still route to a node")
		}
	}
}

func TestHashKey_Exported(t *testing.T) {
	h1 := HashKey("test")
	h2 := HashKey("test")
	if h1 != h2 {
		t.Error("HashKey should produce consistent results")
	}

	h3 := HashKey("different")
	if h3 == 0 {
		t.Error("Hash should be non-zero")
	}
}
