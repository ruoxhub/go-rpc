package detector

import (
	"bufio"
	"bytes"
	"context"
	"io"
	"net"
	"net/http"
	"sync"
)

// HttpMatcher matches HTTP protocol
type HttpMatcher struct {
	httpServer *http.Server
	once       sync.Once
	listener   net.Listener
}

// NewHttpMatcher creates a new HttpMatcher
func NewHttpMatcher() *HttpMatcher {
	return &HttpMatcher{}
}

// SetHTTPServer sets the HTTP server for handling connections
func (m *HttpMatcher) SetHTTPServer(server *http.Server) {
	m.httpServer = server
}

// Match checks if the buffer matches HTTP protocol
func (m *HttpMatcher) Match(buf []byte) int {
	if len(buf) < 4 {
		return Pending
	}

	// Check for HTTP methods
	httpMethods := [][]byte{
		[]byte("GET "),
		[]byte("POST "),
		[]byte("PUT "),
		[]byte("DELETE "),
		[]byte("HEAD "),
		[]byte("OPTIONS "),
		[]byte("PATCH "),
	}

	for _, method := range httpMethods {
		if bytes.HasPrefix(buf, method) {
			return Match
		}
	}

	return Mismatch
}

// HandleConnection handles HTTP connections by forwarding to http.Server
func (m *HttpMatcher) HandleConnection(ctx context.Context, conn net.Conn, firstRead []byte) error {
	// Create a reader that includes the firstRead data
	reader := bufio.NewReader(io.MultiReader(bytes.NewReader(firstRead), conn))

	// Create a custom connection that wraps the reader
	hijackedConn := &hijackedConn{
		Conn:   conn,
		reader: reader,
	}

	// Create a single-connection listener
	listener := &singleConnListener{conn: hijackedConn}

	// Serve the single connection
	return m.httpServer.Serve(listener)
}

// hijackedConn wraps a net.Conn with a custom reader
type hijackedConn struct {
	net.Conn
	reader *bufio.Reader
}

func (h *hijackedConn) Read(p []byte) (n int, err error) {
	return h.reader.Read(p)
}

// singleConnListener implements net.Listener for a single connection
type singleConnListener struct {
	conn net.Conn
	done chan struct{}
}

func (l *singleConnListener) Accept() (net.Conn, error) {
	if l.done != nil {
		return nil, net.ErrClosed
	}
	l.done = make(chan struct{})
	return l.conn, nil
}

func (l *singleConnListener) Close() error {
	if l.done != nil {
		close(l.done)
	}
	return nil
}

func (l *singleConnListener) Addr() net.Addr {
	if l.conn != nil {
		return l.conn.LocalAddr()
	}
	return nil
}
