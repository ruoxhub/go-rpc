package router

import (
	"testing"

	"github.com/mrh30000/go-rpc/pkg/server/client"
)

func TestRouter_RouteBySpecifiedClient(t *testing.T) {
	router := NewRouter()
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
	router := NewRouter()
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
	router := NewRouter()
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
	router := NewRouter()
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
	router := NewRouter()
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
	router := NewRouter()

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
	router := NewRouter()
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
