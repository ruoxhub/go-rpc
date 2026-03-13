package eventbus

import (
	"sync"
	"testing"
)

// testEvent is a test event implementation
type testEvent struct {
	called bool
	data   interface{}
	mu     sync.Mutex
}

func (e *testEvent) OnEvent(data interface{}) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.called = true
	e.data = data
}

func (e *testEvent) wasCalled() bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.called
}

func TestNewEventBus(t *testing.T) {
	bus := NewEventBus()
	if bus == nil {
		t.Fatal("NewEventBus() returned nil")
	}
	if bus.handlers == nil {
		t.Error("NewEventBus() handlers not initialized")
	}
}

func TestEventBusRegisterAndDispatch(t *testing.T) {
	bus := NewEventBus()
	event := &testEvent{}

	bus.Register("test.event", event)
	bus.Dispatch("test.event", "test data")

	if !event.wasCalled() {
		t.Error("Event handler was not called")
	}
	if event.data != "test data" {
		t.Errorf("Event data = %v, want 'test data'", event.data)
	}
}

func TestEventBusUnregister(t *testing.T) {
	bus := NewEventBus()
	event := &testEvent{}

	bus.Register("test.event", event)
	bus.Unregister("test.event", event)
	bus.Dispatch("test.event", "test data")

	// After unregister, handler should not be called
	// Note: Since we already dispatched once, called might be true from first dispatch
	// Create a new event to verify
	event2 := &testEvent{}
	bus.Register("test.event2", event2)
	bus.Unregister("test.event2", event2)
	bus.Dispatch("test.event2", "test data")

	if event2.wasCalled() {
		t.Error("Event handler should not be called after unregister")
	}
}

func TestEventBusMultipleHandlers(t *testing.T) {
	bus := NewEventBus()
	event1 := &testEvent{}
	event2 := &testEvent{}
	event3 := &testEvent{}

	bus.Register("multi.event", event1)
	bus.Register("multi.event", event2)
	bus.Register("multi.event", event3)

	bus.Dispatch("multi.event", "broadcast")

	if !event1.wasCalled() {
		t.Error("Event handler 1 was not called")
	}
	if !event2.wasCalled() {
		t.Error("Event handler 2 was not called")
	}
	if !event3.wasCalled() {
		t.Error("Event handler 3 was not called")
	}
}

func TestEventBusClear(t *testing.T) {
	bus := NewEventBus()
	event := &testEvent{}

	bus.Register("test.event", event)
	bus.Clear("test.event")
	bus.Dispatch("test.event", "test data")

	if event.wasCalled() {
		t.Error("Event handler should not be called after clear")
	}
}

func TestEventBusClearAll(t *testing.T) {
	bus := NewEventBus()
	event1 := &testEvent{}
	event2 := &testEvent{}

	bus.Register("event1", event1)
	bus.Register("event2", event2)
	bus.ClearAll()

	bus.Dispatch("event1", "data")
	bus.Dispatch("event2", "data")

	if event1.wasCalled() || event2.wasCalled() {
		t.Error("Event handlers should not be called after clear all")
	}
}

func TestEventBusUnknownEventType(t *testing.T) {
	bus := NewEventBus()

	// Dispatching to unknown event type should not panic
	bus.Dispatch("unknown.event", "data")

	// Unregistering unknown handler should not panic
	bus.Unregister("unknown.event", &testEvent{})

	// Clear unknown event type should not panic
	bus.Clear("unknown.event")
}

func TestEventBusConcurrentDispatch(t *testing.T) {
	bus := NewEventBus()
	event := &testEvent{}

	bus.Register("concurrent.event", event)

	// Test concurrent dispatches
	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			bus.Dispatch("concurrent.event", "concurrent data")
		}()
	}
	wg.Wait()

	if !event.wasCalled() {
		t.Error("Event handler was not called during concurrent dispatch")
	}
}

func TestEventBusConcurrentRegister(t *testing.T) {
	bus := NewEventBus()

	// Test concurrent registrations
	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			bus.Register("concurrent.event", &testEvent{})
		}()
	}
	wg.Wait()

	// Should have 10 handlers
	bus.mu.RLock()
	count := len(bus.handlers["concurrent.event"])
	bus.mu.RUnlock()

	if count != 10 {
		t.Errorf("Expected 10 handlers, got %d", count)
	}
}

// Test event structs
func TestClientEvents(t *testing.T) {
	tests := []struct {
		name     string
		event    Event
		testData interface{}
	}{
		{
			name:     "ClientConnectEvent",
			event:    &ClientConnectEvent{Group: "test", ClientID: "client1"},
			testData: nil,
		},
		{
			name:     "ClientDisconnectEvent",
			event:    &ClientDisconnectEvent{Group: "test", ClientID: "client1"},
			testData: nil,
		},
		{
			name:     "ClientDestroyEvent",
			event:    &ClientDestroyEvent{Group: "test", ClientID: "client1"},
			testData: nil,
		},
		{
			name:     "ClientOnlineEvent",
			event:    &ClientOnlineEvent{Group: "test", ClientID: "client1"},
			testData: nil,
		},
		{
			name:     "InvokerConnectEvent",
			event:    &InvokerConnectEvent{ServerAddr: "localhost:5612"},
			testData: nil,
		},
		{
			name:     "InvokerDisconnectEvent",
			event:    &InvokerDisconnectEvent{ServerAddr: "localhost:5612"},
			testData: nil,
		},
		{
			name:     "InvokerDestroyEvent",
			event:    &InvokerDestroyEvent{ServerAddr: "localhost:5612"},
			testData: nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// OnEvent should not panic
			tt.event.OnEvent(tt.testData)
		})
	}
}
