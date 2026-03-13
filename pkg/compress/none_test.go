package compress

import (
	"bytes"
	"testing"
)

func TestNoneCompressDecompress(t *testing.T) {
	tests := []struct {
		name  string
		input []byte
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
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			compressor := &NoneCompressor{}

			// Compress (pass-through)
			compressed, err := compressor.Compress(tt.input)
			if err != nil {
				t.Fatalf("Compress() error = %v", err)
			}

			// Verify no compression (data unchanged)
			if !bytes.Equal(tt.input, compressed) {
				t.Error("NoneCompressor.Compress() should return data unchanged")
			}

			// Decompress (pass-through)
			decompressed, err := compressor.Decompress(compressed)
			if err != nil {
				t.Fatalf("Decompress() error = %v", err)
			}

			// Verify data unchanged
			if !bytes.Equal(tt.input, decompressed) {
				t.Error("NoneCompressor.Decompress() should return data unchanged")
			}
		})
	}
}

func TestNoneMethod(t *testing.T) {
	compressor := &NoneCompressor{}
	want := "none"
	if got := compressor.Method(); got != want {
		t.Errorf("Method() = %v, want %v", got, want)
	}
}
