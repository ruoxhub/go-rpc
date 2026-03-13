package detector

import (
	"context"
	"encoding/binary"
	"net"
	"testing"

	"github.com/sekiro-go/sekiro-go/pkg/protocol"
)

func TestSekiroMatcher(t *testing.T) {
	matcher := NewSekiroMatcher()

	tests := []struct {
		name   string
		buf    []byte
		want   int
	}{
		{
			name: "valid sekiro magic",
			buf: func() []byte {
				buf := make([]byte, 8)
				binary.BigEndian.PutUint64(buf, uint64(protocol.Magic))
				return buf
			}(),
			want: Match,
		},
		{
			name: "invalid magic",
			buf:  []byte{0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07},
			want: Mismatch,
		},
		{
			name: "incomplete magic",
			buf:  []byte{0x73, 0x65, 0x6B, 0x69, 0x72}, // only 5 bytes
			want: Pending,
		},
		{
			name: "empty buffer",
			buf:  []byte{},
			want: Pending,
		},
		{
			name: "partial buffer",
			buf:  []byte{0x73}, // 1 byte
			want: Pending,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := matcher.Match(tt.buf)
			if got != tt.want {
				t.Errorf("Match() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestHttpMatcher(t *testing.T) {
	matcher := NewHttpMatcher()

	tests := []struct {
		name string
		buf  []byte
		want int
	}{
		{name: "GET request", buf: []byte("GET /api HTTP/1.1\r\n"), want: Match},
		{name: "POST request", buf: []byte("POST /api HTTP/1.1\r\n"), want: Match},
		{name: "PUT request", buf: []byte("PUT /api HTTP/1.1\r\n"), want: Match},
		{name: "DELETE request", buf: []byte("DELETE /api HTTP/1.1\r\n"), want: Match},
		{name: "HEAD request", buf: []byte("HEAD /api HTTP/1.1\r\n"), want: Match},
		{name: "OPTIONS request", buf: []byte("OPTIONS /api HTTP/1.1\r\n"), want: Match},
		{name: "PATCH request", buf: []byte("PATCH /api HTTP/1.1\r\n"), want: Match},
		{name: "invalid HTTP", buf: []byte("INVALID HTTP/1.1\r\n"), want: Mismatch},
		{name: "incomplete", buf: []byte("GE"), want: Pending},
		{name: "empty", buf: []byte{}, want: Pending},
		{name: "binary data", buf: []byte{0x00, 0x01, 0x02, 0x03}, want: Mismatch},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := matcher.Match(tt.buf)
			if got != tt.want {
				t.Errorf("Match() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestProtocolDetector(t *testing.T) {
	sekiroMatcher := NewSekiroMatcher()
	httpMatcher := NewHttpMatcher()

	missHandler := func(ctx context.Context, conn net.Conn, buf []byte) error {
		return nil
	}

	detector, err := NewProtocolDetector(missHandler, sekiroMatcher, httpMatcher)
	if err != nil {
		t.Fatalf("NewProtocolDetector() error = %v", err)
	}
	if detector == nil {
		t.Fatal("NewProtocolDetector() returned nil")
	}
}

func TestProtocolDetectorNoMatchers(t *testing.T) {
	missHandler := func(ctx context.Context, conn net.Conn, buf []byte) error {
		return nil
	}

	_, err := NewProtocolDetector(missHandler)
	if err == nil {
		t.Error("NewProtocolDetector() expected error with no matchers, got nil")
	}
}
