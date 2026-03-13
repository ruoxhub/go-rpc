package protocol

// SekiroPacketType defines the types of Sekiro packets
type SekiroPacketType byte

// Packet type constants
const (
	// Heartbeat packets
	PacketTypeHeartbeat SekiroPacketType = 0

	// Client to Server packets
	PacketTypeRegister        SekiroPacketType = 16
	PacketTypeInvokeResponse  SekiroPacketType = 17
	PacketTypeOffline         SekiroPacketType = 18
	PacketTypeCmdResponse     SekiroPacketType = 19
	PacketTypeInvokeStreamClose SekiroPacketType = 20

	// Server to Client packets
	PacketTypeSInvoke         SekiroPacketType = 32
	PacketTypeSCmd            SekiroPacketType = 33
	PacketTypeSOfflineResponse SekiroPacketType = 34
	PacketTypeSInvokeResponse SekiroPacketType = 35
	PacketTypeSInvokeConnected SekiroPacketType = 36

	// Internal/Invoker packets
	PacketTypeIConnect        SekiroPacketType = 48
	PacketTypeIInvoke         SekiroPacketType = 49
)

// String returns the string representation of the packet type
func (t SekiroPacketType) String() string {
	switch t {
	case PacketTypeHeartbeat:
		return "HEARTBEAT"
	case PacketTypeRegister:
		return "C_REGISTER"
	case PacketTypeInvokeResponse:
		return "C_INVOKE_RESPONSE"
	case PacketTypeOffline:
		return "C_OFFLINE"
	case PacketTypeCmdResponse:
		return "C_CMD_RESPONSE"
	case PacketTypeInvokeStreamClose:
		return "C_INVOKE_STREAM_CLOSE"
	case PacketTypeSInvoke:
		return "S_INVOKE"
	case PacketTypeSCmd:
		return "S_CMD"
	case PacketTypeSOfflineResponse:
		return "S_OFFLINE_RESPONSE"
	case PacketTypeSInvokeResponse:
		return "S_INVOKE_RESPONSE"
	case PacketTypeSInvokeConnected:
		return "S_INVOKE_CONNECTED"
	case PacketTypeIConnect:
		return "I_CONNECT"
	case PacketTypeIInvoke:
		return "I_INVOKE"
	default:
		return "UNKNOWN"
	}
}

// NewPacket creates a new packet with the given type
func (t SekiroPacketType) NewPacket() *SekiroPacket {
	return NewSekiroPacket().SetType(byte(t))
}
