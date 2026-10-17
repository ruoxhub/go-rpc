package config

import (
	"testing"
)

func TestEnvStringReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_STRING", "")
	got := envString("TEST_ENV_STRING", "fallback")
	if got != "fallback" {
		t.Fatalf("envString() = %q, want %q", got, "fallback")
	}
}

func TestEnvStringReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_STRING", "hello")
	got := envString("TEST_ENV_STRING", "fallback")
	if got != "hello" {
		t.Fatalf("envString() = %q, want %q", got, "hello")
	}
}

func TestEnvIntReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "")
	got := envInt("TEST_ENV_INT", 42)
	if got != 42 {
		t.Fatalf("envInt() = %d, want %d", got, 42)
	}
}

func TestEnvIntReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "99")
	got := envInt("TEST_ENV_INT", 42)
	if got != 99 {
		t.Fatalf("envInt() = %d, want %d", got, 99)
	}
}

func TestEnvIntReturnsDefaultOnInvalidValue(t *testing.T) {
	t.Setenv("TEST_ENV_INT", "not-a-number")
	got := envInt("TEST_ENV_INT", 42)
	if got != 42 {
		t.Fatalf("envInt() = %d, want %d", got, 42)
	}
}

func TestEnvBoolReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "")
	got := envBool("TEST_ENV_BOOL", true)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvBoolReturnsValueWhenSet(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "true")
	got := envBool("TEST_ENV_BOOL", false)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvBoolReturnsDefaultOnInvalidValue(t *testing.T) {
	t.Setenv("TEST_ENV_BOOL", "maybe")
	got := envBool("TEST_ENV_BOOL", true)
	if got != true {
		t.Fatalf("envBool() = %v, want %v", got, true)
	}
}

func TestEnvStringSliceReturnsDefaultWhenUnset(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "")
	got := envStringSlice("TEST_ENV_SLICE", []string{"a", "b"})
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("envStringSlice() = %v, want [a b]", got)
	}
}

func TestEnvStringSliceParsesCommaDelimited(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "x,y,z")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 3 || got[0] != "x" || got[1] != "y" || got[2] != "z" {
		t.Fatalf("envStringSlice() = %v, want [x y z]", got)
	}
}

func TestEnvStringSliceTrimsWhitespace(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", " a , b , c ")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 3 || got[0] != "a" || got[1] != "b" || got[2] != "c" {
		t.Fatalf("envStringSlice() = %v, want [a b c]", got)
	}
}

func TestEnvStringSliceSkipsEmptyEntries(t *testing.T) {
	t.Setenv("TEST_ENV_SLICE", "a,,b")
	got := envStringSlice("TEST_ENV_SLICE", nil)
	if len(got) != 2 || got[0] != "a" || got[1] != "b" {
		t.Fatalf("envStringSlice() = %v, want [a b]", got)
	}
}
