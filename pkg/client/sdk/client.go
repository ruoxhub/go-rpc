// Package client implements the Rpc client SDK
package client

import (
	"bytes"
	"fmt"
	"io"
	"net"
	"sync"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/compress"
	"github.com/mrh30000/go-rpc/pkg/protocol"
	"github.com/mrh30000/go-rpc/pkg/transport"
)

// RpcClient represents a Rpc client connection
type RpcClient struct {
	Group           string
	ClientID        string
	ServerHost      string
	ServerPort      int
	Connection      *clientConnection
	compressManager *compress.CompressorManager
	mu              sync.Mutex
	destroyed       bool
}

// clientConnection holds the actual network connection and handlers
type clientConnection struct {
	tcpConn     *transport.TCPConnection
	mu          sync.Mutex
	sendSeq     int32
	respWaiters map[int32]chan *protocol.RpcPacket
}

// NewRpcClient creates a new RpcClient
func NewRpcClient(group, clientID, serverHost string, serverPort int) *RpcClient {
	return &RpcClient{
		Group:           group,
		ClientID:        clientID,
		ServerHost:      serverHost,
		ServerPort:      serverPort,
		compressManager: compress.NewCompressorManager(),
	}
}

// Start connects to the server and starts handling messages
func (c *RpcClient) Start() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.destroyed {
		return io.ErrClosedPipe
	}

	addr := net.JoinHostPort(c.ServerHost, fmt.Sprintf("%d", c.ServerPort))
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		return err
	}

	c.Connection = &clientConnection{
		tcpConn:     transport.NewTCPConnection(conn),
		respWaiters: make(map[int32]chan *protocol.RpcPacket),
	}

	logger.Infof("Connected to Rpc server at %s", addr)

	if err := c.sendRegister(); err != nil {
		conn.Close()
		return err
	}

	go c.readLoop()

	return nil
}

// sendRegister sends registration packet to server
func (c *RpcClient) sendRegister() error {
	packet := protocol.PacketTypeRegister.NewPacket()
	packet.AddHeader("group", c.Group)
	packet.AddHeader("clientId", c.ClientID)
	return c.Connection.send(packet)
}

// readLoop reads packets from the server
func (c *RpcClient) readLoop() {
	for {
		packet, err := c.Connection.receive(c.compressManager)
		if err != nil {
			if err == io.EOF {
				logger.Debug("Connection closed by server")
			} else {
				logger.Errorf("Receive error: %v", err)
			}
			c.handleDisconnect()
			return
		}

		go c.handlePacket(packet)
	}
}

// handlePacket handles received packets
func (c *RpcClient) handlePacket(packet *protocol.RpcPacket) {
	logger.Debugf("Received packet: type=%s", protocol.RpcPacketType(packet.Type))

	switch protocol.RpcPacketType(packet.Type) {
	case protocol.PacketTypeHeartbeat:
		c.Connection.send(packet)

	case protocol.PacketTypeSInvoke:
		c.handleInvoke(packet)

	case protocol.PacketTypeSCmd:
		c.handleCommand(packet)
	}
}

// handleInvoke handles invoke request
func (c *RpcClient) handleInvoke(packet *protocol.RpcPacket) {
	logger.Debug("Invoke request received")
}

// handleCommand handles command
func (c *RpcClient) handleCommand(packet *protocol.RpcPacket) {
	logger.Debug("Command received")
}

// handleDisconnect handles disconnection
func (c *RpcClient) handleDisconnect() {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.Connection != nil {
		c.Connection.close()
		c.Connection = nil
	}

	c.notifyDisconnect()
}

// notifyDisconnect notifies all waiting responses
func (c *RpcClient) notifyDisconnect() {
	if c.Connection == nil {
		return
	}

	c.Connection.mu.Lock()
	defer c.Connection.mu.Unlock()

	for seq, ch := range c.Connection.respWaiters {
		close(ch)
		delete(c.Connection.respWaiters, seq)
	}
}

// Destroy destroys the client
func (c *RpcClient) Destroy(waitSeconds int64) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.destroyed = true
	if c.Connection != nil {
		c.Connection.close()
		c.Connection = nil
	}
}

// send sends a packet
func (c *clientConnection) send(packet *protocol.RpcPacket) error {
	var buf []byte
	encoder := &protocol.BufWriter{Buf: &buf}
	if err := packet.Encode(encoder); err != nil {
		return err
	}

	return c.tcpConn.Send(buf)
}

// receive receives a packet
func (c *clientConnection) receive(compressManager *compress.CompressorManager) (*protocol.RpcPacket, error) {
	raw, err := c.tcpConn.Receive()
	if err != nil {
		return nil, err
	}

	packet, err := protocol.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}

	if compressManager != nil {
		if err := compressManager.HandleDecompress(packet); err != nil {
			logger.Errorf("Decompression failed: %v", err)
			return nil, err
		}
	}

	return packet, nil
}

// close closes the connection
func (c *clientConnection) close() {
	c.tcpConn.Close()
}

// RegisterHandler registers a handler for incoming invocations
type RegisterHandler func(request []byte) ([]byte, error)

// Register registers a handler for the client
func (c *RpcClient) Register(handler RegisterHandler) {
	_ = handler
}
