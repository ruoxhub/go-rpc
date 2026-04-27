package forwarder

import (
	"testing"
	"time"
)

func TestStreamRegisterPushComplete(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	record := manager.RegisterStream("seq-1", "g1", "c1", time.Second)
	if record == nil {
		t.Fatal("expected stream record")
	}
	if manager.StreamCount() != 1 {
		t.Fatalf("stream count = %d, want 1", manager.StreamCount())
	}
	if !manager.PushStreamChunk("seq-1", &StreamChunk{Data: []byte(`{"delta":"a"}`)}) {
		t.Fatal("expected push to succeed")
	}

	chunk := <-record.ChunkChan
	if string(chunk.Data) != `{"delta":"a"}` {
		t.Fatalf("chunk data = %s", chunk.Data)
	}

	if !manager.CompleteStream("seq-1") {
		t.Fatal("expected complete to succeed")
	}
	if manager.StreamCount() != 0 {
		t.Fatalf("stream count = %d, want 0", manager.StreamCount())
	}
}

func TestStreamCleanupExpired(t *testing.T) {
	manager := NewTimeoutManager(&TimeoutManagerConfig{
		DefaultTimeout:  time.Millisecond,
		CleanupInterval: time.Millisecond,
	})
	defer manager.Shutdown()

	manager.RegisterStream("seq-1", "g1", "c1", time.Millisecond)
	time.Sleep(10 * time.Millisecond)
	manager.cleanupExpired()

	if manager.StreamCount() != 0 {
		t.Fatalf("stream count = %d, want 0", manager.StreamCount())
	}
}

func TestStreamDoesNotAffectWaitComplete(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	manager.RegisterStream("stream-1", "g1", "c1", time.Second)
	record := manager.Add("invoke-1", "g1", "c1", nil)
	if record == nil {
		t.Fatal("expected invoke record")
	}
	if !manager.Complete("invoke-1", &InvokeResponse{Data: []byte(`{}`), Status: 0}) {
		t.Fatal("expected invoke completion")
	}
	if manager.StreamCount() != 1 {
		t.Fatalf("stream count = %d, want 1", manager.StreamCount())
	}
}

func TestStreamBackpressureClosesWithTerminalError(t *testing.T) {
	oldTimeout := streamPushTimeout
	streamPushTimeout = time.Millisecond
	defer func() {
		streamPushTimeout = oldTimeout
	}()

	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	record := manager.RegisterStream("seq-1", "g1", "c1", time.Second)
	for i := 0; i < cap(record.ChunkChan); i++ {
		if !manager.PushStreamChunk("seq-1", &StreamChunk{Data: []byte(`{}`)}) {
			t.Fatalf("push %d failed before buffer was full", i)
		}
	}

	if manager.PushStreamChunk("seq-1", &StreamChunk{Done: true}) {
		t.Fatal("expected push to fail when stream is backpressured")
	}
	if manager.StreamCount() != 0 {
		t.Fatalf("stream count = %d, want 0", manager.StreamCount())
	}
	if record.TerminalError() == "" {
		t.Fatal("expected terminal error after backpressure")
	}
}
