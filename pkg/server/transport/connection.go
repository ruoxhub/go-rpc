// Package transport provides a unified connection abstraction over
// different network transports (WebSocket, TCP) used by the RPC server.
package transport

import "net"

// Connection abstracts a bidirectional message transport.
// Implementations must be safe for concurrent use of Send.
type Connection interface {
	// Send writes a message. Must be safe for concurrent use.
	Send(data []byte) error
	// Receive reads the next message. Blocks until a message arrives.
	Receive() ([]byte, error)
	// Close closes the connection.
	Close() error
	// RemoteAddr returns the remote network address.
	RemoteAddr() string
}

// ExtractRemoteIP extracts the IP address from a remote address string.
func ExtractRemoteIP(addr string) string {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		return addr
	}
	return host
}
