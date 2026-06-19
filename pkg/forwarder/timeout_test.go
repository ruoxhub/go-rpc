package forwarder

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestInvokeRecord_IsExpired(t *testing.T) {
	record := &InvokeRecord{
		CreatedAt: time.Now(),
		Timeout:   100 * time.Millisecond,
	}

	// Should not be expired initially
	if record.IsExpired() {
		t.Error("Should not be expired initially")
	}

	// Wait for timeout
	time.Sleep(150 * time.Millisecond)

	// Should be expired now
	if !record.IsExpired() {
		t.Error("Should be expired after timeout")
	}
}

func TestInvokeRecord_IsTimedOut(t *testing.T) {
	record := &InvokeRecord{
		CreatedAt: time.Now(),
		Timeout:   1 * time.Second,
	}

	// Should not be timed out initially
	if record.IsTimedOut() {
		t.Error("Should not be timed out initially")
	}

	// Set timed out
	record.SetTimedOut()

	// Should be timed out
	if !record.IsTimedOut() {
		t.Error("Should be timed out after SetTimedOut")
	}
}

func TestInvokeRecord_Close(t *testing.T) {
	record := &InvokeRecord{
		CreatedAt:    time.Now(),
		Timeout:      1 * time.Second,
		ResponseChan: make(chan *InvokeResponse, 1),
	}

	// Close should not panic
	record.Close()

	// Channel should be closed
	select {
	case _, ok := <-record.ResponseChan:
		if ok {
			t.Error("Channel should be closed")
		}
	default:
		t.Error("Channel should be closed")
	}
}

func TestTimeoutManager_NewTimeoutManager(t *testing.T) {
	config := &TimeoutManagerConfig{
		DefaultTimeout:  30 * time.Second,
		CleanupInterval: 10 * time.Second,
	}

	manager := NewTimeoutManager(config)
	defer manager.Shutdown()

	if manager.defaultTimeout != 30*time.Second {
		t.Errorf("Expected default timeout 30s, got %v", manager.defaultTimeout)
	}
	if manager.cleanupInterval != 10*time.Second {
		t.Errorf("Expected cleanup interval 10s, got %v", manager.cleanupInterval)
	}
}

func TestTimeoutManager_DefaultConfig(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	if manager.defaultTimeout != 30*time.Second {
		t.Errorf("Expected default timeout 30s, got %v", manager.defaultTimeout)
	}
}

func TestTimeoutManager_AddAndGet(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	record := manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	if record == nil {
		t.Fatal("Expected record")
	}
	if record.ID != "test-id" {
		t.Errorf("Expected ID 'test-id', got '%s'", record.ID)
	}
	if record.Group != "test-group" {
		t.Errorf("Expected group 'test-group', got '%s'", record.Group)
	}
	if record.ClientID != "client-1" {
		t.Errorf("Expected clientID 'client-1', got '%s'", record.ClientID)
	}
	if string(record.Data) != "test data" {
		t.Errorf("Expected data 'test data', got '%s'", string(record.Data))
	}

	// Get should return same record
	got := manager.Get("test-id")
	if got != record {
		t.Error("Expected same record")
	}
}

func TestTimeoutManager_Remove(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	// Verify added
	if manager.Count() != 1 {
		t.Errorf("Expected 1 record, got %d", manager.Count())
	}

	// Remove
	manager.Remove("test-id")

	// Verify removed
	if manager.Count() != 0 {
		t.Errorf("Expected 0 records after remove, got %d", manager.Count())
	}

	// Get should return nil
	got := manager.Get("test-id")
	if got != nil {
		t.Error("Expected nil after remove")
	}
}

func TestTimeoutManager_Complete(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	record := manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	// Complete with response
	response := &InvokeResponse{
		Data:   []byte("response data"),
		Status: 200,
	}

	success := manager.Complete("test-id", response)
	if !success {
		t.Error("Expected successful completion")
	}

	// Response should be available in channel
	select {
	case resp := <-record.ResponseChan:
		if string(resp.Data) != "response data" {
			t.Errorf("Expected response data 'response data', got '%s'", string(resp.Data))
		}
		if resp.Status != 200 {
			t.Errorf("Expected status 200, got %d", resp.Status)
		}
	case <-time.After(100 * time.Millisecond):
		t.Error("Timeout waiting for response")
	}
}

func TestTimeoutManager_Complete_NonExistent(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	// Complete non-existent record should return false
	success := manager.Complete("non-existent", &InvokeResponse{})
	if success {
		t.Error("Expected false for non-existent record")
	}
}

func TestTimeoutManager_Wait(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	// Complete in goroutine
	go func() {
		time.Sleep(10 * time.Millisecond)
		manager.Complete("test-id", &InvokeResponse{
			Data:   []byte("response"),
			Status: 200,
		})
	}()

	// Wait for response
	response, err := manager.Wait("test-id")
	if err != nil {
		t.Fatalf("Expected no error, got %v", err)
	}
	if response == nil {
		t.Fatal("Expected response")
	}
	if string(response.Data) != "response" {
		t.Errorf("Expected response 'response', got '%s'", string(response.Data))
	}
}

func TestTimeoutManager_Wait_Timeout(t *testing.T) {
	config := &TimeoutManagerConfig{
		DefaultTimeout:  50 * time.Millisecond,
		CleanupInterval: 10 * time.Second,
	}
	manager := NewTimeoutManager(config)
	defer manager.Shutdown()

	manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	// Wait should timeout
	response, err := manager.Wait("test-id")
	if err != ErrTimeout {
		t.Errorf("Expected ErrTimeout, got %v", err)
	}
	if response != nil {
		t.Error("Expected nil response on timeout")
	}
}

func TestTimeoutManager_Wait_NotFound(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	// Wait for non-existent record
	response, err := manager.Wait("non-existent")
	if err != ErrRecordNotFound {
		t.Errorf("Expected ErrRecordNotFound, got %v", err)
	}
	if response != nil {
		t.Error("Expected nil response for not found")
	}
}

func TestTimeoutManager_CleanupExpired(t *testing.T) {
	config := &TimeoutManagerConfig{
		DefaultTimeout:  50 * time.Millisecond,
		CleanupInterval: 100 * time.Millisecond,
	}
	manager := NewTimeoutManager(config)
	defer manager.Shutdown()

	// Add record
	manager.Add("test-id", "test-group", "client-1", []byte("test data"))

	// Wait for cleanup
	time.Sleep(150 * time.Millisecond)

	// Record should be cleaned up
	got := manager.Get("test-id")
	if got != nil {
		t.Error("Expected record to be cleaned up")
	}
}

func TestTimeoutManager_Shutdown(t *testing.T) {
	config := &TimeoutManagerConfig{
		DefaultTimeout:  1 * time.Second,
		CleanupInterval: 10 * time.Millisecond,
	}
	manager := NewTimeoutManager(config)

	// Add records
	manager.Add("test-id-1", "test-group", "client-1", []byte("test data 1"))
	manager.Add("test-id-2", "test-group", "client-2", []byte("test data 2"))

	// Shutdown
	manager.Shutdown()

	// Wait should not block after shutdown
	_, err := manager.Wait("test-id-1")
	if err == nil {
		t.Error("Expected error after shutdown")
	}
}

func TestTimeoutManager_Count(t *testing.T) {
	manager := NewTimeoutManager(nil)
	defer manager.Shutdown()

	if manager.Count() != 0 {
		t.Errorf("Expected 0 records, got %d", manager.Count())
	}

	manager.Add("id1", "group", "c1", nil)
	manager.Add("id2", "group", "c2", nil)
	manager.Add("id3", "group", "c3", nil)

	if manager.Count() != 3 {
		t.Errorf("Expected 3 records, got %d", manager.Count())
	}
}

func TestTimeoutManager_ShutdownConcurrent(t *testing.T) {
	m := NewTimeoutManager(nil)
	m.Add("1", "g", "c", []byte("data"))
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			m.Shutdown()
		}()
	}
	wg.Wait()
	assert.Equal(t, 0, m.Count())
}

func TestTimeoutManager_ShutdownIdempotent(t *testing.T) {
	m := NewTimeoutManager(nil)
	m.Shutdown()
	m.Shutdown()
	m.Shutdown()
}
