package flow

import (
	"testing"
	"time"
)

func TestDefaultBackoffConfig(t *testing.T) {
	config := DefaultBackoffConfig()

	if config.InitialDelay != 1*time.Second {
		t.Errorf("Expected InitialDelay 1s, got %v", config.InitialDelay)
	}
	if config.MaxDelay != 20*time.Second {
		t.Errorf("Expected MaxDelay 20s, got %v", config.MaxDelay)
	}
	if config.Multiplier != 2.0 {
		t.Errorf("Expected Multiplier 2.0, got %v", config.Multiplier)
	}
	if config.ResetTimeout != 30*time.Second {
		t.Errorf("Expected ResetTimeout 30s, got %v", config.ResetTimeout)
	}
}

func TestNewDelayBackoff(t *testing.T) {
	// Test with default config
	backoff := NewDelayBackoff(nil)
	if backoff.config == nil {
		t.Error("Expected default config")
	}

	// Test with custom config
	customConfig := &BackoffConfig{
		InitialDelay: 500 * time.Millisecond,
		MaxDelay:     5 * time.Second,
		Multiplier:   1.5,
		ResetTimeout: 10 * time.Second,
	}
	backoff2 := NewDelayBackoff(customConfig)
	if backoff2.config != customConfig {
		t.Error("Expected custom config")
	}
}

func TestDelayBackoff_GetDelay(t *testing.T) {
	backoff := NewDelayBackoff(nil)

	// New group should have initial delay
	delay := backoff.GetDelay("test-group")
	if delay != backoff.config.InitialDelay {
		t.Errorf("Expected initial delay %v, got %v", backoff.config.InitialDelay, delay)
	}
}

func TestDelayBackoff_RecordEmpty(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Initial delay should be 1s
	delay := backoff.GetDelay("test-group")
	if delay != 1*time.Second {
		t.Errorf("Expected initial delay 1s, got %v", delay)
	}

	// Record empty - delay should double
	backoff.RecordEmpty("test-group")
	delay = backoff.GetDelay("test-group")
	if delay != 2*time.Second {
		t.Errorf("Expected delay 2s after first empty, got %v", delay)
	}

	// Record empty again - delay should double again
	backoff.RecordEmpty("test-group")
	delay = backoff.GetDelay("test-group")
	if delay != 4*time.Second {
		t.Errorf("Expected delay 4s after second empty, got %v", delay)
	}
}

func TestDelayBackoff_RecordEmpty_MaxDelay(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     5 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Record empty multiple times
	for i := 0; i < 10; i++ {
		backoff.RecordEmpty("test-group")
	}

	delay := backoff.GetDelay("test-group")
	if delay != config.MaxDelay {
		t.Errorf("Expected delay capped at MaxDelay %v, got %v", config.MaxDelay, delay)
	}
}

func TestDelayBackoff_RecordSuccess(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Increase delay
	backoff.RecordEmpty("test-group")
	backoff.RecordEmpty("test-group")

	delay := backoff.GetDelay("test-group")
	if delay != 4*time.Second {
		t.Errorf("Expected delay 4s, got %v", delay)
	}

	// Record success - should reset to initial delay
	backoff.RecordSuccess("test-group")
	delay = backoff.GetDelay("test-group")
	if delay != 1*time.Second {
		t.Errorf("Expected delay reset to 1s after success, got %v", delay)
	}
}

func TestDelayBackoff_Reset(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Increase delay
	backoff.RecordEmpty("test-group")
	backoff.RecordEmpty("test-group")

	delay := backoff.GetDelay("test-group")
	if delay != 4*time.Second {
		t.Errorf("Expected delay 4s, got %v", delay)
	}

	// Reset
	backoff.Reset("test-group")
	delay = backoff.GetDelay("test-group")
	if delay != 1*time.Second {
		t.Errorf("Expected delay reset to 1s, got %v", delay)
	}
}

func TestDelayBackoff_Remove(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Create state
	backoff.RecordEmpty("test-group")

	// Remove state
	backoff.Remove("test-group")

	// GetDelay should create new state with initial delay
	delay := backoff.GetDelay("test-group")
	if delay != 1*time.Second {
		t.Errorf("Expected initial delay after remove, got %v", delay)
	}
}

func TestDelayBackoff_Cleanup(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 30 * time.Second,
	}
	backoff := NewDelayBackoff(config)

	// Create multiple states
	backoff.RecordEmpty("group-1")
	backoff.RecordEmpty("group-2")
	backoff.RecordEmpty("group-3")

	// Cleanup
	backoff.Cleanup()

	// All states should be reset
	delay1 := backoff.GetDelay("group-1")
	delay2 := backoff.GetDelay("group-2")
	delay3 := backoff.GetDelay("group-3")

	if delay1 != 1*time.Second {
		t.Errorf("Expected group-1 initial delay, got %v", delay1)
	}
	if delay2 != 1*time.Second {
		t.Errorf("Expected group-2 initial delay, got %v", delay2)
	}
	if delay3 != 1*time.Second {
		t.Errorf("Expected group-3 initial delay, got %v", delay3)
	}
}

func TestDelayBackoff_ResetTimeout(t *testing.T) {
	config := &BackoffConfig{
		InitialDelay: 1 * time.Second,
		MaxDelay:     10 * time.Second,
		Multiplier:   2.0,
		ResetTimeout: 100 * time.Millisecond, // Short timeout for testing
	}
	backoff := NewDelayBackoff(config)

	// Increase delay
	backoff.RecordEmpty("test-group")
	backoff.RecordEmpty("test-group")

	delay := backoff.GetDelay("test-group")
	if delay != 4*time.Second {
		t.Errorf("Expected delay 4s, got %v", delay)
	}

	// Wait for reset timeout
	time.Sleep(150 * time.Millisecond)

	// Delay should be reset to initial
	delay = backoff.GetDelay("test-group")
	if delay != 1*time.Second {
		t.Errorf("Expected delay reset after timeout, got %v", delay)
	}
}
