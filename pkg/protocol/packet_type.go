package protocol

// RpcPacketType defines the types of Rpc packets
type RpcPacketType byte

// Packet type constants
const (
	// Heartbeat packets
	PacketTypeHeartbeat RpcPacketType = 0

	// Client to Server packets
	PacketTypeRegister        RpcPacketType = 16
	PacketTypeInvokeResponse  RpcPacketType = 17
	PacketTypeOffline         RpcPacketType = 18
	PacketTypeCmdResponse     RpcPacketType = 19
	PacketTypeInvokeStreamClose RpcPacketType = 20

	// Server to Client packets
	PacketTypeSInvoke         RpcPacketType = 32
	PacketTypeSCmd            RpcPacketType = 33
	PacketTypeSOfflineResponse RpcPacketType = 34
	PacketTypeSInvokeResponse RpcPacketType = 35
	PacketTypeSInvokeConnected RpcPacketType = 36

	// Internal/Invoker packets
	PacketTypeIConnect        RpcPacketType = 48
	PacketTypeIInvoke         RpcPacketType = 49
)

// String returns the string representation of the packet type
func (t RpcPacketType) String() string {
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
func (t RpcPacketType) NewPacket() *RpcPacket {
	return NewRpcPacket().SetType(byte(t))
}
