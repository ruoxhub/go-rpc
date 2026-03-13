package client

import (
	"testing"
)

func TestSekiroGroup_Register(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	client := NewSekiroClient("test-group", "client-1", nil)

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

func TestSekiroGroup_Unregister(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	client := NewSekiroClient("test-group", "client-1", nil)
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

func TestSekiroGroup_GetAllClients(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	// 注册多个客户端
	group.Register(NewSekiroClient("test-group", "client-1", nil))
	group.Register(NewSekiroClient("test-group", "client-2", nil))
	group.Register(NewSekiroClient("test-group", "client-3", nil))

	// 获取所有客户端
	clients := group.GetAllClients()
	if len(clients) != 3 {
		t.Errorf("Expected 3 clients, got %d", len(clients))
	}
}

func TestSekiroGroup_AllocateClient(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	// 空组应该返回 nil
	client := group.AllocateClient()
	if client != nil {
		t.Error("Expected nil for empty group")
	}

	// 注册客户端
	c1 := NewSekiroClient("test-group", "client-1", nil)
	c1.SetStatus(StatusOnline)
	group.Register(c1)

	c2 := NewSekiroClient("test-group", "client-2", nil)
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

func TestSekiroGroup_Name(t *testing.T) {
	group := NewSekiroGroup("my-group")
	defer group.Close()

	if group.Name() != "my-group" {
		t.Errorf("Expected name 'my-group', got '%s'", group.Name())
	}
}

func TestSekiroGroup_ClientCount(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	if group.ClientCount() != 0 {
		t.Error("Expected 0 clients for new group")
	}

	group.Register(NewSekiroClient("test-group", "client-1", nil))
	group.Register(NewSekiroClient("test-group", "client-2", nil))

	// 使用 GetAllClients 来验证
	clients := group.GetAllClients()
	if len(clients) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(clients))
	}
}

func TestSekiroGroup_Close(t *testing.T) {
	group := NewSekiroGroup("test-group")

	client := NewSekiroClient("test-group", "client-1", nil)
	group.Register(client)

	// 验证注册成功
	if group.GetClient("client-1") == nil {
		t.Fatal("Client should be registered")
	}

	group.Close()

	// 关闭后注册应该无效（使用 Close 的 group）
	group.Register(NewSekiroClient("test-group", "client-2", nil))

	// 验证 client-2 没有注册成功
	if group.HasClient("client-2") {
		t.Error("New client should not be registered after close")
	}
}

func TestSekiroGroup_HasClient(t *testing.T) {
	group := NewSekiroGroup("test-group")
	defer group.Close()

	if group.HasClient("client-1") {
		t.Error("Expected false for non-existent client")
	}

	group.Register(NewSekiroClient("test-group", "client-1", nil))

	if !group.HasClient("client-1") {
		t.Error("Expected true for existing client")
	}
}
