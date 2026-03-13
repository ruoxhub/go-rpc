// Package client implements the Sekiro client SDK
package client

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"sync"

	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/compress"
	"github.com/sekiro-go/sekiro-go/pkg/protocol"
)

// SekiroClient represents a Sekiro client connection
type SekiroClient struct {
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
	conn       net.Conn
	reader     *bufio.Reader
	closed     bool
	mu         sync.Mutex
	sendSeq    int32
	respWaiters map[int32]chan *protocol.SekiroPacket
}

// NewSekiroClient creates a new SekiroClient
func NewSekiroClient(group, clientID, serverHost string, serverPort int) *SekiroClient {
	return &SekiroClient{
		Group:           group,
		ClientID:        clientID,
		ServerHost:      serverHost,
		ServerPort:      serverPort,
		compressManager: compress.NewCompressorManager(),
	}
}

// Start connects to the server and starts handling messages
func (c *SekiroClient) Start() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.destroyed {
		return io.ErrClosedPipe
	}

	// Connect to server
	addr := fmt.Sprintf("%s:%d", c.ServerHost, c.ServerPort)
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		return err
	}

	c.Connection = &clientConnection{
		conn:        conn,
		reader:      bufio.NewReader(conn),
		respWaiters: make(map[int32]chan *protocol.SekiroPacket),
	}

	logger.Infof("Connected to Sekiro server at %s", addr)

	// Send registration packet
	if err := c.sendRegister(); err != nil {
		conn.Close()
		return err
	}

	// Start read loop
	go c.readLoop()

	return nil
}

// sendRegister sends registration packet to server
func (c *SekiroClient) sendRegister() error {
	packet := protocol.PacketTypeRegister.NewPacket()
	packet.AddHeader("group", c.Group)
	packet.AddHeader("clientId", c.ClientID)
	return c.Connection.send(packet)
}

// readLoop reads packets from the server
func (c *SekiroClient) readLoop() {
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

		// Handle packet
		go c.handlePacket(packet)
	}
}

// handlePacket handles received packets
func (c *SekiroClient) handlePacket(packet *protocol.SekiroPacket) {
	logger.Debugf("Received packet: type=%s", protocol.SekiroPacketType(packet.Type))

	switch protocol.SekiroPacketType(packet.Type) {
	case protocol.PacketTypeHeartbeat:
		// Echo heartbeat
		c.Connection.send(packet)

	case protocol.PacketTypeSInvoke:
		// Handle invoke request from server
		c.handleInvoke(packet)

	case protocol.PacketTypeSCmd:
		// Handle command from server
		c.handleCommand(packet)
	}
}

// handleInvoke handles invoke request
func (c *SekiroClient) handleInvoke(packet *protocol.SekiroPacket) {
	// User should implement their own handler
	logger.Debug("Invoke request received")
}

// handleCommand handles command
func (c *SekiroClient) handleCommand(packet *protocol.SekiroPacket) {
	logger.Debug("Command received")
}

// handleDisconnect handles disconnection
func (c *SekiroClient) handleDisconnect() {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.Connection != nil {
		c.Connection.close()
		c.Connection = nil
	}

	// Notify waiters
	c.notifyDisconnect()
}

// notifyDisconnect notifies all waiting responses
func (c *SekiroClient) notifyDisconnect() {
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
func (c *SekiroClient) Destroy(waitSeconds int64) {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.destroyed = true
	if c.Connection != nil {
		c.Connection.close()
		c.Connection = nil
	}
}

// send sends a packet
func (c *clientConnection) send(packet *protocol.SekiroPacket) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return io.ErrClosedPipe
	}

	var buf []byte
	encoder := &bufWriter{buf: &buf}
	if err := packet.Encode(encoder); err != nil {
		return err
	}

	_, err := c.conn.Write(buf)
	return err
}

// receive receives a packet
func (c *clientConnection) receive(compressManager *compress.CompressorManager) (*protocol.SekiroPacket, error) {
	packet, err := protocol.Decode(c.reader)
	if err != nil {
		return nil, err
	}

	if compressManager != nil {
		if err := compressManager.HandleDecompress(packet); err != nil {
			logger.Errorf("Decompression failed: %v", err)
		}
	}

	return packet, nil
}

// close closes the connection
func (c *clientConnection) close() {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.closed {
		return
	}

	c.closed = true
	c.conn.Close()
}

// bufWriter implements io.Writer
type bufWriter struct {
	buf *[]byte
}

func (w *bufWriter) Write(p []byte) (n int, err error) {
	*w.buf = append(*w.buf, p...)
	return len(p), nil
}

// RegisterHandler registers a handler for incoming invocations
type RegisterHandler func(request []byte) ([]byte, error)

// Register registers a handler for the client
func (c *SekiroClient) Register(handler RegisterHandler) {
	// Implementation for handling invocations
	_ = handler
}
