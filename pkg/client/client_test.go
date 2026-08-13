package client

import (
	"io"
	"testing"

	"github.com/mrh30000/go-rpc/pkg/protocol"
)

type protocolMetadataConnection struct{}

func (protocolMetadataConnection) Send([]byte) error        { return nil }
func (protocolMetadataConnection) Receive() ([]byte, error) { return nil, io.EOF }
func (protocolMetadataConnection) Close() error             { return nil }
func (protocolMetadataConnection) RemoteAddr() string       { return "test" }

func TestRpcClientProtocolMetadataIsCopied(t *testing.T) {
	c := NewRpcClient("g", "c", protocolMetadataConnection{})
	input := []string{protocol.CapabilityInvocationContextV1}
	c.SetProtocol(1, input)
	input[0] = "mutated"
	got := c.Capabilities()
	got[0] = "mutated-again"
	if !c.SupportsCapability(protocol.CapabilityInvocationContextV1) {
		t.Fatal("capability snapshot was mutable")
	}
	if c.ProtocolVersion() != 1 {
		t.Fatalf("version = %d", c.ProtocolVersion())
	}
}
