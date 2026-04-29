package client

import (
	"bufio"
	"encoding/json"
	"errors"
	"io"
	"math/rand"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

// RpcInvoker represents a Rpc invoker (caller)
type RpcInvoker struct {
	apiToken         string
	serverClients    []*invokerClient
	roundRobinIndex  int
	serialCounter    int32
	mu               sync.RWMutex
}

// invokerClient represents a connection to a Rpc server
type invokerClient struct {
	serverAddr string
	conn       *clientConnection
	alive      bool
}

// InvokeRequest represents an invoke request
type InvokeRequest struct {
	Group      string
	Api        string
	Params     map[string]interface{}
	Timeout    time.Duration
}

// InvokeResponse represents an invoke response
type InvokeResponse struct {
	Code    int         `json:"code"`
	Message string      `json:"message"`
	Data    interface{} `json:"data"`
}

// NewRpcInvoker creates a new RpcInvoker
func NewRpcInvoker(serverList []string) *RpcInvoker {
	return NewRpcInvokerWithToken("", serverList)
}

// NewRpcInvokerWithToken creates a new RpcInvoker with API token
func NewRpcInvokerWithToken(apiToken string, serverList []string) *RpcInvoker {
	invoker := &RpcInvoker{
		apiToken:      apiToken,
		serverClients: make([]*invokerClient, 0, len(serverList)),
	}

	// Shuffle server list for load balancing
	shuffled := make([]string, len(serverList))
	copy(shuffled, serverList)
	rand.Shuffle(len(shuffled), func(i, j int) {
		shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
	})

	// Create connections to all servers
	for _, server := range shuffled {
		client := invoker.createInvokerClient(server)
		if client != nil {
			invoker.serverClients = append(invoker.serverClients, client)
		}
	}

	return invoker
}

// createInvokerClient creates a connection to a Rpc server
func (s *RpcInvoker) createInvokerClient(config string) *invokerClient {
	server := config
	host := server
	port := 5612

	// Parse host:port
	if idx := indexOf(server, ':'); idx > 0 {
		host = server[:idx]
		port = parseInt(server[idx+1:])
	}

	addr := netJoinHostPort(host, port)
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		logger.Errorf("Failed to connect to server %s: %v", server, err)
		return nil
	}

	logger.Infof("Connected to invoker server at %s", addr)

	return &invokerClient{
		serverAddr: addr,
		conn: &clientConnection{
			conn:        conn,
			reader:      bufio.NewReader(conn),
			respWaiters: make(map[int32]chan *protocol.RpcPacket),
		},
		alive: true,
	}
}

// Invoke sends an invoke request
func (s *RpcInvoker) Invoke(req *InvokeRequest) (*InvokeResponse, error) {
	// Create invoke packet
	packet := protocol.PacketTypeIInvoke.NewPacket()
	packet.SetSerialNumber(s.generateSerialNumber())

	// Set headers
	packet.AddHeader("group", req.Group)
	packet.AddHeader("api", req.Api)
	if req.Timeout > 0 {
		packet.AddHeader("timeout", formatDuration(req.Timeout))
	}

	// Set data (JSON encoded params)
	data := encodeJSON(req.Params)
	packet.SetData(data)

	// Try servers in round-robin fashion
	var lastErr error
	for i := 0; i < len(s.serverClients); i++ {
		client := s.getNextClient()
		if client == nil || !client.alive {
			continue
		}

		// Send request
		if err := client.send(packet); err != nil {
			lastErr = err
			logger.Errorf("Send error: %v", err)
			client.alive = false
			continue
		}

		// Wait for response
		resp, err := client.waitForResponse(packet.SerialNumber, req.Timeout)
		if err != nil {
			lastErr = err
			continue
		}

		// Parse response
		return parseInvokeResponse(resp.Data)
	}

	if lastErr == nil {
		lastErr = errors.New("no available server")
	}
	return nil, lastErr
}

// getNextClient gets the next available client using round-robin
func (s *RpcInvoker) getNextClient() *invokerClient {
	s.mu.Lock()
	defer s.mu.Unlock()

	if len(s.serverClients) == 0 {
		return nil
	}

	// Proper round-robin with index
	s.roundRobinIndex = (s.roundRobinIndex + 1) % len(s.serverClients)
	return s.serverClients[s.roundRobinIndex]
}

// generateSerialNumber generates a unique serial number
func (s *RpcInvoker) generateSerialNumber() int32 {
	return int32(atomic.AddInt32(&s.serialCounter, 1))
}

// send sends a packet
func (c *invokerClient) send(packet *protocol.RpcPacket) error {
	if c.conn == nil {
		return io.ErrClosedPipe
	}

	var buf []byte
	encoder := &bufWriter{buf: &buf}
	if err := packet.Encode(encoder); err != nil {
		return err
	}

	_, err := c.conn.conn.Write(buf)
	return err
}

// waitForResponse waits for response with timeout
func (c *invokerClient) waitForResponse(seq int32, timeout time.Duration) (*protocol.RpcPacket, error) {
	if timeout <= 0 {
		timeout = 30 * time.Second
	}

	respChan := make(chan *protocol.RpcPacket, 1)

	c.conn.mu.Lock()
	c.conn.respWaiters[seq] = respChan
	c.conn.mu.Unlock()

	defer func() {
		c.conn.mu.Lock()
		delete(c.conn.respWaiters, seq)
		c.conn.mu.Unlock()
	}()

	select {
	case resp := <-respChan:
		return resp, nil
	case <-time.After(timeout):
		return nil, errors.New("timeout waiting for response")
	}
}

// Destroy destroys the invoker
func (s *RpcInvoker) Destroy() {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, client := range s.serverClients {
		if client.conn != nil {
			client.conn.close()
		}
	}
	s.serverClients = nil
}

// Helper functions

func indexOf(s string, ch byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == ch {
			return i
		}
	}
	return -1
}

func parseInt(s string) int {
	var n int
	for _, ch := range s {
		if ch >= '0' && ch <= '9' {
			n = n*10 + int(ch-'0')
		}
	}
	return n
}

func netJoinHostPort(host string, port int) string {
	return host + ":" + formatInt(port)
}

func formatInt(n int) string {
	if n == 0 {
		return "0"
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}

func formatDuration(d time.Duration) string {
	return d.String()
}

func encodeJSON(v interface{}) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return data
}

func parseInvokeResponse(data []byte) (*InvokeResponse, error) {
	// Simple JSON parsing (in production, use encoding/json)
	resp := &InvokeResponse{
		Code:    0,
		Message: "success",
		Data:    string(data),
	}
	return resp, nil
}
