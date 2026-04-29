// Package eventbus implements event bus for Rpc client events
package eventbus

import (
	"sync"
)

// Event represents an event interface
type Event interface {
	OnEvent(data interface{})
}

// EventBus manages event registration and dispatch
type EventBus struct {
	handlers map[string][]Event
	mu       sync.RWMutex
}

// NewEventBus creates a new EventBus
func NewEventBus() *EventBus {
	return &EventBus{
		handlers: make(map[string][]Event),
	}
}

// Register registers an event handler
func (eb *EventBus) Register(eventType string, handler Event) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	eb.handlers[eventType] = append(eb.handlers[eventType], handler)
}

// Unregister unregisters an event handler
func (eb *EventBus) Unregister(eventType string, handler Event) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	handlers := eb.handlers[eventType]
	for i, h := range handlers {
		if h == handler {
			eb.handlers[eventType] = append(handlers[:i], handlers[i+1:]...)
			return
		}
	}
}

// Dispatch dispatches an event to all registered handlers
func (eb *EventBus) Dispatch(eventType string, data interface{}) {
	eb.mu.RLock()
	handlers := eb.handlers[eventType]
	eb.mu.RUnlock()

	for _, handler := range handlers {
		handler.OnEvent(data)
	}
}

// Clear clears all handlers for an event type
func (eb *EventBus) Clear(eventType string) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	delete(eb.handlers, eventType)
}

// ClearAll clears all handlers
func (eb *EventBus) ClearAll() {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	eb.handlers = make(map[string][]Event)
}
