// Package eventbus 实现 RPC 客户端事件的事件发布-订阅总线
package eventbus

import (
	"sync"
)

// EventHandler 事件处理函数类型
type EventHandler func(event interface{})

// EventBus 管理事件的注册和分发
type EventBus struct {
	handlers map[string][]EventHandler
	mu       sync.RWMutex
}

// New 创建一个新的 EventBus
func New() *EventBus {
	return &EventBus{
		handlers: make(map[string][]EventHandler),
	}
}

// Subscribe 订阅指定事件类型
func (eb *EventBus) Subscribe(eventType string, handler EventHandler) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	eb.handlers[eventType] = append(eb.handlers[eventType], handler)
}

// Unsubscribe 取消订阅指定事件类型
func (eb *EventBus) Unsubscribe(eventType string, handler EventHandler) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	handlers := eb.handlers[eventType]
	for i, h := range handlers {
		if sameHandler(h, handler) {
			eb.handlers[eventType] = append(handlers[:i], handlers[i+1:]...)
			return
		}
	}
}

// Publish 向所有注册的处理器发布事件。
// 当前为同步派发：在调用方 goroutine 内顺序调用所有 handler，
// 慢订阅者会阻塞发布者。如需异步语义，由订阅方自行启动 goroutine。
func (eb *EventBus) Publish(eventType string, event interface{}) {
	eb.mu.RLock()
	handlers := make([]EventHandler, len(eb.handlers[eventType]))
	copy(handlers, eb.handlers[eventType])
	eb.mu.RUnlock()

	for _, handler := range handlers {
		handler(event)
	}
}

// Clear 清除指定事件类型的所有处理器
func (eb *EventBus) Clear(eventType string) {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	delete(eb.handlers, eventType)
}

// ClearAll 清除所有事件处理器
func (eb *EventBus) ClearAll() {
	eb.mu.Lock()
	defer eb.mu.Unlock()

	eb.handlers = make(map[string][]EventHandler)
}

// HandlerCount 返回指定事件类型的处理器数量
func (eb *EventBus) HandlerCount(eventType string) int {
	eb.mu.RLock()
	defer eb.mu.RUnlock()
	return len(eb.handlers[eventType])
}

// sameHandler 比较两个处理函数是否为同一个（通过地址）
func sameHandler(a, b EventHandler) bool {
	return funcEqual(a, b)
}
