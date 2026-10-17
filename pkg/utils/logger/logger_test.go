package logger

import (
	"os"
	"path/filepath"
	"testing"
)

func TestInitLogger_FileOutput(t *testing.T) {
	tmpDir := filepath.Join(os.TempDir(), "sekiro-logger-test")
	defer os.RemoveAll(tmpDir)

	opts := &FileOptions{
		Enabled:    true,
		Dir:        tmpDir,
		Filename:   "test.log",
		MaxSize:    1,
		MaxBackups: 1,
		MaxAge:     1,
		Compress:   false,
	}

	InitLogger(false, opts)

	Info("file output test message")
	Sync()

	logPath := filepath.Join(tmpDir, "test.log")
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("expected log file to be created: %v", err)
	}
	if len(data) == 0 {
		t.Fatal("expected log file to contain data")
	}
	if op := string(data); !contains(op, "file output test message") {
		t.Fatalf("expected log file to contain test message, got: %s", op)
	}
}

func TestInitLogger_NilFileOptions(t *testing.T) {
	// Should not panic and should not create any files
	InitLogger(false, nil)
	Info("console-only test message")
	Sync()

	// No assertion on output — just verifying no panic and no file
	// is created in the working directory.
}

func TestInitLogger_FileDisabled(t *testing.T) {
	InitLogger(false, &FileOptions{Enabled: false})
	Info("disabled file test message")
	Sync()
	// No file should be created; just verify no panic.
}

func TestInitLogger_DebugMode(t *testing.T) {
	tmpDir := filepath.Join(os.TempDir(), "sekiro-logger-debug-test")
	defer os.RemoveAll(tmpDir)

	opts := &FileOptions{
		Enabled:    true,
		Dir:        tmpDir,
		Filename:   "debug.log",
		MaxSize:    1,
		MaxBackups: 1,
		MaxAge:     1,
		Compress:   false,
	}

	InitLogger(true, opts)

	Debug("debug mode test message")
	Sync()

	logPath := filepath.Join(tmpDir, "debug.log")
	data, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatalf("expected log file to be created in debug mode: %v", err)
	}
	if op := string(data); !contains(op, "debug mode test message") {
		t.Fatalf("expected log file to contain debug message, got: %s", op)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && searchSubstring(s, substr)
}

func searchSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
