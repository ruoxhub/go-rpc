// Package detector implements protocol detection for Rpc server
package detector

import (
	"context"
	"errors"
	"io"
	"net"
)

// Match result constants
const (
	Match     = 1
	Mismatch  = -1
	Pending   = 0
)

// ProtocolMatcher defines the interface for protocol matchers
type ProtocolMatcher interface {
	// Match checks if the buffer matches the protocol
	// Returns: Match, Mismatch, or Pending
	Match(buf []byte) int
	// HandleConnection handles the connection after protocol is matched
	// firstRead contains data already read from the connection during detection
	HandleConnection(ctx context.Context, conn net.Conn, firstRead []byte) error
}

// MatchMissHandler handles the case when all matchers fail
type MatchMissHandler func(ctx context.Context, conn net.Conn, buf []byte) error

// ProtocolDetector detects protocols and delegates to appropriate handlers
type ProtocolDetector struct {
	matchers   []ProtocolMatcher
	missHandler MatchMissHandler
}

// NewProtocolDetector creates a new ProtocolDetector
func NewProtocolDetector(missHandler MatchMissHandler, matchers ...ProtocolMatcher) (*ProtocolDetector, error) {
	if len(matchers) == 0 {
		return nil, errors.New("no matcher for ProtocolDetector")
	}
	return &ProtocolDetector{
		matchers:    matchers,
		missHandler: missHandler,
	}, nil
}

// DetectAndHandle detects the protocol and handles the connection
func (d *ProtocolDetector) DetectAndHandle(ctx context.Context, conn net.Conn) error {
	// Read initial buffer
	buf := make([]byte, 0, 1024)
	tempBuf := make([]byte, 512)

	// First read
	n, err := conn.Read(tempBuf)
	if err != nil {
		return err
	}
	buf = append(buf, tempBuf[:n]...)

	// Try to match protocols
	for i := 0; i < len(d.matchers); {
		matcher := d.matchers[i]
		result := matcher.Match(buf)

		if result == Match {
			// Protocol matched, let the matcher handle the connection
			// Pass the already-read buffer to the handler
			return matcher.HandleConnection(ctx, conn, buf)
		}

		if result == Pending {
			// Need more data
			n, err := conn.Read(tempBuf)
			if err != nil {
				if err == io.EOF {
					return nil
				}
				return err
			}
			buf = append(buf, tempBuf[:n]...)
			continue
		}

		// Mismatch, try next matcher
		i++
	}

	// All matchers failed
	if d.missHandler != nil {
		return d.missHandler(ctx, conn, buf)
	}
	return nil
}
