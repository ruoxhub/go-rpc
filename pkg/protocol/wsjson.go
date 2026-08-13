package protocol

import (
	"encoding/json"
	"errors"
	"strconv"
	"strings"
)

const (
	CurrentProtocolVersion        = 1
	CapabilityInvocationContextV1 = "invocation_context.v1"
	MessageTypeRegistered         = WSMessageType("registered")
	MessageTypeHeartbeat          = WSMessageType("heartbeat")
	MessageTypeInvoke             = WSMessageType("invoke")
	MessageTypeInvokeResponse     = WSMessageType("invoke_response")
	MessageTypeInvokeStream       = WSMessageType("invoke_stream")
	MessageTypeBind               = WSMessageType("bind")
)

var (
	ErrUnsupportedProtocolVersion = errors.New("unsupported protocol version")
	ErrInvalidCapabilities        = errors.New("invalid capabilities")
)

type Registration struct {
	Legacy          bool
	ProtocolVersion int
	Capabilities    []string
}

type WSMessageType string

func LegacyRegistration() Registration {
	return Registration{Legacy: true, ProtocolVersion: CurrentProtocolVersion}
}

func (r Registration) Supports(capability string) bool {
	for _, current := range r.Capabilities {
		if current == capability {
			return true
		}
	}
	return false
}

type WireInvocationContext struct {
	Sequence       string `json:"sequence"`
	TraceID        string `json:"trace_id"`
	Group          string `json:"group"`
	Action         string `json:"action"`
	ClientID       string `json:"client_id"`
	DeadlineUnixMS int64  `json:"deadline_unix_ms"`
	Idempotent     bool   `json:"idempotent"`
	IdempotencyKey string `json:"idempotency_key"`
	Attempt        int    `json:"attempt"`
}

type WSMessage struct {
	Type            WSMessageType          `json:"type"`
	Sequence        string                 `json:"sequence,omitempty"`
	RpcSeq          string                 `json:"__sekiro_seq__,omitempty"`
	Group           string                 `json:"group,omitempty"`
	ClientID        string                 `json:"clientId,omitempty"`
	Actions         []string               `json:"actions,omitempty"`
	Data            json.RawMessage        `json:"data,omitempty"`
	Error           string                 `json:"error,omitempty"`
	Status          int                    `json:"status,omitempty"`
	Done            bool                   `json:"done,omitempty"`
	Timestamp       int64                  `json:"timestamp,omitempty"`
	TraceID         string                 `json:"trace_id,omitempty"`
	ProtocolVersion int                    `json:"protocol_version,omitempty"`
	Capabilities    []string               `json:"capabilities,omitempty"`
	RPCContext      *WireInvocationContext `json:"__rpc_context__,omitempty"`
}

func (m WSMessage) GetSequence() string {
	if m.RpcSeq != "" {
		return m.RpcSeq
	}
	return m.Sequence
}

func NegotiateRegistration(versionRaw, capabilitiesRaw string, enabled []string) (Registration, error) {
	if versionRaw == "" {
		return LegacyRegistration(), nil
	}
	if versionRaw != strconv.Itoa(CurrentProtocolVersion) {
		return Registration{}, ErrUnsupportedProtocolVersion
	}
	declared, err := parseCapabilities(capabilitiesRaw)
	if err != nil {
		return Registration{}, err
	}
	declaredSet := make(map[string]struct{}, len(declared))
	for _, capability := range declared {
		declaredSet[capability] = struct{}{}
	}
	intersection := make([]string, 0, len(enabled))
	for _, capability := range enabled {
		if _, ok := declaredSet[capability]; ok {
			intersection = append(intersection, capability)
		}
	}
	return Registration{ProtocolVersion: CurrentProtocolVersion, Capabilities: intersection}, nil
}

func parseCapabilities(raw string) ([]string, error) {
	if raw == "" {
		return nil, nil
	}
	items := strings.Split(raw, ",")
	if len(items) > 16 {
		return nil, ErrInvalidCapabilities
	}

	seen := make(map[string]struct{}, len(items))
	capabilities := make([]string, 0, len(items))
	for _, item := range items {
		if item == "" || len(item) > 32 {
			return nil, ErrInvalidCapabilities
		}
		for i := 0; i < len(item); i++ {
			char := item[i]
			if !((char >= 'a' && char <= 'z') || (char >= '0' && char <= '9') || char == '.' || char == '_' || char == '-') {
				return nil, ErrInvalidCapabilities
			}
		}
		if _, ok := seen[item]; ok {
			continue
		}
		seen[item] = struct{}{}
		capabilities = append(capabilities, item)
	}
	return capabilities, nil
}
