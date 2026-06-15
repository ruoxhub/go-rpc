package client

import (
	"testing"
)

func TestRpcGroup_Register(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	client := NewRpcClient("test-group", "client-1", nil)

	// 注册客户端
	group.Register(client)

	// 使用 GetClient 来等待异步注册完成
	registered := group.GetClient("client-1")
	if registered == nil {
		t.Fatal("Client not registered")
	}
	if registered.ClientID != "client-1" {
		t.Errorf("Expected client-1, got %s", registered.ClientID)
	}
}

func TestRpcGroup_Unregister(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	client := NewRpcClient("test-group", "client-1", nil)
	group.Register(client)

	// 使用 GetClient 验证注册成功
	registered := group.GetClient("client-1")
	if registered == nil {
		t.Fatal("Client should be registered")
	}

	// 注销客户端
	group.Unregister("client-1")

	// 验证注销成功
	registered = group.GetClient("client-1")
	if registered != nil {
		t.Error("Client should be unregistered")
	}
}

func TestRpcGroup_GetAllClients(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	// 注册多个客户端
	group.Register(NewRpcClient("test-group", "client-1", nil))
	group.Register(NewRpcClient("test-group", "client-2", nil))
	group.Register(NewRpcClient("test-group", "client-3", nil))

	// 获取所有客户端
	clients := group.GetAllClients()
	if len(clients) != 3 {
		t.Errorf("Expected 3 clients, got %d", len(clients))
	}
}

func TestRpcGroup_AllocateClient(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	// 空组应该返回 nil
	client := group.AllocateClient()
	if client != nil {
		t.Error("Expected nil for empty group")
	}

	// 注册客户端
	c1 := NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(StatusOnline)
	group.Register(c1)

	c2 := NewRpcClient("test-group", "client-2", nil)
	c2.SetStatus(StatusOffline)
	group.Register(c2)

	// 应该返回在线客户端
	allocated := group.AllocateClient()
	if allocated == nil {
		t.Fatal("Expected a client")
	}
	if allocated.ClientID != "client-1" {
		t.Errorf("Expected client-1 (online), got %s", allocated.ClientID)
	}
}

func TestRpcGroup_Name(t *testing.T) {
	group := NewRpcGroup("my-group")
	defer group.Close()

	if group.Name() != "my-group" {
		t.Errorf("Expected name 'my-group', got '%s'", group.Name())
	}
}

func TestRpcGroup_ClientCount(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	if group.ClientCount() != 0 {
		t.Error("Expected 0 clients for new group")
	}

	group.Register(NewRpcClient("test-group", "client-1", nil))
	group.Register(NewRpcClient("test-group", "client-2", nil))

	// 使用 GetAllClients 来验证
	clients := group.GetAllClients()
	if len(clients) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(clients))
	}
}

func TestRpcGroup_Close(t *testing.T) {
	group := NewRpcGroup("test-group")

	client := NewRpcClient("test-group", "client-1", nil)
	group.Register(client)

	// 验证注册成功
	if group.GetClient("client-1") == nil {
		t.Fatal("Client should be registered")
	}

	group.Close()

	// 关闭后注册应该无效（使用 Close 的 group）
	group.Register(NewRpcClient("test-group", "client-2", nil))

	// 验证 client-2 没有注册成功
	if group.HasClient("client-2") {
		t.Error("New client should not be registered after close")
	}
}

func TestRpcGroup_HasClient(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	if group.HasClient("client-1") {
		t.Error("Expected false for non-existent client")
	}

	group.Register(NewRpcClient("test-group", "client-1", nil))

	if !group.HasClient("client-1") {
		t.Error("Expected true for existing client")
	}
}

func TestRpcGroup_AllocateClient_RoundRobinOrder(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	for _, id := range []string{"A", "B", "C"} {
		c := NewRpcClient("test-group", id, nil)
		c.SetStatus(StatusOnline)
		group.Register(c)
	}

	// 前 3 次：A → B → C（每次取队头、旋转到队尾）
	for _, want := range []string{"A", "B", "C"} {
		got := group.AllocateClient()
		if got == nil || got.ClientID != want {
			t.Fatalf("expected %s, got %v", want, got)
		}
	}
	// 再来一轮验证循环：A → B → C
	for _, want := range []string{"A", "B", "C"} {
		got := group.AllocateClient()
		if got == nil || got.ClientID != want {
			t.Fatalf("second round: expected %s, got %v", want, got)
		}
	}
}

func TestRpcGroup_AllocateClient_SkipsUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c1 := NewRpcClient("test-group", "A", nil)
	c1.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c1.MarkFailure() // 触发熔断器打开
	}
	group.Register(c1)

	c2 := NewRpcClient("test-group", "B", nil)
	c2.SetStatus(StatusOnline)
	group.Register(c2)

	// A 不健康，总是轮到 B
	for i := 0; i < 3; i++ {
		got := group.AllocateClient()
		if got == nil || got.ClientID != "B" {
			t.Fatalf("iteration %d: expected B, got %v", i, got)
		}
	}
}

func TestRpcGroup_AllocateClient_FallbackToUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c1 := NewRpcClient("test-group", "A", nil)
	c1.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c1.MarkFailure()
	}
	group.Register(c1)

	c2 := NewRpcClient("test-group", "B", nil)
	c2.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c2.MarkFailure()
	}
	group.Register(c2)

	// 所有客户端都不健康，但仍能分配（兜底行为）
	got := group.AllocateClient()
	if got == nil {
		t.Fatal("expected a fallback client, got nil")
	}
	if got.ClientID != "A" && got.ClientID != "B" {
		t.Fatalf("unexpected client: %s", got.ClientID)
	}
}

func TestRpcGroup_FindClientByFuzzy_HealthFirst(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	abcUnhealthy := NewRpcClient("test-group", "client-abc-1", nil)
	abcUnhealthy.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		abcUnhealthy.MarkFailure()
	}
	group.Register(abcUnhealthy)

	abcHealthy := NewRpcClient("test-group", "client-abc-2", nil)
	abcHealthy.SetStatus(StatusOnline)
	group.Register(abcHealthy)

	other := NewRpcClient("test-group", "client-def", nil)
	other.SetStatus(StatusOnline)
	group.Register(other)

	// 模糊匹配 "abc" 应该命中 abc-1 和 abc-2，但优先返回健康的 abc-2
	got := group.FindClientByFuzzy("abc")
	if got == nil {
		t.Fatal("expected a fuzzy match, got nil")
	}
	if got.ClientID != "client-abc-2" {
		t.Errorf("expected healthy match client-abc-2, got %s", got.ClientID)
	}

	// 不匹配任何客户端
	if group.FindClientByFuzzy("xyz") != nil {
		t.Error("expected nil for non-matching substring")
	}
}

func TestRpcGroup_FindClientByFuzzy_FallbackToUnhealthy(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	c := NewRpcClient("test-group", "only-unhealthy", nil)
	c.SetStatus(StatusOnline)
	for i := 0; i < 3; i++ {
		c.MarkFailure()
	}
	group.Register(c)

	got := group.FindClientByFuzzy("unhealthy")
	if got == nil {
		t.Fatal("expected fallback to unhealthy client, got nil")
	}
	if got.ClientID != "only-unhealthy" {
		t.Errorf("expected only-unhealthy, got %s", got.ClientID)
	}
}

func TestRpcGroup_FindClientByFuzzy_EmptyGroup(t *testing.T) {
	group := NewRpcGroup("test-group")
	defer group.Close()

	if group.FindClientByFuzzy("anything") != nil {
		t.Error("expected nil for empty group")
	}
}
