package detector

import (
	"bufio"
	"bytes"
	"context"
	"io"
	"net"
	"sync"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/compress"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

// RpcHandler handles Rpc protocol connections
type RpcHandler struct {
	conn            net.Conn
	compressManager *compress.CompressorManager
	reader          *bufio.Reader
	mu              sync.Mutex
	closed          bool
}

func newRpcHandler(conn net.Conn, compressManager *compress.CompressorManager, firstRead []byte) *RpcHandler {
	// Use MultiReader to combine already-read data with remaining connection data
	reader := bufio.NewReader(io.MultiReader(bytes.NewReader(firstRead), conn))
	return &RpcHandler{
		conn:            conn,
		compressManager: compressManager,
		reader:          reader,
	}
}

// Handle handles the connection
func (h *RpcHandler) Handle(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		packet, err := h.Receive()
		if err != nil {
			if err == io.EOF {
				logger.Debugf("Connection closed: %s", h.conn.RemoteAddr())
				return nil
			}
			logger.Errorf("Receive error: %v", err)
			return err
		}

		if err := h.handlePacket(packet); err != nil {
			logger.Errorf("Handle packet error: %v", err)
		}
	}
}

// Receive receives a packet
func (h *RpcHandler) Receive() (*protocol.RpcPacket, error) {
	packet, err := protocol.Decode(h.reader)
	if err != nil {
		return nil, err
	}

	// Decompress if needed
	if h.compressManager != nil {
		if err := h.compressManager.HandleDecompress(packet); err != nil {
			logger.Errorf("Decompression failed: %v", err)
		}
	}

	return packet, nil
}

// Send sends a packet
func (h *RpcHandler) Send(packet *protocol.RpcPacket) error {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.closed {
		return io.ErrClosedPipe
	}

	// Compress if needed
	if h.compressManager != nil {
		if err := h.compressManager.DoCompress(packet); err != nil {
			logger.Errorf("Compression failed: %v", err)
		}
	}

	// Encode and send
	var buf []byte
	encoder := &bufWriter{buf: &buf}
	if err := packet.Encode(encoder); err != nil {
		return err
	}

	_, err := h.conn.Write(buf)
	return err
}

// Close closes the connection
func (h *RpcHandler) Close() error {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.closed {
		return nil
	}

	h.closed = true
	return h.conn.Close()
}

// handlePacket handles a received packet
func (h *RpcHandler) handlePacket(packet *protocol.RpcPacket) error {
	logger.Debugf("Received packet: type=%s, serial=%d",
		protocol.RpcPacketType(packet.Type), packet.SerialNumber)

	switch protocol.RpcPacketType(packet.Type) {
	case protocol.PacketTypeHeartbeat:
		return h.handleHeartbeat(packet)
	case protocol.PacketTypeRegister:
		return h.handleRegister(packet)
	case protocol.PacketTypeInvokeResponse:
		return h.handleInvokeResponse(packet)
	case protocol.PacketTypeOffline:
		return h.handleOffline(packet)
	default:
		logger.Debugf("Unhandled packet type: %s", protocol.RpcPacketType(packet.Type))
	}

	return nil
}

// handleHeartbeat handles heartbeat packets
func (h *RpcHandler) handleHeartbeat(packet *protocol.RpcPacket) error {
	logger.Debug("Heartbeat received")
	// Echo heartbeat back
	return h.Send(packet)
}

// handleRegister handles client registration
func (h *RpcHandler) handleRegister(packet *protocol.RpcPacket) error {
	logger.Debug("Register packet received")
	// Registration handling will be implemented with client manager
	return nil
}

// handleInvokeResponse handles invoke response
func (h *RpcHandler) handleInvokeResponse(packet *protocol.RpcPacket) error {
	logger.Debug("Invoke response received")
	return nil
}

// handleOffline handles client offline
func (h *RpcHandler) handleOffline(packet *protocol.RpcPacket) error {
	logger.Debug("Client offline notification received")
	return nil
}

// bufWriter implements io.Writer for byte slice
type bufWriter struct {
	buf *[]byte
}

func (w *bufWriter) Write(p []byte) (n int, err error) {
	*w.buf = append(*w.buf, p...)
	return len(p), nil
}
