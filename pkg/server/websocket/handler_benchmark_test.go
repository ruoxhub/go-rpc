package websocket

import (
	stdjson "encoding/json"
	"testing"

	json "github.com/goccy/go-json"
)

var benchmarkData = RpcMessage{
	Type:      MessageTypeInvokeResponse,
	Sequence:  "seq-benchmark-123456789",
	RpcSeq:    "seq-benchmark-123456789",
	Group:     "benchmark-group-name",
	ClientID:  "benchmark-client-id-uuid-v4",
	Timestamp: 1716382000000,
	Status:    200,
	Error:     "",
}

func BenchmarkStandardJSON_Marshal(b *testing.B) {
	for i := 0; i < b.N; i++ {
		_, err := stdjson.Marshal(&benchmarkData)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkGoJSON_Marshal(b *testing.B) {
	for i := 0; i < b.N; i++ {
		_, err := json.Marshal(&benchmarkData)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkStandardJSON_Unmarshal(b *testing.B) {
	data, _ := stdjson.Marshal(&benchmarkData)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var msg RpcMessage
		err := stdjson.Unmarshal(data, &msg)
		if err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkGoJSON_Unmarshal(b *testing.B) {
	data, _ := json.Marshal(&benchmarkData)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var msg RpcMessage
		err := json.Unmarshal(data, &msg)
		if err != nil {
			b.Fatal(err)
		}
	}
}
