package main

import (
	"context"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestRunAdapterPropagatesExitOutput(t *testing.T) {
	var command []string
	if runtime.GOOS == "windows" {
		command = []string{"cmd", "/c", "echo standard-out & echo standard-err 1>&2 & exit /b 7"}
	} else {
		command = []string{"sh", "-c", "printf standard-out; printf standard-err >&2; exit 7"}
	}
	err := runAdapter(context.Background(), t.TempDir(), "broken-adapter", command...)
	if err == nil {
		t.Fatal("expected adapter failure")
	}
	for _, want := range []string{"broken-adapter", "exit code 7", "standard-out", "standard-err"} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q missing %q", err, want)
		}
	}
}

func TestRunAdapterHonorsContext(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	var command []string
	if runtime.GOOS == "windows" {
		command = []string{"cmd", "/c", "ping 127.0.0.1 -n 4 > nul"}
	} else {
		command = []string{"sh", "-c", "sleep 1"}
	}
	if err := runAdapter(ctx, t.TempDir(), "slow-adapter", command...); err == nil {
		t.Fatal("expected context timeout")
	}
}
