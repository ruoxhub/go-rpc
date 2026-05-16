package detector

import (
	"bytes"
	"context"
	"io"
	"net"

	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/compress"
	"github.com/mrh30000/go-rpc/pkg/protocol"
	"github.com/mrh30000/go-rpc/pkg/server/transport"
)

// RpcHandler handles Rpc protocol connections
type RpcHandler struct {
	tcpConn         *transport.TCPConnection
	compressManager *compress.CompressorManager
}

func newRpcHandler(conn net.Conn, compressManager *compress.CompressorManager, firstRead []byte) *RpcHandler {
	return &RpcHandler{
		tcpConn:         transport.NewTCPConnectionWithData(conn, firstRead),
		compressManager: compressManager,
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
				logger.Debugf("Connection closed: %s", h.tcpConn.RemoteAddr())
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
	raw, err := h.tcpConn.Receive()
	if err != nil {
		return nil, err
	}

	packet, err := protocol.Decode(bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}

	if h.compressManager != nil {
		if err := h.compressManager.HandleDecompress(packet); err != nil {
			logger.Errorf("Decompression failed: %v", err)
		}
	}

	return packet, nil
}

// Send sends a packet
func (h *RpcHandler) Send(packet *protocol.RpcPacket) error {
	if h.compressManager != nil {
		if err := h.compressManager.DoCompress(packet); err != nil {
			logger.Errorf("Compression failed: %v", err)
		}
	}

	var buf []byte
	encoder := &protocol.BufWriter{Buf: &buf}
	if err := packet.Encode(encoder); err != nil {
		return err
	}

	return h.tcpConn.Send(buf)
}

// Close closes the connection
func (h *RpcHandler) Close() error {
	return h.tcpConn.Close()
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
	return h.Send(packet)
}

// handleRegister handles client registration
func (h *RpcHandler) handleRegister(packet *protocol.RpcPacket) error {
	logger.Debug("Register packet received")
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
