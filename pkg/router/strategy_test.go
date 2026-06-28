package router

import (
	"testing"

	"github.com/mrh30000/go-rpc/pkg/client"
)

func TestRouter_RouteBySpecifiedClient(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册客户端
	c1 := client.NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(client.StatusOnline)
	group.Register(c1)

	c2 := client.NewRpcClient("test-group", "client-2", nil)
	c2.SetStatus(client.StatusOnline)
	group.Register(c2)

	// 指定客户端路由
	params := RouteParams{
		GroupName: "test-group",
		ClientID:  "client-1",
	}

	result := router.Route(group, params)
	if result == nil {
		t.Fatal("Expected client-1")
	}
	if result.ClientID != "client-1" {
		t.Errorf("Expected client-1, got %s", result.ClientID)
	}
}

func TestRouter_RouteBySpecifiedClient_NotFound(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册客户端
	c1 := client.NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(client.StatusOnline)
	group.Register(c1)

	// 指定不存在的客户端
	params := RouteParams{
		GroupName: "test-group",
		ClientID:  "non-existent",
	}

	result := router.Route(group, params)
	if result != nil {
		t.Errorf("Expected nil for non-existent client")
	}
}

func TestRouter_RouteByConsistentHash(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册客户端
	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	// 一致性哈希路由
	params := RouteParams{
		GroupName: "test-group",
		HashKey:   "test-key",
	}

	// 相同 key 应该总是路由到同一客户端
	result1 := router.Route(group, params)
	result2 := router.Route(group, params)

	if result1 == nil || result2 == nil {
		t.Fatal("Expected a client")
	}
	if result1.ClientID != result2.ClientID {
		t.Errorf("Expected same client, got %s and %s", result1.ClientID, result2.ClientID)
	}
}

func TestRouter_RouteByRoundRobin(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册 3 个客户端
	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	// 轮询路由
	params := RouteParams{
		GroupName: "test-group",
	}

	// 应该轮询所有客户端
	seen := make(map[string]bool)
	for i := 0; i < 6; i++ {
		result := router.Route(group, params)
		if result == nil {
			t.Fatal("Expected a client")
		}
		seen[result.ClientID] = true
	}

	// 应该至少见过 2 个不同的客户端（由于取模，可能是 3 个）
	if len(seen) < 2 {
		t.Errorf("Expected round-robin to cycle through clients, only saw %d unique", len(seen))
	}
}

func TestRouter_Route_Priority(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册客户端
	c1 := client.NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(client.StatusOnline)
	group.Register(c1)

	c2 := client.NewRpcClient("test-group", "client-2", nil)
	c2.SetStatus(client.StatusOnline)
	group.Register(c2)

	// 同时指定 ClientID 和 HashKey，应该优先使用 ClientID
	params := RouteParams{
		GroupName: "test-group",
		ClientID:  "client-1",
		HashKey:   "some-key",
	}

	result := router.Route(group, params)
	if result == nil {
		t.Fatal("Expected a client")
	}
	if result.ClientID != "client-1" {
		t.Errorf("Expected client-1 (specified), got %s", result.ClientID)
	}
}

func TestRouter_Route_NilGroup(t *testing.T) {
	router := NewRouter(nil)

	params := RouteParams{
		GroupName: "test-group",
		ClientID:  "client-1",
	}

	result := router.Route(nil, params)
	if result != nil {
		t.Error("Expected nil for nil group")
	}
}

func TestRouter_Route_EmptyGroup(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	params := RouteParams{
		GroupName: "test-group",
	}

	result := router.Route(group, params)
	if result != nil {
		t.Error("Expected nil for empty group")
	}
}

func TestRouter_RouteByConstantInvoke(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	// 注册客户端
	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	// 使用 ConstantInvoke 自动构建 hash key
	params := RouteParams{
		GroupName:      "test-group",
		ConstantInvoke: "true",
		Action:         "myAction",
		Payload:        map[string]string{"key": "value"},
	}

	// 相同参数应该总是路由到同一客户端
	result1 := router.Route(group, params)
	result2 := router.Route(group, params)

	if result1 == nil || result2 == nil {
		t.Fatal("Expected a client")
	}
	if result1.ClientID != result2.ClientID {
		t.Errorf("Expected same client for same ConstantInvoke params, got %s and %s", result1.ClientID, result2.ClientID)
	}

	// 不同 payload 可能路由到不同客户端
	params2 := RouteParams{
		GroupName:      "test-group",
		ConstantInvoke: "true",
		Action:         "myAction",
		Payload:        map[string]string{"key": "different"},
	}
	result3 := router.Route(group, params2)
	if result3 == nil {
		t.Fatal("Expected a client for different payload")
	}
}

func TestRouter_RouteByConstantInvoke_Disabled(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	// ConstantInvoke = "false" 应该使用 round-robin
	params := RouteParams{
		GroupName:      "test-group",
		ConstantInvoke: "false",
		Action:         "myAction",
		Payload:        map[string]string{"key": "value"},
	}

	// Round-robin 应该轮转
	seen := make(map[string]bool)
	for i := 0; i < 6; i++ {
		result := router.Route(group, params)
		if result == nil {
			t.Fatal("Expected a client")
		}
		seen[result.ClientID] = true
	}
	if len(seen) < 2 {
		t.Errorf("Expected round-robin to cycle, only saw %d unique", len(seen))
	}
}

func TestRouter_RingCache_Reuse(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	params := RouteParams{
		GroupName: "test-group",
		HashKey:   "test-key",
	}

	// First call builds the ring
	result1 := router.Route(group, params)
	if result1 == nil {
		t.Fatal("Expected a client")
	}

	// Verify ring is cached
	router.mu.Lock()
	cached, exists := router.ringCache["test-group"]
	router.mu.Unlock()

	if !exists {
		t.Fatal("Expected ring cache to exist after first route")
	}
	if cached == nil || cached.ring == nil {
		t.Fatal("Expected non-nil cached ring")
	}

	// Second call should reuse cached ring (same fingerprint)
	result2 := router.Route(group, params)
	if result2 == nil {
		t.Fatal("Expected a client")
	}
	if result1.ClientID != result2.ClientID {
		t.Errorf("Expected same client from cached ring, got %s and %s", result1.ClientID, result2.ClientID)
	}
}

func TestRouter_RingCache_Invalidation(t *testing.T) {
	router := NewRouter(nil)
	group := client.NewRpcGroup("test-group")
	defer group.Close()

	for i := 1; i <= 3; i++ {
		c := client.NewRpcClient("test-group", string(rune('a'+i-1)), nil)
		c.SetStatus(client.StatusOnline)
		group.Register(c)
	}

	params := RouteParams{
		GroupName: "test-group",
		HashKey:   "test-key",
	}

	// Build initial ring
	router.Route(group, params)

	// Invalidate cache
	router.InvalidateRingCache("test-group")

	router.mu.Lock()
	_, exists := router.ringCache["test-group"]
	router.mu.Unlock()

	if exists {
		t.Error("Expected ring cache to be invalidated")
	}
}

func TestRouter_RingCache_InvalidateAll(t *testing.T) {
	router := NewRouter(nil)
	group1 := client.NewRpcGroup("group-1")
	group2 := client.NewRpcGroup("group-2")
	defer group1.Close()
	defer group2.Close()

	c1 := client.NewRpcClient("group-1", "c1", nil)
	c1.SetStatus(client.StatusOnline)
	group1.Register(c1)

	c2 := client.NewRpcClient("group-2", "c2", nil)
	c2.SetStatus(client.StatusOnline)
	group2.Register(c2)

	// Build rings for both groups
	router.Route(group1, RouteParams{GroupName: "group-1", HashKey: "k1"})
	router.Route(group2, RouteParams{GroupName: "group-2", HashKey: "k2"})

	// Invalidate all
	router.InvalidateAllRingCaches()

	router.mu.Lock()
	count := len(router.ringCache)
	router.mu.Unlock()

	if count != 0 {
		t.Errorf("Expected 0 cached rings after InvalidateAll, got %d", count)
	}
}

func TestClientListFingerprint(t *testing.T) {
	clients1 := []*client.RpcClient{
		{ClientID: "a"},
		{ClientID: "b"},
		{ClientID: "c"},
	}
	clients2 := []*client.RpcClient{
		{ClientID: "c"},
		{ClientID: "a"},
		{ClientID: "b"},
	}

	// Same set of clients (different order) should produce same fingerprint
	fp1 := clientListFingerprint(clients1)
	fp2 := clientListFingerprint(clients2)
	if fp1 != fp2 {
		t.Errorf("Expected same fingerprint for same client set, got %s and %s", fp1, fp2)
	}

	// Different set should produce different fingerprint
	clients3 := []*client.RpcClient{
		{ClientID: "a"},
		{ClientID: "b"},
	}
	fp3 := clientListFingerprint(clients3)
	if fp1 == fp3 {
		t.Error("Expected different fingerprint for different client set")
	}
}

func TestShouldUseConsistentHash(t *testing.T) {
	tests := []struct {
		input    string
		expected bool
	}{
		{"", false},
		{"true", true},
		{"1", true},
		{"false", false},
		{"0", false},
		{"yes", false},
		{"no", false},
	}

	for _, tt := range tests {
		result := shouldUseConsistentHash(tt.input)
		if result != tt.expected {
			t.Errorf("shouldUseConsistentHash(%q) = %v, want %v", tt.input, result, tt.expected)
		}
	}
}

func TestBuildConsistentHashKey(t *testing.T) {
	// Same inputs should produce same key
	key1 := buildConsistentHashKey("group", "action", map[string]string{"k": "v"})
	key2 := buildConsistentHashKey("group", "action", map[string]string{"k": "v"})
	if key1 != key2 {
		t.Errorf("Expected same key, got %s and %s", key1, key2)
	}

	// Different payload should produce different key
	key3 := buildConsistentHashKey("group", "action", map[string]string{"k": "different"})
	if key1 == key3 {
		t.Error("Expected different key for different payload")
	}

	// Nil payload marshals to "null" (valid JSON), so key includes it
	key4 := buildConsistentHashKey("group", "action", nil)
	if key4 != "group:action:null" {
		t.Errorf("Expected 'group:action:null' for nil payload, got %s", key4)
	}
}
