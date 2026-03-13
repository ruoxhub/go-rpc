package compress

import (
	"bytes"
	"testing"
)

func TestSnappyCompressDecompress(t *testing.T) {
	tests := []struct {
		name     string
		input    []byte
		wantErr  bool
	}{
		{
			name:  "simple text",
			input: []byte("Hello, World!"),
		},
		{
			name:  "empty data",
			input: []byte(""),
		},
		{
			name:  "binary data",
			input: []byte{0x00, 0x01, 0x02, 0x03, 0xFF, 0xFE, 0xFD},
		},
		{
			name:  "large data",
			input: bytes.Repeat([]byte("test data"), 1000),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			compressor := &SnappyCompressor{}

			// Compress
			compressed, err := compressor.Compress(tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("Compress() error = %v, wantErr %v", err, tt.wantErr)
			}
			if err != nil {
				return
			}

			// Decompress
			decompressed, err := compressor.Decompress(compressed)
			if err != nil {
				t.Fatalf("Decompress() error = %v", err)
			}

			// Verify round-trip
			if !bytes.Equal(tt.input, decompressed) {
				t.Errorf("Round-trip failed: got %v, want %v", decompressed, tt.input)
			}
		})
	}
}

func TestSnappyMethod(t *testing.T) {
	compressor := &SnappyCompressor{}
	want := "snappy"
	if got := compressor.Method(); got != want {
		t.Errorf("Method() = %v, want %v", got, want)
	}
}

func TestSnappyInvalidData(t *testing.T) {
	compressor := &SnappyCompressor{}

	// Try to decompress invalid snappy data
	invalidData := []byte{0xFF, 0xFF, 0xFF, 0xFF}
	_, err := compressor.Decompress(invalidData)
	if err == nil {
		t.Error("Decompress() expected error for invalid data, got nil")
	}
}
