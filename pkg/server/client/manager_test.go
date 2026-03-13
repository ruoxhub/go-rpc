package client

import (
	"testing"
)

func TestClientManager_Register(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	client := NewSekiroClient("test-group", "client-1", nil)
	manager.Register(client)

	// 验证客户端已注册
	registered := manager.GetClient("test-group", "client-1")
	if registered == nil {
		t.Fatal("Client not registered")
	}
	if registered.ClientID != "client-1" {
		t.Errorf("Expected client-1, got %s", registered.ClientID)
	}
}

func TestClientManager_Unregister(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	client := NewSekiroClient("test-group", "client-1", nil)
	manager.Register(client)

	// 验证注册成功
	if manager.GetClient("test-group", "client-1") == nil {
		t.Fatal("Client should be registered")
	}

	// 注销
	manager.Unregister("test-group", "client-1")

	// 验证注销成功
	if manager.GetClient("test-group", "client-1") != nil {
		t.Error("Client should be unregistered")
	}
}

func TestClientManager_GetAllGroups(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	// 初始应该为空
	groups := manager.GetAllGroups()
	if len(groups) != 0 {
		t.Errorf("Expected 0 groups, got %d", len(groups))
	}

	// 注册不同组的客户端
	manager.Register(NewSekiroClient("group1", "client-1", nil))
	manager.Register(NewSekiroClient("group2", "client-1", nil))
	manager.Register(NewSekiroClient("group1", "client-2", nil))

	groups = manager.GetAllGroups()
	if len(groups) != 2 {
		t.Errorf("Expected 2 groups, got %d", len(groups))
	}
}

func TestClientManager_GetClientsByGroup(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	// 空组应该返回 nil
	clients := manager.GetClientsByGroup("non-existent")
	if clients != nil {
		t.Error("Expected nil for non-existent group")
	}

	// 注册客户端
	manager.Register(NewSekiroClient("test-group", "client-1", nil))
	manager.Register(NewSekiroClient("test-group", "client-2", nil))
	manager.Register(NewSekiroClient("other-group", "client-3", nil))

	clients = manager.GetClientsByGroup("test-group")
	if len(clients) != 2 {
		t.Errorf("Expected 2 clients, got %d", len(clients))
	}
}

func TestClientManager_AllocateClient(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	// 空组应该返回 nil
	client := manager.AllocateClient("test-group")
	if client != nil {
		t.Error("Expected nil for empty group")
	}

	// 注册在线客户端
	c1 := NewSekiroClient("test-group", "client-1", nil)
	c1.SetStatus(StatusOnline)
	manager.Register(c1)

	c2 := NewSekiroClient("test-group", "client-2", nil)
	c2.SetStatus(StatusOffline)
	manager.Register(c2)

	// 应该返回在线客户端
	allocated := manager.AllocateClient("test-group")
	if allocated == nil {
		t.Fatal("Expected a client")
	}
	if allocated.ClientID != "client-1" {
		t.Errorf("Expected client-1 (online), got %s", allocated.ClientID)
	}
}

func TestClientManager_CleanupAll(t *testing.T) {
	manager := NewClientManager()

	// 注册客户端
	manager.Register(NewSekiroClient("group1", "client-1", nil))
	manager.Register(NewSekiroClient("group1", "client-2", nil))
	manager.Register(NewSekiroClient("group2", "client-3", nil))

	// 验证注册成功
	if manager.GroupCount() != 2 {
		t.Errorf("Expected 2 groups, got %d", manager.GroupCount())
	}
	if manager.ClientCount() != 3 {
		t.Errorf("Expected 3 clients, got %d", manager.ClientCount())
	}

	// 清理所有
	manager.CleanupAll()

	// 验证清理成功
	if manager.GroupCount() != 0 {
		t.Error("Expected 0 groups after cleanup")
	}
	if manager.ClientCount() != 0 {
		t.Error("Expected 0 clients after cleanup")
	}
}

func TestClientManager_GetGroup(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	// 不存在的组
	group := manager.GetGroup("non-existent")
	if group != nil {
		t.Error("Expected nil for non-existent group")
	}

	// 存在的组
	manager.Register(NewSekiroClient("test-group", "client-1", nil))
	group = manager.GetGroup("test-group")
	if group == nil {
		t.Fatal("Expected group to exist")
	}
	if group.Name() != "test-group" {
		t.Errorf("Expected group name 'test-group', got '%s'", group.Name())
	}
}

func TestClientManager_HasGroup(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	if manager.HasGroup("test-group") {
		t.Error("Expected false for non-existent group")
	}

	manager.Register(NewSekiroClient("test-group", "client-1", nil))

	if !manager.HasGroup("test-group") {
		t.Error("Expected true for existing group")
	}
}

func TestClientManager_GroupCount(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	if manager.GroupCount() != 0 {
		t.Error("Expected 0 groups initially")
	}

	manager.Register(NewSekiroClient("group1", "client-1", nil))
	manager.Register(NewSekiroClient("group2", "client-1", nil))
	manager.Register(NewSekiroClient("group1", "client-2", nil))

	if manager.GroupCount() != 2 {
		t.Errorf("Expected 2 groups, got %d", manager.GroupCount())
	}
}

func TestClientManager_ClientCount(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	if manager.ClientCount() != 0 {
		t.Error("Expected 0 clients initially")
	}

	manager.Register(NewSekiroClient("group1", "client-1", nil))
	manager.Register(NewSekiroClient("group1", "client-2", nil))
	manager.Register(NewSekiroClient("group2", "client-3", nil))

	if manager.ClientCount() != 3 {
		t.Errorf("Expected 3 clients, got %d", manager.ClientCount())
	}
}
