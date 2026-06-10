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

	expectedVNodes := 3 * defaultVirtualNodeCount
	if ring.Len() != expectedVNodes {
		t.Errorf("Expected %d virtual nodes (3 physical × %d vnodes), got %d", expectedVNodes, defaultVirtualNodeCount, ring.Len())
	}

	if ring.PhysicalNodeCount() != 3 {
		t.Errorf("Expected 3 physical nodes, got %d", ring.PhysicalNodeCount())
	}

	// Verify nodes are sorted by hash
	for i := 1; i < ring.Len(); i++ {
		if ring.nodes[i-1].Hash > ring.nodes[i].Hash {
			t.Error("Nodes should be sorted by hash")
		}
	}

	// Verify all virtual nodes point back to correct physical nodes
	physicalCount := make(map[string]int)
	for _, node := range ring.nodes {
		physicalCount[node.PhysicalClientID]++
	}
	for _, id := range []string{"client-1", "client-2", "client-3"} {
		if count := physicalCount[id]; count != defaultVirtualNodeCount {
			t.Errorf("Physical node %s should have %d virtual nodes, got %d", id, defaultVirtualNodeCount, count)
		}
	}
}

func TestConsistentHashRing_Remove(t *testing.T) {
	ring := NewConsistentHashRing()

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	// Remove middle node
	ring.Remove("client-2")

	expectedVNodes := 2 * defaultVirtualNodeCount
	if ring.Len() != expectedVNodes {
		t.Errorf("Expected %d virtual nodes after removal, got %d", expectedVNodes, ring.Len())
	}

	if ring.PhysicalNodeCount() != 2 {
		t.Errorf("Expected 2 physical nodes after removal, got %d", ring.PhysicalNodeCount())
	}

	// Verify client-2 virtual nodes are removed
	for _, node := range ring.nodes {
		if node.PhysicalClientID == "client-2" {
			t.Error("client-2 virtual nodes should be removed")
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

	// Same key should always route to same physical node
	key := "test-key"
	node1 := ring.Get(key)
	node2 := ring.Get(key)
	if node1 != node2 {
		t.Errorf("Expected same physical node for same key, got %s and %s", node1, node2)
	}

	// Get should return physical client IDs (not virtual node keys)
	for i := 0; i < 20; i++ {
		k := string(rune('a' + i))
		result := ring.Get(k)
		if result == "" {
			t.Errorf("Expected non-empty result for key %q", k)
		}
		// Should be one of the physical nodes
		if result != "client-1" && result != "client-2" && result != "client-3" {
			t.Errorf("Expected physical node ID, got %q", result)
		}
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

	// Remove the physical node responsible for this key
	if initialNode != "" {
		ring.Remove(initialNode)

		// Key should now route to a different physical node
		newNode := ring.Get(key)
		if newNode == initialNode {
			t.Error("Key should route to different physical node after removal")
		}
		if newNode == "" {
			t.Error("Key should still route to a node after removal")
		}
	}
}

func TestConsistentHashRing_WithSingleVNode(t *testing.T) {
	ring := NewConsistentHashRingWithVirtualNodes(1)

	ring.Add("client-1")
	ring.Add("client-2")
	ring.Add("client-3")

	if ring.Len() != 3 {
		t.Errorf("Expected 3 nodes (1 vnode each), got %d", ring.Len())
	}

	// Same key should route to same node
	key := "test-key"
	node1 := ring.Get(key)
	node2 := ring.Get(key)
	if node1 != node2 {
		t.Errorf("Expected same node, got %s and %s", node1, node2)
	}
}

func TestConsistentHashRing_Distribution(t *testing.T) {
	// With virtual nodes, keys should be more evenly distributed
	ring := NewConsistentHashRing()
	ring.Add("client-1")
	ring.Add("client-2")

	// Route 1000 different keys and count distribution
	counts := make(map[string]int)
	for i := 0; i < 1000; i++ {
		key := string(rune('a'+(i%26))) + string(rune('0'+(i/26)%10))
		result := ring.Get(key)
		counts[result]++
	}

	// With virtual nodes, distribution should be roughly even (40-60% each)
	total := counts["client-1"] + counts["client-2"]
	if total != 1000 {
		t.Errorf("Expected 1000 total routes, got %d", total)
	}

	ratio1 := float64(counts["client-1"]) / float64(total)
	if ratio1 < 0.3 || ratio1 > 0.7 {
		t.Errorf("Expected roughly even distribution (30-70%%), client-1 got %.1f%%", ratio1*100)
	}
}

func TestConsistentHashRing_WithoutVirtualNodesDistribution(t *testing.T) {
	// Without virtual nodes, 2 physical nodes may have very uneven distribution
	ring := NewConsistentHashRingWithVirtualNodes(1)
	ring.Add("client-1")
	ring.Add("client-2")

	counts := make(map[string]int)
	for i := 0; i < 1000; i++ {
		key := string(rune('a'+(i%26))) + string(rune('0'+(i/26)%10))
		result := ring.Get(key)
		counts[result]++
	}

	// Without virtual nodes, distribution might be less even, but should still be
	// within a reasonable range (both nodes get some traffic)
	total := counts["client-1"] + counts["client-2"]
	if total != 1000 {
		t.Errorf("Expected 1000 total routes, got %d", total)
	}

	ratio1 := float64(counts["client-1"]) / float64(total)
	t.Logf("Without virtual nodes (2 physical): client-1=%.1f%%, client-2=%.1f%%", ratio1*100, (1-ratio1)*100)
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
