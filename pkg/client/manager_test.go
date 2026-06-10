package client

import (
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/eventbus"
)

func TestClientManager_Register(t *testing.T) {
	manager := NewClientManager()
	defer manager.CleanupAll()

	client := NewRpcClient("test-group", "client-1", nil)
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

	client := NewRpcClient("test-group", "client-1", nil)
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
	manager.Register(NewRpcClient("group1", "client-1", nil))
	manager.Register(NewRpcClient("group2", "client-1", nil))
	manager.Register(NewRpcClient("group1", "client-2", nil))

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
	manager.Register(NewRpcClient("test-group", "client-1", nil))
	manager.Register(NewRpcClient("test-group", "client-2", nil))
	manager.Register(NewRpcClient("other-group", "client-3", nil))

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
	c1 := NewRpcClient("test-group", "client-1", nil)
	c1.SetStatus(StatusOnline)
	manager.Register(c1)

	c2 := NewRpcClient("test-group", "client-2", nil)
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
	manager.Register(NewRpcClient("group1", "client-1", nil))
	manager.Register(NewRpcClient("group1", "client-2", nil))
	manager.Register(NewRpcClient("group2", "client-3", nil))

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
	manager.Register(NewRpcClient("test-group", "client-1", nil))
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

	manager.Register(NewRpcClient("test-group", "client-1", nil))

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

	manager.Register(NewRpcClient("group1", "client-1", nil))
	manager.Register(NewRpcClient("group2", "client-1", nil))
	manager.Register(NewRpcClient("group1", "client-2", nil))

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

	manager.Register(NewRpcClient("group1", "client-1", nil))
	manager.Register(NewRpcClient("group1", "client-2", nil))
	manager.Register(NewRpcClient("group2", "client-3", nil))

	if manager.ClientCount() != 3 {
		t.Errorf("Expected 3 clients, got %d", manager.ClientCount())
	}
}

// newDebounceTestManager 构造一个使用极短去抖窗口的 manager，便于快速触发 trailing。
func newDebounceTestManager(t *testing.T, eb *eventbus.EventBus, debounce time.Duration) *ClientManager {
	t.Helper()
	m := NewClientManager()
	m.debounceDuration = debounce
	m.SetEventBus(eb)
	t.Cleanup(func() {
		m.Stop()
		m.CleanupAll()
	})
	return m
}

// TestClientManager_DebouncesConsecutiveRegisters 验证窗口内同一 (group, clientID, eventType)
// 多次 Register 只发布一次事件。
func TestClientManager_DebouncesConsecutiveRegisters(t *testing.T) {
	eb := eventbus.New()
	var connectCount int32
	eb.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
		atomic.AddInt32(&connectCount, 1)
	})

	debounce := 30 * time.Millisecond
	manager := newDebounceTestManager(t, eb, debounce)

	for i := 0; i < 5; i++ {
		manager.Register(NewRpcClient("g", "c1", nil))
	}

	// 等待 trailing 触发：debounce + 一定缓冲
	time.Sleep(debounce + 50*time.Millisecond)

	if got := atomic.LoadInt32(&connectCount); got != 1 {
		t.Errorf("Expected 1 connect event after debounce, got %d", got)
	}
}

// TestClientManager_DebounceKeysAreIndependent 验证不同的去抖键互不干扰：
// (group, clientID, eventType) 三元组中任一维度不同，事件应分别发布。
func TestClientManager_DebounceKeysAreIndependent(t *testing.T) {
	eb := eventbus.New()
	var connectCount, disconnectCount int32
	eb.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
		atomic.AddInt32(&connectCount, 1)
	})
	eb.Subscribe(eventbus.EventClientDisconnect, func(event interface{}) {
		atomic.AddInt32(&disconnectCount, 1)
	})

	debounce := 30 * time.Millisecond
	manager := newDebounceTestManager(t, eb, debounce)

	// 三种键维度变化：分组、客户端、事件类型
	manager.Register(NewRpcClient("g1", "c1", nil))
	manager.Register(NewRpcClient("g2", "c1", nil)) // group 不同
	manager.Register(NewRpcClient("g1", "c2", nil)) // clientID 不同
	manager.Unregister("g1", "c1")                  // eventType 不同

	time.Sleep(debounce + 50*time.Millisecond)

	if got := atomic.LoadInt32(&connectCount); got != 3 {
		t.Errorf("Expected 3 connect events for 3 distinct keys, got %d", got)
	}
	if got := atomic.LoadInt32(&disconnectCount); got != 1 {
		t.Errorf("Expected 1 disconnect event, got %d", got)
	}
}

// TestClientManager_StopCancelsPending 验证 Stop() 取消所有 pending timer，
// 未触发的事件被丢弃，关停后再调 Register 也不会发布。
func TestClientManager_StopCancelsPending(t *testing.T) {
	eb := eventbus.New()
	var connectCount int32
	eb.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
		atomic.AddInt32(&connectCount, 1)
	})

	debounce := 50 * time.Millisecond
	manager := NewClientManager()
	manager.debounceDuration = debounce
	manager.SetEventBus(eb)
	t.Cleanup(manager.CleanupAll)

	manager.Register(NewRpcClient("g", "c1", nil))
	manager.Register(NewRpcClient("g", "c2", nil))

	// trailing 触发前调用 Stop
	manager.Stop()

	// Stop 之后再注册不应发布事件
	manager.Register(NewRpcClient("g", "c3", nil))

	time.Sleep(debounce + 50*time.Millisecond)

	if got := atomic.LoadInt32(&connectCount); got != 0 {
		t.Errorf("Expected 0 events after Stop, got %d", got)
	}

	// Stop 是幂等的
	manager.Stop()
}

// TestClientManager_StateUpdatesAreSynchronous 验证去抖只压制事件发布，
// 状态更新立即生效（GetClient 在 Register 后立刻可见）。
func TestClientManager_StateUpdatesAreSynchronous(t *testing.T) {
	eb := eventbus.New()
	manager := newDebounceTestManager(t, eb, 30*time.Millisecond)

	manager.Register(NewRpcClient("g", "c1", nil))

	// 不等待 debounce 窗口
	if got := manager.GetClient("g", "c1"); got == nil {
		t.Error("Client state should be visible immediately, debounce only delays events")
	}
}

// TestClientManager_DebounceConcurrentRegister 在并发 Register 同分组不同客户端的场景下
// 验证去抖逻辑无 panic、事件计数正确（每个 clientID 一次）。
func TestClientManager_DebounceConcurrentRegister(t *testing.T) {
	eb := eventbus.New()
	var connectCount int32
	eb.Subscribe(eventbus.EventClientConnect, func(event interface{}) {
		atomic.AddInt32(&connectCount, 1)
	})

	debounce := 20 * time.Millisecond
	manager := newDebounceTestManager(t, eb, debounce)

	const goroutines = 50
	const repeatsPerKey = 10
	var wg sync.WaitGroup
	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c := NewRpcClient("g", fmt.Sprintf("c%d", i), nil)
			for j := 0; j < repeatsPerKey; j++ {
				manager.Register(c)
			}
		}(i)
	}
	wg.Wait()

	time.Sleep(debounce + 80*time.Millisecond)

	// 每个独立 clientID 应只产生 1 个事件（debounce 合并所有 repeat）
	if got := atomic.LoadInt32(&connectCount); got != int32(goroutines) {
		t.Errorf("Expected %d connect events (one per distinct clientID), got %d",
			goroutines, got)
	}
}

// TestClientManager_ConcurrentRegisterUnregisterNoDeadlock 是 RpcGroup 关停死锁的回归测试。
// 修复前：当 Unregister 把 group.ClientCount() 变成 0 → manager 调 group.Close() → runLoop 退出，
// 与此并行的 goroutine 在 getOrCreateGroup 之后拿到旧 group 引用，再调 ClientCount/AllocateClient 时
// 命令塞进 commandChan 但永远拿不到 callback，TestTimeout 死锁。
// 修复后：group.Close() 关 done channel，所有 sender/waiter 用 select+done 立即解锁返回零值。
func TestClientManager_ConcurrentRegisterUnregisterNoDeadlock(t *testing.T) {
	eb := eventbus.New()
	manager := newDebounceTestManager(t, eb, 5*time.Millisecond)

	const goroutines = 100
	var wg sync.WaitGroup
	done := make(chan struct{})

	for i := 0; i < goroutines; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c := NewRpcClient("g", "c-shared", nil)
			manager.Register(c)
			// 触发 group.ClientCount() 与并行 Close 的竞态
			manager.Unregister("g", "c-shared")
		}(i)
	}

	go func() {
		wg.Wait()
		close(done)
	}()

	select {
	case <-done:
		// 所有 goroutine 完成
	case <-time.After(10 * time.Second):
		t.Fatal("Deadlock: concurrent Register/Unregister did not complete in 10s")
	}
}
