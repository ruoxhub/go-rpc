package detector

import (
	"context"
	"encoding/binary"
	"net"

	"github.com/sekiro-go/sekiro-go/pkg/compress"
	"github.com/sekiro-go/sekiro-go/pkg/protocol"
)

// SekiroMatcher matches Sekiro binary protocol
type SekiroMatcher struct {
	compressManager *compress.CompressorManager
}

// NewSekiroMatcher creates a new SekiroMatcher
func NewSekiroMatcher() *SekiroMatcher {
	return &SekiroMatcher{
		compressManager: compress.NewCompressorManager(),
	}
}

// Magic header length for Sekiro protocol
const SekiroMagicLength = 8

// Match checks if the buffer matches Sekiro protocol
func (m *SekiroMatcher) Match(buf []byte) int {
	if len(buf) < SekiroMagicLength {
		return Pending
	}

	// Read magic number (big-endian int64)
	magic := int64(binary.BigEndian.Uint64(buf[:8]))

	if magic == protocol.Magic {
		return Match
	}
	return Mismatch
}

// HandleConnection handles the Sekiro protocol connection
func (m *SekiroMatcher) HandleConnection(ctx context.Context, conn net.Conn, firstRead []byte) error {
	handler := newSekiroHandler(conn, m.compressManager, firstRead)
	return handler.Handle(ctx)
}
