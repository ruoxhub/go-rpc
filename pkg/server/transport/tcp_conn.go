package transport

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"sync"
)

// TCPConnection wraps a net.Conn as a transport.Connection.
// Receive reads a complete RPC protocol frame (magic + length + body).
type TCPConnection struct {
	conn net.Conn

	writeMu  sync.Mutex
	closed   bool
	closedMu sync.RWMutex
}

// NewTCPConnection creates a new TCPConnection.
func NewTCPConnection(conn net.Conn) *TCPConnection {
	return &TCPConnection{conn: conn}
}

// NewTCPConnectionWithData creates a TCPConnection that prepends already-read
// data to the input stream. Used by protocol detectors that consume initial bytes.
func NewTCPConnectionWithData(conn net.Conn, firstRead []byte) *TCPConnection {
	return &TCPConnection{conn: &prependConn{Conn: conn, prefix: firstRead}}
}

// prependConn prepends initial bytes on the first read, then delegates to the
// underlying connection. Implements net.Conn.
type prependConn struct {
	net.Conn
	prefix []byte
	once   sync.Once
	mu     sync.Mutex
}

func (p *prependConn) Read(b []byte) (int, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if len(p.prefix) > 0 {
		n := copy(b, p.prefix)
		p.prefix = p.prefix[n:]
		if len(p.prefix) == 0 {
			p.prefix = nil
		}
		if n > 0 {
			return n, nil
		}
	}
	return p.Conn.Read(b)
}

func (t *TCPConnection) Send(data []byte) error {
	t.closedMu.RLock()
	closed := t.closed
	t.closedMu.RUnlock()
	if closed {
		return fmt.Errorf("connection closed")
	}

	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	_, err := t.conn.Write(data)
	return err
}

func (t *TCPConnection) Receive() ([]byte, error) {
	// Read magic number (8 bytes)
	var magic int64
	if err := binary.Read(t.conn, binary.BigEndian, &magic); err != nil {
		return nil, err
	}

	// Read body length (4 bytes)
	var bodyLen int32
	if err := binary.Read(t.conn, binary.BigEndian, &bodyLen); err != nil {
		return nil, err
	}
	if bodyLen < 0 || bodyLen > 10*1024*1024 {
		return nil, errors.New("invalid body length")
	}

	// Read the body (type + serial + headers + data)
	body := make([]byte, bodyLen)
	if _, err := io.ReadFull(t.conn, body); err != nil {
		return nil, err
	}

	// Return the full framed message bytes
	var buf bytes.Buffer
	binary.Write(&buf, binary.BigEndian, magic)
	binary.Write(&buf, binary.BigEndian, bodyLen)
	buf.Write(body)
	return buf.Bytes(), nil
}

func (t *TCPConnection) Close() error {
	t.closedMu.Lock()
	defer t.closedMu.Unlock()
	if t.closed {
		return nil
	}
	t.closed = true
	return t.conn.Close()
}

func (t *TCPConnection) RemoteAddr() string {
	if t.conn == nil {
		return ""
	}
	return t.conn.RemoteAddr().String()
}

// Conn returns the underlying net.Conn.
func (t *TCPConnection) Conn() net.Conn {
	return t.conn
}
