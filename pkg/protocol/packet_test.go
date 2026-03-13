package protocol

import (
	"bytes"
	"testing"
)

func TestSekiroPacketEncodeDecode(t *testing.T) {
	tests := []struct {
		name     string
		packet   *SekiroPacket
		wantErr  bool
	}{
		{
			name: "simple packet",
			packet: &SekiroPacket{
				Type:         byte(PacketTypeHeartbeat),
				SerialNumber: 123,
				Headers:      map[string]string{"key1": "value1"},
				Data:         []byte("test data"),
			},
		},
		{
			name: "empty packet",
			packet: &SekiroPacket{
				Type:         byte(PacketTypeHeartbeat),
				SerialNumber: 0,
				Headers:      make(map[string]string),
				Data:         nil,
			},
		},
		{
			name: "multiple headers",
			packet: &SekiroPacket{
				Type:         byte(PacketTypeRegister),
				SerialNumber: 456,
				Headers: map[string]string{
					"group":    "test-group",
					"clientId": "client-123",
					"version":  "1.0",
				},
				Data: []byte("payload"),
			},
		},
		{
			name: "large data",
			packet: &SekiroPacket{
				Type:         byte(PacketTypeSInvoke),
				SerialNumber: 789,
				Headers:      map[string]string{"api": "test"},
				Data:         bytes.Repeat([]byte("x"), 10000),
			},
		},
		{
			name: "binary data",
			packet: &SekiroPacket{
				Type:         byte(PacketTypeIInvoke),
				SerialNumber: 999,
				Headers:      make(map[string]string),
				Data:         []byte{0x00, 0x01, 0x02, 0xFF, 0xFE, 0xFD},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Encode
			var buf bytes.Buffer
			err := tt.packet.Encode(&buf)
			if (err != nil) != tt.wantErr {
				t.Fatalf("Encode() error = %v, wantErr %v", err, tt.wantErr)
			}
			if err != nil {
				return
			}

			// Decode
			decoded, err := Decode(&buf)
			if err != nil {
				t.Fatalf("Decode() error = %v", err)
			}

			// Verify type
			if decoded.Type != tt.packet.Type {
				t.Errorf("Type mismatch: got %d, want %d", decoded.Type, tt.packet.Type)
			}

			// Verify serial number
			if decoded.SerialNumber != tt.packet.SerialNumber {
				t.Errorf("SerialNumber mismatch: got %d, want %d", decoded.SerialNumber, tt.packet.SerialNumber)
			}

			// Verify headers
			if len(decoded.Headers) != len(tt.packet.Headers) {
				t.Errorf("Headers count mismatch: got %d, want %d", len(decoded.Headers), len(tt.packet.Headers))
			}
			for k, v := range tt.packet.Headers {
				if decoded.Headers[k] != v {
					t.Errorf("Header[%s] mismatch: got %s, want %s", k, decoded.Headers[k], v)
				}
			}

			// Verify data
			if !bytes.Equal(decoded.Data, tt.packet.Data) {
				t.Errorf("Data mismatch: got %v, want %v", decoded.Data, tt.packet.Data)
			}
		})
	}
}

func TestDecodeInvalidMagic(t *testing.T) {
	// Create buffer with invalid magic number
	buf := bytes.NewReader([]byte{0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00})
	_, err := Decode(buf)
	if err == nil {
		t.Error("Decode() expected error for invalid magic number, got nil")
	}
}

func TestDecodeTruncatedData(t *testing.T) {
	// Create buffer with valid magic but truncated data
	buf := bytes.NewReader([]byte{0x73, 0x65, 0x6B, 0x69, 0x72, 0x6F, 0x00, 0x00})
	_, err := Decode(buf)
	if err == nil {
		t.Error("Decode() expected error for truncated data, got nil")
	}
}

func TestSekiroPacketTypeString(t *testing.T) {
	tests := []struct {
		packetType SekiroPacketType
		want       string
	}{
		{PacketTypeHeartbeat, "HEARTBEAT"},
		{PacketTypeRegister, "C_REGISTER"},
		{PacketTypeInvokeResponse, "C_INVOKE_RESPONSE"},
		{PacketTypeOffline, "C_OFFLINE"},
		{PacketTypeCmdResponse, "C_CMD_RESPONSE"},
		{PacketTypeInvokeStreamClose, "C_INVOKE_STREAM_CLOSE"},
		{PacketTypeSInvoke, "S_INVOKE"},
		{PacketTypeSCmd, "S_CMD"},
		{PacketTypeSOfflineResponse, "S_OFFLINE_RESPONSE"},
		{PacketTypeSInvokeResponse, "S_INVOKE_RESPONSE"},
		{PacketTypeSInvokeConnected, "S_INVOKE_CONNECTED"},
		{PacketTypeIConnect, "I_CONNECT"},
		{PacketTypeIInvoke, "I_INVOKE"},
		{SekiroPacketType(99), "UNKNOWN"},
	}

	for _, tt := range tests {
		t.Run(tt.want, func(t *testing.T) {
			if got := tt.packetType.String(); got != tt.want {
				t.Errorf("SekiroPacketType(%d).String() = %q, want %q", tt.packetType, got, tt.want)
			}
		})
	}
}

func TestNewPacket(t *testing.T) {
	packet := PacketTypeHeartbeat.NewPacket()
	if packet.Type != byte(PacketTypeHeartbeat) {
		t.Errorf("NewPacket() Type = %d, want %d", packet.Type, byte(PacketTypeHeartbeat))
	}
}

func TestPacketBuilder(t *testing.T) {
	packet := NewSekiroPacket().
		SetType(byte(PacketTypeRegister)).
		SetSerialNumber(100).
		AddHeader("group", "test").
		AddHeader("clientId", "client-1").
		SetData([]byte("test data"))

	if packet.Type != byte(PacketTypeRegister) {
		t.Errorf("SetType failed: got %d, want %d", packet.Type, byte(PacketTypeRegister))
	}
	if packet.SerialNumber != 100 {
		t.Errorf("SetSerialNumber failed: got %d, want %d", packet.SerialNumber, 100)
	}
	if packet.Headers["group"] != "test" {
		t.Errorf("AddHeader(group) failed: got %s", packet.Headers["group"])
	}
	if packet.Headers["clientId"] != "client-1" {
		t.Errorf("AddHeader(clientId) failed: got %s", packet.Headers["clientId"])
	}
	if !bytes.Equal(packet.Data, []byte("test data")) {
		t.Errorf("SetData failed: got %v", packet.Data)
	}
}

func TestGetHeader(t *testing.T) {
	packet := NewSekiroPacket()
	packet.AddHeader("key", "value")

	if got := packet.GetHeader("key"); got != "value" {
		t.Errorf("GetHeader() = %s, want value", got)
	}

	if got := packet.GetHeader("nonexistent"); got != "" {
		t.Errorf("GetHeader(nonexistent) = %s, want empty string", got)
	}

	// Test nil headers
	emptyPacket := &SekiroPacket{}
	if got := emptyPacket.GetHeader("key"); got != "" {
		t.Errorf("GetHeader() on nil headers = %s, want empty string", got)
	}
}

func TestEncodeWriteError(t *testing.T) {
	// Create a writer that always fails
	failWriter := &failWriter{}
	packet := NewSekiroPacket()
	err := packet.Encode(failWriter)
	if err == nil {
		t.Error("Encode() expected error from failing writer, got nil")
	}
}

// failWriter implements io.Writer that always returns an error
type failWriter struct{}

func (w *failWriter) Write(p []byte) (n int, err error) {
	return 0, bytes.ErrTooLarge
}
