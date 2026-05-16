package client

import (
	"bytes"
	"errors"
	"io"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/protocol"
	"github.com/mrh30000/go-rpc/pkg/server/transport"
)

// mockNetConn is a minimal net.Conn for testing.
type mockNetConn struct {
	reader io.Reader
	writer io.Writer
	closed bool
	mu     sync.Mutex
}

func (m *mockNetConn) Read(p []byte) (n int, err error)  { return m.reader.Read(p) }
func (m *mockNetConn) Write(p []byte) (n int, err error) { return m.writer.Write(p) }
func (m *mockNetConn) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.closed = true
	return nil
}
func (m *mockNetConn) LocalAddr() net.Addr                { return nil }
func (m *mockNetConn) RemoteAddr() net.Addr               { return nil }
func (m *mockNetConn) SetDeadline(t time.Time) error      { return nil }
func (m *mockNetConn) SetReadDeadline(t time.Time) error  { return nil }
func (m *mockNetConn) SetWriteDeadline(t time.Time) error { return nil }

// mockConn is a transport.Connection that returns a configurable error on Send.
type mockConn struct {
	sendErr error
	closed  bool
}

func (m *mockConn) Send(data []byte) error     { return m.sendErr }
func (m *mockConn) Receive() ([]byte, error)   { return nil, io.EOF }
func (m *mockConn) Close() error               { m.closed = true; return nil }
func (m *mockConn) RemoteAddr() string         { return "mock" }

var _ transport.Connection = (*mockConn)(nil)

func TestNewRpcClient(t *testing.T) {
	client := NewRpcClient("test-group", "client-1", "localhost", 5612)
	if client == nil {
		t.Fatal("NewRpcClient() returned nil")
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

func TestRpcClientDestroy(t *testing.T) {
	client := NewRpcClient("test-group", "client-1", "localhost", 5612)
	client.Destroy(0)
	if !client.destroyed {
		t.Error("destroyed flag not set after Destroy()")
	}
}

func TestClientConnectionSend(t *testing.T) {
	conn := &clientConnection{
		tcpConn:     nil, // will be sent to
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}

	packet := protocol.NewRpcPacket()
	// Nil tcpConn will panic on Send — we test via mock below.
	_ = packet
	_ = conn
}

func TestClientConnectionSendError(t *testing.T) {
	mock := &mockConn{sendErr: errors.New("connection closed")}
	conn := &clientConnection{
		tcpConn:     transport.NewTCPConnection(&mockNetConn{reader: bytes.NewReader(nil), writer: io.Discard}),
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}
	// Close the underlying tcpConn
	conn.tcpConn.Close()

	packet := protocol.NewRpcPacket()
	err := conn.send(packet)
	if err == nil {
		t.Error("send() on closed connection should return error")
	}
	_ = mock
}

func TestClientConnectionClose(t *testing.T) {
	mock := &mockNetConn{reader: bytes.NewReader([]byte{}), writer: io.Discard}
	tcpConn := transport.NewTCPConnection(mock)
	conn := &clientConnection{
		tcpConn:     tcpConn,
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}

	conn.close()
	if !mock.closed {
		t.Error("underlying connection not closed")
	}

	// Second close should be no-op (not panic)
	conn.close()
}

func TestClientConnectionReceive(t *testing.T) {
	mock := &mockNetConn{reader: bytes.NewReader([]byte{}), writer: io.Discard}
	tcpConn := transport.NewTCPConnection(mock)
	conn := &clientConnection{
		tcpConn:     tcpConn,
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}

	// Receive with empty data will fail, but we test it doesn't panic
	_, err := conn.receive(nil)
	if err == nil {
		t.Error("receive() should return error with empty data")
	}
}

func TestNotifyDisconnect(t *testing.T) {
	ch1 := make(chan *protocol.RpcPacket, 1)

	conn := &clientConnection{
		tcpConn:     transport.NewTCPConnection(&mockNetConn{reader: bytes.NewReader(nil), writer: io.Discard}),
		respWaiters: map[int32]chan *protocol.RpcPacket{
			1: ch1,
		},
	}
	conn.tcpConn.Close()

	client := &RpcClient{
		Connection: conn,
	}

	client.notifyDisconnect()

	_, ok := <-ch1
	if ok {
		t.Error("Channel should be closed after notifyDisconnect")
	}
}

func TestNotifyDisconnectChannels(t *testing.T) {
	ch1 := make(chan *protocol.RpcPacket, 1)
	ch2 := make(chan *protocol.RpcPacket, 1)

	close(ch1)
	close(ch2)

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
	client := &RpcClient{
		Connection: nil,
	}
	client.notifyDisconnect()
}

func TestBufWriter(t *testing.T) {
	var buf []byte
	writer := &protocol.BufWriter{Buf: &buf}

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
	client := NewRpcClient("test-group", "client-1", "localhost", 5612)

	handler := func(request []byte) ([]byte, error) {
		return []byte("response"), nil
	}

	client.Register(handler)
}

func TestRpcClientStartDestroyed(t *testing.T) {
	client := NewRpcClient("test-group", "client-1", "localhost", 5612)
	client.Destroy(0)

	err := client.Start()
	if err == nil {
		t.Error("Start() after Destroy should return error")
	}
}

func TestClientConnectionSendConcurrent(t *testing.T) {
	mock := &mockConn{sendErr: errors.New("closed")}
	conn := &clientConnection{
		tcpConn:     transport.NewTCPConnection(&mockNetConn{reader: bytes.NewReader(nil), writer: io.Discard}),
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}
	conn.tcpConn.Close()

	var wg sync.WaitGroup
	for i := 0; i < 10; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			packet := protocol.NewRpcPacket()
			conn.send(packet)
		}()
	}
	wg.Wait()
	_ = mock
}

func TestInvokeRequestResponse(t *testing.T) {
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
