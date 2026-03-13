package eventbus

// Client events
type ClientConnectEvent struct {
	Group    string
	ClientID string
}

func (e *ClientConnectEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type ClientDisconnectEvent struct {
	Group    string
	ClientID string
}

func (e *ClientDisconnectEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type ClientDestroyEvent struct {
	Group    string
	ClientID string
}

func (e *ClientDestroyEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type ClientOnlineEvent struct {
	Group    string
	ClientID string
}

func (e *ClientOnlineEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type InvokerConnectEvent struct {
	ServerAddr string
}

func (e *InvokerConnectEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type InvokerDisconnectEvent struct {
	ServerAddr string
}

func (e *InvokerDisconnectEvent) OnEvent(data interface{}) {
	// Handler implementation
}

type InvokerDestroyEvent struct {
	ServerAddr string
}

func (e *InvokerDestroyEvent) OnEvent(data interface{}) {
	// Handler implementation
}
