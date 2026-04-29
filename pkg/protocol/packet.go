// Package protocol implements the Rpc communication protocol
package protocol

import (
	"encoding/binary"
	"errors"
	"io"
)

// Magic number for Rpc protocol
// Java: 8315170387645116465L = 0x73656b69726f0000 ("sekiro\0\0" in big-endian)
const Magic = int64(8315170387645116465)

// Protocol constants
const (
	MagicSize         = 8  // int64
	ContentLengthSize = 4  // int32
	TypeSize          = 1  // byte
	SerialNumberSize  = 4  // int32
	KeyLenSize        = 1  // byte
	ValueLenSize      = 1  // byte
	MaxHeaderKeyLen   = 255
	MaxHeaderValueLen = 255
)

// RpcPacket represents a Rpc protocol packet
type RpcPacket struct {
	Type         byte
	SerialNumber int32
	Headers      map[string]string
	Data         []byte
}

// NewRpcPacket creates a new RpcPacket
func NewRpcPacket() *RpcPacket {
	return &RpcPacket{
		Headers: make(map[string]string),
	}
}

// Encode encodes the packet to binary format
// Format: [Magic:int64][Length:int32][Type:byte][SerialNumber:int32][Headers][Data]
func (p *RpcPacket) Encode(w io.Writer) error {
	// Calculate body length
	bodyLen := p.calculateBodyLength()

	// Write magic number (big-endian)
	if err := binary.Write(w, binary.BigEndian, Magic); err != nil {
		return err
	}

	// Write body length (big-endian)
	if err := binary.Write(w, binary.BigEndian, int32(bodyLen)); err != nil {
		return err
	}

	// Write type
	if err := binary.Write(w, binary.BigEndian, p.Type); err != nil {
		return err
	}

	// Write serial number (big-endian)
	if err := binary.Write(w, binary.BigEndian, p.SerialNumber); err != nil {
		return err
	}

	// Write headers count
	if err := binary.Write(w, binary.BigEndian, byte(len(p.Headers))); err != nil {
		return err
	}

	// Write headers
	for key, value := range p.Headers {
		if len(key) > MaxHeaderKeyLen {
			key = key[:MaxHeaderKeyLen]
		}
		if len(value) > MaxHeaderValueLen {
			value = value[:MaxHeaderValueLen]
		}
		if err := binary.Write(w, binary.BigEndian, byte(len(key))); err != nil {
			return err
		}
		if _, err := w.Write([]byte(key)); err != nil {
			return err
		}
		if err := binary.Write(w, binary.BigEndian, byte(len(value))); err != nil {
			return err
		}
		if _, err := w.Write([]byte(value)); err != nil {
			return err
		}
	}

	// Write data
	if p.Data != nil {
		if _, err := w.Write(p.Data); err != nil {
			return err
		}
	}

	return nil
}

// calculateBodyLength calculates the length of packet body (excluding magic and length field)
func (p *RpcPacket) calculateBodyLength() int {
	length := TypeSize + SerialNumberSize // type + serial number

	// headers: count(1) + for each: keyLen(1) + key + valueLen(1) + value
	length += 1 // header count
	for key, value := range p.Headers {
		length += 1 + len(key) + 1 + len(value)
	}

	// data length
	if p.Data != nil {
		length += len(p.Data)
	}

	return length
}

// Decode reads a packet from binary data
func Decode(r io.Reader) (*RpcPacket, error) {
	packet := NewRpcPacket()

	// Read and verify magic number
	var magic int64
	if err := binary.Read(r, binary.BigEndian, &magic); err != nil {
		return nil, err
	}
	if magic != Magic {
		return nil, errors.New("invalid magic number")
	}

	// Read body length
	var bodyLen int32
	if err := binary.Read(r, binary.BigEndian, &bodyLen); err != nil {
		return nil, err
	}

	// Read type
	if err := binary.Read(r, binary.BigEndian, &packet.Type); err != nil {
		return nil, err
	}

	// Read serial number
	if err := binary.Read(r, binary.BigEndian, &packet.SerialNumber); err != nil {
		return nil, err
	}

	// Read header count
	var headerCount byte
	if err := binary.Read(r, binary.BigEndian, &headerCount); err != nil {
		return nil, err
	}

	// Read headers
	for i := 0; i < int(headerCount); i++ {
		var keyLen byte
		if err := binary.Read(r, binary.BigEndian, &keyLen); err != nil {
			return nil, err
		}
		key := make([]byte, keyLen)
		if _, err := io.ReadFull(r, key); err != nil {
			return nil, err
		}

		var valueLen byte
		if err := binary.Read(r, binary.BigEndian, &valueLen); err != nil {
			return nil, err
		}
		value := make([]byte, valueLen)
		if _, err := io.ReadFull(r, value); err != nil {
			return nil, err
		}

		packet.Headers[string(key)] = string(value)
	}

	// Read data (remaining bytes in body)
	// bodyLen includes: type(1) + serial(4) + headers + data
	// we've already read: type(1) + serial(4) + headers
	dataLen := int(bodyLen) - TypeSize - SerialNumberSize - 1 // -1 for header count
	for k, v := range packet.Headers {
		dataLen -= 1 + len(k) + 1 + len(v)
	}

	if dataLen > 0 {
		packet.Data = make([]byte, dataLen)
		if _, err := io.ReadFull(r, packet.Data); err != nil {
			return nil, err
		}
	} else if dataLen < 0 {
		return nil, errors.New("invalid packet: negative data length")
	}

	return packet, nil
}

// AddHeader adds a header to the packet
func (p *RpcPacket) AddHeader(key, value string) *RpcPacket {
	p.Headers[key] = value
	return p
}

// GetHeader gets a header value
func (p *RpcPacket) GetHeader(key string) string {
	if p.Headers == nil {
		return ""
	}
	return p.Headers[key]
}

// SetData sets the packet data
func (p *RpcPacket) SetData(data []byte) *RpcPacket {
	p.Data = data
	return p
}

// SetType sets the packet type
func (p *RpcPacket) SetType(t byte) *RpcPacket {
	p.Type = t
	return p
}

// SetSerialNumber sets the packet serial number
func (p *RpcPacket) SetSerialNumber(sn int32) *RpcPacket {
	p.SerialNumber = sn
	return p
}
