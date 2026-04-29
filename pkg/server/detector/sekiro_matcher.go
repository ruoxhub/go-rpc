package detector

import (
	"context"
	"encoding/binary"
	"net"

	"github.com/mrh30000/go-rpc/pkg/compress"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

// RpcMatcher matches Rpc binary protocol
type RpcMatcher struct {
	compressManager *compress.CompressorManager
}

// NewRpcMatcher creates a new RpcMatcher
func NewRpcMatcher() *RpcMatcher {
	return &RpcMatcher{
		compressManager: compress.NewCompressorManager(),
	}
}

// Magic header length for Rpc protocol
const RpcMagicLength = 8

// Match checks if the buffer matches Rpc protocol
func (m *RpcMatcher) Match(buf []byte) int {
	if len(buf) < RpcMagicLength {
		return Pending
	}

	// Read magic number (big-endian int64)
	magic := int64(binary.BigEndian.Uint64(buf[:8]))

	if magic == protocol.Magic {
		return Match
	}
	return Mismatch
}

// HandleConnection handles the Rpc protocol connection
func (m *RpcMatcher) HandleConnection(ctx context.Context, conn net.Conn, firstRead []byte) error {
	handler := newRpcHandler(conn, m.compressManager, firstRead)
	return handler.Handle(ctx)
}
