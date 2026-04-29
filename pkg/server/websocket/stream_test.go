package websocket

import (
	"context"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

func TestHandleInvokeStreamRoutesChunkAndFinal(t *testing.T) {
	manager := client.NewClientManager()
	timeoutMgr := forwarder.NewTimeoutManager(nil)
	handler := NewHandler(manager, timeoutMgr, nil)
	defer handler.Shutdown()

	stream := timeoutMgr.RegisterStream("seq-1", "g1", "c1", time.Second)
	handler.processMessage(context.Background(), nil, []byte(`{"type":"invoke_stream","__sekiro_seq__":"seq-1","data":{"delta":"hello"},"done":false}`))

	chunk := <-stream.ChunkChan
	if string(chunk.Data) != `{"delta":"hello"}` {
		t.Fatalf("chunk = %s", chunk.Data)
	}

	handler.processMessage(context.Background(), nil, []byte(`{"type":"invoke_stream","__sekiro_seq__":"seq-1","done":true}`))
	final := <-stream.ChunkChan
	if !final.Done {
		t.Fatal("expected final chunk")
	}
	if timeoutMgr.StreamCount() != 0 {
		t.Fatalf("stream count = %d, want 0", timeoutMgr.StreamCount())
	}
}
