package compress

import (
	"errors"
	"strings"

	"github.com/mrh30000/go-rpc/pkg/protocol"
)

// CompressorManager manages multiple compression algorithms
type CompressorManager struct {
	compressors map[string]Compressor
}

// NewCompressorManager creates a new CompressorManager with default compressors
func NewCompressorManager() *CompressorManager {
	m := &CompressorManager{
		compressors: make(map[string]Compressor),
	}
	m.setupDefaultCompressor()
	return m
}

// setupDefaultCompressor registers default compressors
func (m *CompressorManager) setupDefaultCompressor() {
	m.RegisterCompressor(&GzipCompressor{})
	m.RegisterCompressor(&NoneCompressor{})
	m.RegisterCompressor(&SnappyCompressor{})
}

// RegisterCompressor registers a compressor
func (m *CompressorManager) RegisterCompressor(c Compressor) *CompressorManager {
	m.compressors[strings.TrimSpace(c.Method())] = c
	return m
}

// fetchCompressor gets the compressor for a packet based on headers
func (m *CompressorManager) fetchCompressor(packet *protocol.RpcPacket) Compressor {
	// Only compress response packets
	if packet.Type != byte(protocol.PacketTypeInvokeResponse) &&
		packet.Type != byte(protocol.PacketTypeSInvokeResponse) {
		return nil
	}

	method := packet.GetHeader("compress_method")
	if method == "" {
		return nil
	}

	compressor, ok := m.compressors[strings.TrimSpace(method)]
	if !ok {
		return nil
	}

	return compressor
}

// HandleDecompress decompresses packet data if needed
func (m *CompressorManager) HandleDecompress(packet *protocol.RpcPacket) error {
	compressor := m.fetchCompressor(packet)
	if compressor == nil {
		return nil
	}

	decompressed, err := compressor.Decompress(packet.Data)
	if err != nil {
		return err
	}

	packet.Data = decompressed
	return nil
}

// DoCompress compresses packet data if needed
func (m *CompressorManager) DoCompress(packet *protocol.RpcPacket) error {
	compressor := m.fetchCompressor(packet)
	if compressor == nil {
		return nil
	}

	if len(packet.Data) < 1024 {
		delete(packet.Headers, "compress_method")
		return nil
	}

	compressed, err := compressor.Compress(packet.Data)
	if err != nil {
		return err
	}

	packet.Data = compressed
	return nil
}

// GetCompressor gets a compressor by method name
func (m *CompressorManager) GetCompressor(method string) (Compressor, error) {
	c, ok := m.compressors[strings.TrimSpace(method)]
	if !ok {
		return nil, errors.New("compressor not found: " + method)
	}
	return c, nil
}
