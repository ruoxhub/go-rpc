package compress

import (
	"bytes"
	"testing"

	"github.com/mrh30000/go-rpc/pkg/protocol"
)

func TestCompressorManager(t *testing.T) {
	manager := NewCompressorManager()

	// Test GetCompressor
	tests := []struct {
		name    string
		method  string
		wantErr bool
	}{
		{name: "gzip", method: "gzip", wantErr: false},
		{name: "snappy", method: "snappy", wantErr: false},
		{name: "none", method: "none", wantErr: false},
		{name: "unknown", method: "unknown", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := manager.GetCompressor(tt.method)
			if (err != nil) != tt.wantErr {
				t.Errorf("GetCompressor(%q) error = %v, wantErr %v", tt.method, err, tt.wantErr)
			}
		})
	}
}

func TestCompressorManagerDoCompress(t *testing.T) {
	manager := NewCompressorManager()

	tests := []struct {
		name           string
		packetType     byte
		compressMethod string
		inputData      []byte
		expectCompress bool
	}{
		{
			name:           "invoke response with gzip",
			packetType:     byte(protocol.PacketTypeInvokeResponse),
			compressMethod: "gzip",
			inputData:      []byte("test data"),
			expectCompress: true,
		},
		{
			name:           "S invoke response with gzip",
			packetType:     byte(protocol.PacketTypeSInvokeResponse),
			compressMethod: "gzip",
			inputData:      []byte("test data"),
			expectCompress: true,
		},
		{
			name:           "heartbeat packet",
			packetType:     byte(protocol.PacketTypeHeartbeat),
			compressMethod: "gzip",
			inputData:      []byte("test data"),
			expectCompress: false,
		},
		{
			name:           "no compress method",
			packetType:     byte(protocol.PacketTypeInvokeResponse),
			compressMethod: "",
			inputData:      []byte("test data"),
			expectCompress: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			originalData := make([]byte, len(tt.inputData))
			copy(originalData, tt.inputData)

			packet := protocol.NewRpcPacket()
			packet.Type = tt.packetType
			packet.Data = tt.inputData
			packet.AddHeader("compress_method", tt.compressMethod)

			err := manager.DoCompress(packet)
			if err != nil {
				t.Fatalf("DoCompress() error = %v", err)
			}

			if tt.expectCompress {
				// Data should be compressed (different from original for non-empty data)
				if len(tt.inputData) > 10 && bytes.Equal(originalData, packet.Data) {
					t.Error("DoCompress() should have compressed the data")
				}

				// Verify we can decompress it back
				err = manager.HandleDecompress(packet)
				if err != nil {
					t.Fatalf("HandleDecompress() error = %v", err)
				}

				if !bytes.Equal(originalData, packet.Data) {
					t.Error("Round-trip compress/decompress failed")
				}
			} else {
				// Data should be unchanged
				if !bytes.Equal(originalData, packet.Data) {
					t.Error("DoCompress() should not have modified the data")
				}
			}
		})
	}
}

func TestCompressorManagerHandleDecompress(t *testing.T) {
	manager := NewCompressorManager()

	// First compress some data
	originalData := []byte("test data for decompression")
	compressor, _ := manager.GetCompressor("gzip")
	compressedData, _ := compressor.Compress(originalData)

	packet := protocol.NewRpcPacket()
	packet.Type = byte(protocol.PacketTypeInvokeResponse)
	packet.Data = compressedData
	packet.AddHeader("compress_method", "gzip")

	// Decompress
	err := manager.HandleDecompress(packet)
	if err != nil {
		t.Fatalf("HandleDecompress() error = %v", err)
	}

	// Verify decompressed data matches original
	if !bytes.Equal(originalData, packet.Data) {
		t.Errorf("HandleDecompress() failed: got %v, want %v", packet.Data, originalData)
	}
}

func TestCompressorManager_RegisterCompressor(t *testing.T) {
	manager := &CompressorManager{
		compressors: make(map[string]Compressor),
	}

	// Register a custom compressor
	customCompressor := &NoneCompressor{}
	result := manager.RegisterCompressor(customCompressor)

	// Verify it was registered
	if result != manager {
		t.Error("RegisterCompressor should return self for chaining")
	}

	_, err := manager.GetCompressor("none")
	if err != nil {
		t.Errorf("GetCompressor() failed after registration: %v", err)
	}
}
