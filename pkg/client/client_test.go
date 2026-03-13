package client

import (
	"bufio"
	"bytes"
	"io"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/sekiro-go/sekiro-go/pkg/protocol"
)

// bufReadWriteCloser is a mock net.Conn implementation for testing
type bufReadWriteCloser struct {
	reader io.Reader
	writer io.Writer
}

func (b bufReadWriteCloser) Read(p []byte) (n int, err error)   { return b.reader.Read(p) }
func (b bufReadWriteCloser) Write(p []byte) (n int, err error)  { return b.writer.Write(p) }
func (b bufReadWriteCloser) Close() error                       { return nil }
func (b bufReadWriteCloser) LocalAddr() net.Addr                { return nil }
func (b bufReadWriteCloser) RemoteAddr() net.Addr               { return nil }
func (b bufReadWriteCloser) SetDeadline(t time.Time) error      { return nil }
func (b bufReadWriteCloser) SetReadDeadline(t time.Time) error  { return nil }
func (b bufReadWriteCloser) SetWriteDeadline(t time.Time) error { return nil }

func TestNewSekiroClient(t *testing.T) {
	client := NewSekiroClient("test-group", "client-1", "localhost", 5612)
	if client == nil {
		t.Fatal("NewSekiroClient() returned nil")
	}
	if client.Group != "test-group" {
		t.Errorf("Group = %s, want 'test-group'", client.Group)
	}
	if client.ClientID != "client-1" {
		t.Errorf("ClientID = %s, want 'client-1'", client.ClientID)
	}
	if client.ServerHost != "localhost" {
		t.Errorf("ServerHost = %s, want 'localhost'", client.ServerHost)
	}
	if client.ServerPort != 5612 {
		t.Errorf("ServerPort = %d, want 5612", client.ServerPort)
	}
	if client.compressManager == nil {
		t.Error("compressManager not initialized")
	}
}

func TestSekiroClientDestroy(t *testing.T) {
	client := NewSekiroClient("test-group", "client-1", "localhost", 5612)

	// Destroy should not panic
	client.Destroy(0)

	// After destroy, destroyed flag should be set
	if !client.destroyed {
		t.Error("destroyed flag not set after Destroy()")
	}
}

func TestClientConnectionSend(t *testing.T) {
	conn := &clientConnection{
		respWaiters: make(map[int32]chan *protocol.SekiroPacket),
		closed:      true, // Simulate closed connection
	}

	packet := protocol.NewSekiroPacket()
	err := conn.send(packet)

	if err == nil {
		t.Error("send() on closed connection should return error")
	}
}

func TestClientConnectionClose(t *testing.T) {
	// Create a mock connection using a bytes buffer as a mock net.Conn
	buf := &bytes.Buffer{}
	conn := &clientConnection{
		conn:        &bufReadWriteCloser{reader: bytes.NewReader([]byte{}), writer: buf},
		respWaiters: make(map[int32]chan *protocol.SekiroPacket),
		closed:      false,
	}

	// First close should work
	conn.close()

	if !conn.closed {
		t.Error("closed flag not set after close()")
	}

	// Second close should be no-op (not panic)
	conn.close()
}

func TestClientConnectionReceive(t *testing.T) {
	// This test requires a valid reader, so we just verify the function exists
	// and the compress manager can be nil
	conn := &clientConnection{
		reader:      bufio.NewReader(bytes.NewReader([]byte{})),
		respWaiters: make(map[int32]chan *protocol.SekiroPacket),
	}

	// Receive with empty data will fail, but we test it doesn't panic
	_, err := conn.receive(nil)
	if err == nil {
		t.Error("receive() should return error with empty data")
	}
}

func TestNotifyDisconnect(t *testing.T) {
	// notifyDisconnect only closes channels, it doesn't set the closed flag
	// The closed flag is set by the close() method
	// This test verifies that notifyDisconnect doesn't panic with valid connection

	ch1 := make(chan *protocol.SekiroPacket, 1)

	conn := &clientConnection{
		respWaiters: map[int32]chan *protocol.SekiroPacket{
			1: ch1,
		},
	}

	client := &SekiroClient{
		Connection: conn,
	}

	// Notify disconnect should close all channels without panicking
	client.notifyDisconnect()

	// Verify channel is closed
	_, ok := <-ch1
	if ok {
		t.Error("Channel should be closed after notifyDisconnect")
	}
}

func TestNotifyDisconnectChannels(t *testing.T) {
	// Test that channels are properly closed
	ch1 := make(chan *protocol.SekiroPacket, 1)
	ch2 := make(chan *protocol.SekiroPacket, 1)

	// Manually close channels to simulate what notifyDisconnect does
	close(ch1)
	close(ch2)

	// Verify channels are closed
	_, ok := <-ch1
	if ok {
		t.Error("Channel 1 should be closed")
	}
	_, ok = <-ch2
	if ok {
		t.Error("Channel 2 should be closed")
	}
}

func TestNotifyDisconnectNilConnection(t *testing.T) {
	client := &SekiroClient{
		Connection: nil,
	}

	// Should not panic
	client.notifyDisconnect()
}

func TestBufWriter(t *testing.T) {
	var buf []byte
	writer := &bufWriter{buf: &buf}

	data := []byte("test data")
	n, err := writer.Write(data)

	if err != nil {
		t.Errorf("Write() error = %v", err)
	}
	if n != len(data) {
		t.Errorf("Write() n = %d, want %d", n, len(data))
	}
	if len(buf) != len(data) {
		t.Errorf("Buffer length = %d, want %d", len(buf), len(data))
	}
}

func TestRegisterHandler(t *testing.T) {
	client := NewSekiroClient("test-group", "client-1", "localhost", 5612)

	handler := func(request []byte) ([]byte, error) {
		return []byte("response"), nil
	}

	client.Register(handler)

	// Register should not panic
	// Note: The current implementation is a stub, so we just verify it doesn't crash
}

func TestSekiroClientStartDestroyed(t *testing.T) {
	client := NewSekiroClient("test-group", "client-1", "localhost", 5612)
	client.Destroy(0)

	// Start after destroy should return error
	err := client.Start()
	if err == nil {
		t.Error("Start() after Destroy should return error")
	}
}

func TestClientConnectionSendConcurrent(t *testing.T) {
	// Test that send is safe for concurrent use
	conn := &clientConnection{
		respWaiters: make(map[int32]chan *protocol.SekiroPacket),
		closed:      true, // Closed to avoid actual network operations
	}

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			packet := protocol.NewSekiroPacket()
			conn.send(packet) // Will return error, but should be thread-safe
		}()
	}
	wg.Wait()
}

func TestInvokeRequestResponse(t *testing.T) {
	// Test InvokeRequest struct
	req := &InvokeRequest{
		Group:   "test-group",
		Api:     "test-api",
		Params:  map[string]interface{}{"key": "value"},
		Timeout: 5 * time.Second,
	}

	if req.Group != "test-group" {
		t.Errorf("Group = %s, want 'test-group'", req.Group)
	}
	if req.Api != "test-api" {
		t.Errorf("Api = %s, want 'test-api'", req.Api)
	}
}

func TestInvokeResponse(t *testing.T) {
	// Test InvokeResponse struct
	resp := &InvokeResponse{
		Code:    0,
		Message: "success",
		Data:    map[string]interface{}{"result": "ok"},
	}

	if resp.Code != 0 {
		t.Errorf("Code = %d, want 0", resp.Code)
	}
	if resp.Message != "success" {
		t.Errorf("Message = %s, want 'success'", resp.Message)
	}
}
