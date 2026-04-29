// Package compress implements compression algorithms for Rpc protocol
package compress

import (
	"bytes"
	"compress/gzip"
	"io"
)

// Compressor defines the interface for compression algorithms
type Compressor interface {
	Method() string
	Compress(input []byte) ([]byte, error)
	Decompress(input []byte) ([]byte, error)
}

// GzipCompressor implements gzip compression
type GzipCompressor struct{}

// Method returns the compression method name
func (g *GzipCompressor) Method() string {
	return "gzip"
}

// Compress compresses input data using gzip
func (g *GzipCompressor) Compress(input []byte) ([]byte, error) {
	var buf bytes.Buffer
	gw := gzip.NewWriter(&buf)
	_, err := gw.Write(input)
	if err != nil {
		gw.Close()
		return nil, err
	}
	err = gw.Close()
	if err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// Decompress decompresses gzip data
func (g *GzipCompressor) Decompress(input []byte) ([]byte, error) {
	gr, err := gzip.NewReader(bytes.NewReader(input))
	if err != nil {
		return nil, err
	}
	defer gr.Close()
	return io.ReadAll(gr)
}
