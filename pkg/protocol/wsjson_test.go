package protocol

import (
	"encoding/json"
	"errors"
	"slices"
	"strings"
	"testing"
)

func TestNegotiateRegistration(t *testing.T) {
	enabled := []string{CapabilityInvocationContextV1}
	tests := []struct {
		name, version, capabilities string
		wantLegacy                  bool
		wantCaps                    []string
		wantErr                     error
	}{
		{name: "legacy", wantLegacy: true},
		{name: "supported", version: "1", capabilities: "unknown.v1,invocation_context.v1,invocation_context.v1", wantCaps: []string{CapabilityInvocationContextV1}},
		{name: "unsupported version", version: "2", wantErr: ErrUnsupportedProtocolVersion},
		{name: "invalid uppercase", version: "1", capabilities: "Cancel.v1", wantErr: ErrInvalidCapabilities},
		{name: "invalid empty item", version: "1", capabilities: "a.v1,,b.v1", wantErr: ErrInvalidCapabilities},
		{name: "too many raw items", version: "1", capabilities: "a,a,a,a,a,a,a,a,a,a,a,a,a,a,a,a,a", wantErr: ErrInvalidCapabilities},
		{name: "item too long", version: "1", capabilities: strings.Repeat("a", 33), wantErr: ErrInvalidCapabilities},
		{name: "non ascii", version: "1", capabilities: "能力.v1", wantErr: ErrInvalidCapabilities},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := NegotiateRegistration(tt.version, tt.capabilities, enabled)
			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("error = %v, want %v", err, tt.wantErr)
			}
			if got.Legacy != tt.wantLegacy || !slices.Equal(got.Capabilities, tt.wantCaps) {
				t.Fatalf("registration = %#v", got)
			}
		})
	}
}

func TestWSMessageJSON(t *testing.T) {
	message := WSMessage{
		Type:     MessageTypeInvoke,
		Sequence: "sequence-1",
		RpcSeq:   "rpc-sequence-1",
		Group:    "group-a",
		ClientID: "client-a",
		Actions:  []string{"action-a"},
		Data:     json.RawMessage(`{"value":true}`),
		TraceID:  "trace-1",
		RPCContext: &WireInvocationContext{
			Sequence:       "sequence-1",
			TraceID:        "trace-1",
			Group:          "group-a",
			Action:         "action-a",
			ClientID:       "client-a",
			DeadlineUnixMS: 123,
			Idempotent:     true,
			IdempotencyKey: "key-1",
			Attempt:        1,
		},
	}

	data, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("marshal message: %v", err)
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		t.Fatalf("unmarshal message: %v", err)
	}
	for _, field := range []string{"type", "__sekiro_seq__", "trace_id", "__rpc_context__"} {
		if _, ok := fields[field]; !ok {
			t.Errorf("missing field %q in %s", field, data)
		}
	}
	var decoded WSMessage
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal typed message: %v", err)
	}
	if decoded.RPCContext == nil || decoded.RPCContext.Action != "action-a" {
		t.Fatalf("decoded RPC context = %#v", decoded.RPCContext)
	}

	if got := message.GetSequence(); got != "rpc-sequence-1" {
		t.Fatalf("GetSequence() = %q", got)
	}
	message.RpcSeq = ""
	if got := message.GetSequence(); got != "sequence-1" {
		t.Fatalf("GetSequence() fallback = %q", got)
	}
}
