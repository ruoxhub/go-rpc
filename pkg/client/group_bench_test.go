package client

import (
	"fmt"
	"testing"
)

func BenchmarkRpcGroup_AllocateClient(b *testing.B) {
	group := NewRpcGroup("bench-group")
	defer group.Close()

	for i := 0; i < 20; i++ {
		c := NewRpcClient("bench-group", fmt.Sprintf("client-%d", i), nil)
		c.SetStatus(StatusOnline)
		group.Register(c)
	}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = group.AllocateClient()
	}
}
