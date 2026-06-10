package transport

import (
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// WSConnection wraps a gorilla/websocket.Conn as a transport.Connection.
type WSConnection struct {
	conn    *websocket.Conn
	writeMu sync.Mutex
}

// NewWSConnection creates a new WSConnection.
func NewWSConnection(conn *websocket.Conn) *WSConnection {
	return &WSConnection{conn: conn}
}

func (w *WSConnection) Send(data []byte) error {
	w.writeMu.Lock()
	defer w.writeMu.Unlock()
	w.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
	return w.conn.WriteMessage(websocket.TextMessage, data)
}

func (w *WSConnection) Close() error {
	return w.conn.Close()
}

func (w *WSConnection) RemoteAddr() string {
	if w.conn == nil || w.conn.UnderlyingConn() == nil {
		return ""
	}
	addr := w.conn.UnderlyingConn().RemoteAddr()
	if addr == nil {
		return ""
	}
	return addr.String()
}

// Conn returns the underlying gorilla/websocket.Conn.
// Used when WebSocket-specific operations (SetReadDeadline) are needed.
func (w *WSConnection) Conn() *websocket.Conn {
	return w.conn
}

var _ Connection = (*WSConnection)(nil)
