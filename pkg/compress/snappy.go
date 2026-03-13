package compress

import (
	"github.com/golang/snappy"
)

// SnappyCompressor implements snappy compression
type SnappyCompressor struct{}

// Method returns the compression method name
func (s *SnappyCompressor) Method() string {
	return "snappy"
}

// Compress compresses input data using snappy
func (s *SnappyCompressor) Compress(input []byte) ([]byte, error) {
	return snappy.Encode(nil, input), nil
}

// Decompress decompresses snappy data
func (s *SnappyCompressor) Decompress(input []byte) ([]byte, error) {
	return snappy.Decode(nil, input)
}
