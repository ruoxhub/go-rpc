package eventbus

import (
	"sync"
	"testing"
	"time"
)

func TestNewEventBus(t *testing.T) {
	bus := New()
	if bus == nil {
		t.Fatal("New() returned nil")
	}
	if bus.handlers == nil {
		t.Error("New() handlers not initialized")
	}
}

func TestEventBusSubscribeAndPublish(t *testing.T) {
	bus := New()
	var called bool
	var received interface{}

	bus.Subscribe("test.event", func(event interface{}) {
		called = true
		received = event
	})

	bus.Publish("test.event", "test data")

	if !called {
		t.Error("Event handler was not called")
	}
	if received != "test data" {
		t.Errorf("Event data = %v, want 'test data'", received)
	}
}

func TestEventBusUnsubscribe(t *testing.T) {
	bus := New()
	called := false
	handler := func(event interface{}) {
		called = true
	}

	bus.Subscribe("test.event", handler)
	bus.Unsubscribe("test.event", handler)
	bus.Publish("test.event", "test data")

	if called {
		t.Error("Event handler should not be called after unsubscribe")
	}
}

func TestEventBusMultipleHandlers(t *testing.T) {
	bus := New()
	count := 0
	var mu sync.Mutex

	incr := func(event interface{}) {
		mu.Lock()
		defer mu.Unlock()
		count++
	}

	bus.Subscribe("multi.event", incr)
	bus.Subscribe("multi.event", incr)
	bus.Subscribe("multi.event", incr)

	bus.Publish("multi.event", "broadcast")

	mu.Lock()
	defer mu.Unlock()
	if count != 3 {
		t.Errorf("Expected 3 handler calls, got %d", count)
	}
}

func TestEventBusClear(t *testing.T) {
	bus := New()
	called := false

	handler := func(event interface{}) {
		called = true
	}

	bus.Subscribe("test.event", handler)
	bus.Clear("test.event")
	bus.Publish("test.event", "test data")

	if called {
		t.Error("Event handler should not be called after clear")
	}
}

func TestEventBusClearAll(t *testing.T) {
	bus := New()
	called1, called2 := false, false

	bus.Subscribe("event1", func(event interface{}) { called1 = true })
	bus.Subscribe("event2", func(event interface{}) { called2 = true })
	bus.ClearAll()

	bus.Publish("event1", "data")
	bus.Publish("event2", "data")

	if called1 || called2 {
		t.Error("Event handlers should not be called after clear all")
	}
}

func TestEventBusUnknownEventType(t *testing.T) {
	bus := New()

	// Publishing to unknown event type should not panic
	bus.Publish("unknown.event", "data")

	// Unsubscribing unknown handler should not panic
	bus.Unsubscribe("unknown.event", func(event interface{}) {})

	// Clear unknown event type should not panic
	bus.Clear("unknown.event")
}

func TestEventBusConcurrentPublish(t *testing.T) {
	bus := New()
	count := 0
	var mu sync.Mutex

	bus.Subscribe("concurrent.event", func(event interface{}) {
		mu.Lock()
		defer mu.Unlock()
		count++
	})

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			bus.Publish("concurrent.event", "concurrent data")
		}()
	}
	wg.Wait()

	mu.Lock()
	defer mu.Unlock()
	if count != 10 {
		t.Errorf("Expected 10 handler calls, got %d", count)
	}
}

func TestEventBusConcurrentSubscribe(t *testing.T) {
	bus := New()

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			bus.Subscribe("concurrent.event", func(event interface{}) {})
		}()
	}
	wg.Wait()

	if n := bus.HandlerCount("concurrent.event"); n != 10 {
		t.Errorf("Expected 10 handlers, got %d", n)
	}
}

func TestHandlerCount(t *testing.T) {
	bus := New()

	if n := bus.HandlerCount("nonexistent"); n != 0 {
		t.Errorf("Expected 0 handlers, got %d", n)
	}

	bus.Subscribe("test.event", func(event interface{}) {})
	bus.Subscribe("test.event", func(event interface{}) {})

	if n := bus.HandlerCount("test.event"); n != 2 {
		t.Errorf("Expected 2 handlers, got %d", n)
	}
}

func TestEventStructs(t *testing.T) {
	now := time.Now()

	// Verify all event structs can be created and fields are correct
	e1 := ClientConnectEvent{Group: "g1", ClientID: "c1", Timestamp: now}
	if e1.Group != "g1" || e1.ClientID != "c1" {
		t.Error("ClientConnectEvent fields mismatch")
	}

	e2 := ClientDisconnectEvent{Group: "g2", ClientID: "c2", Timestamp: now}
	if e2.Group != "g2" || e2.ClientID != "c2" {
		t.Error("ClientDisconnectEvent fields mismatch")
	}

	e3 := ClientHealthDegradedEvent{Group: "g3", ClientID: "c3", FailCount: 5, Timestamp: now}
	if e3.FailCount != 5 {
		t.Error("ClientHealthDegradedEvent fields mismatch")
	}

	e4 := InvokerConnectEvent{ServerAddr: "localhost:5612", Timestamp: now}
	if e4.ServerAddr != "localhost:5612" {
		t.Error("InvokerConnectEvent fields mismatch")
	}
}
