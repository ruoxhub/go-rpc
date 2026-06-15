package eventbus

import "time"

// 事件类型常量
const (
	EventClientConnect                = "client.connect"
	EventClientDisconnect             = "client.disconnect"
	EventClientDestroy                = "client.destroy"
	EventClientOnline                 = "client.online"
	EventClientHealthDegraded         = "client.health_degraded"
	EventCircuitBreakerStateChanged   = "client.circuit_breaker_state_changed"
	EventInvokerConnect               = "invoker.connect"
	EventInvokerDisconnect            = "invoker.disconnect"
	EventInvokerDestroy               = "invoker.destroy"
	EventClientKicked                 = "client.kicked"
)

// ClientConnectEvent 客户端连接事件
type ClientConnectEvent struct {
	Group     string
	ClientID  string
	Timestamp time.Time
}

// ClientDisconnectEvent 客户端断开事件
type ClientDisconnectEvent struct {
	Group     string
	ClientID  string
	Timestamp time.Time
}

// ClientDestroyEvent 客户端销毁事件
type ClientDestroyEvent struct {
	Group     string
	ClientID  string
	Timestamp time.Time
}

// ClientOnlineEvent 客户端上线事件
type ClientOnlineEvent struct {
	Group     string
	ClientID  string
	Timestamp time.Time
}

// ClientHealthDegradedEvent 客户端健康降级事件
type ClientHealthDegradedEvent struct {
	Group     string
	ClientID  string
	FailCount int
	Timestamp time.Time
}

// InvokerConnectEvent 调用端连接事件
type InvokerConnectEvent struct {
	ServerAddr string
	Timestamp  time.Time
}

// InvokerDisconnectEvent 调用端断开事件
type InvokerDisconnectEvent struct {
	ServerAddr string
	Timestamp  time.Time
}

// InvokerDestroyEvent 调用端销毁事件
type InvokerDestroyEvent struct {
	ServerAddr string
	Timestamp  time.Time
}

// CircuitBreakerStateEvent 熔断器状态变更事件
type CircuitBreakerStateEvent struct {
	Group     string
	ClientID  string
	From      string
	To        string
	Timestamp time.Time
}

// ClientKickedEvent 客户端被踢除事件
type ClientKickedEvent struct {
	Group    string
	ClientID string // 为空时表示整组踢除
	Time     time.Time
}
