// Package compress implements compression algorithms for Rpc protocol
package compress

import (
	"bytes"
	"compress/gzip"
	"io"
	"sync"
)

// Compressor defines the interface for compression algorithms
type Compressor interface {
	Method() string
	Compress(input []byte) ([]byte, error)
	Decompress(input []byte) ([]byte, error)
}

// GzipCompressor implements gzip compression
type GzipCompressor struct {
	writerPool sync.Pool
	readerPool sync.Pool
	once       sync.Once
}

func (g *GzipCompressor) init() {
	g.writerPool.New = func() interface{} {
		return gzip.NewWriter(io.Discard)
	}
}

// Method returns the compression method name
func (g *GzipCompressor) Method() string {
	return "gzip"
}

// Compress compresses input data using gzip
func (g *GzipCompressor) Compress(input []byte) ([]byte, error) {
	g.once.Do(g.init)

	var buf bytes.Buffer
	gw := g.writerPool.Get().(*gzip.Writer)
	gw.Reset(&buf)
	defer g.writerPool.Put(gw)

	if _, err := gw.Write(input); err != nil {
		_ = gw.Close()
		return nil, err
	}

	if err := gw.Close(); err != nil {
		return nil, err
	}

	return buf.Bytes(), nil
}

// Decompress decompresses gzip data
func (g *GzipCompressor) Decompress(input []byte) ([]byte, error) {
	g.once.Do(g.init)

	grVal := g.readerPool.Get()
	gr, ok := grVal.(*gzip.Reader)
	if !ok || gr == nil {
		var err error
		gr, err = gzip.NewReader(bytes.NewReader(input))
		if err != nil {
			return nil, err
		}
	} else {
		err := gr.Reset(bytes.NewReader(input))
		if err != nil {
			return nil, err
		}
	}

	defer func() {
		gr.Close()
		g.readerPool.Put(gr)
	}()

	return io.ReadAll(gr)
}
