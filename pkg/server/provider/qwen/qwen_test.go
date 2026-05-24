package qwen

import (
	"testing"

	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/model"
)

func TestProviderName(t *testing.T) {
	p := New(config.ProviderConfig{})
	if p.Name() != "qwen" {
		t.Fatalf("Name() = %q, want qwen", p.Name())
	}
}

func TestProviderMatch(t *testing.T) {
	p := New(config.ProviderConfig{})
	cases := map[string]bool{
		"Qwen3-Max":      true,
		"qwen3-flash":    true,
		"qwen-anything":  true,
		"gpt-4":          false,
		"claude-opus-4":  false,
		"":               false,
	}
	for name, want := range cases {
		if got := p.Match(name); got != want {
			t.Errorf("Match(%q) = %v, want %v", name, got, want)
		}
	}
}

func TestProviderBuildClientAction(t *testing.T) {
	p := New(config.ProviderConfig{})
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			{Role: model.ChatMessageRoleUser, Content: "hello"},
		},
	}
	action, err := p.BuildClientAction(req)
	if err != nil {
		t.Fatalf("BuildClientAction unexpected error: %v", err)
	}
	if action.Action != ActionChatStream {
		t.Errorf("Action = %q, want %q", action.Action, ActionChatStream)
	}

	target, ok := action.Payload["target"].(string)
	if !ok || target != DefaultChatTarget {
		t.Errorf("payload.target wrong: %v", action.Payload["target"])
	}
	body, ok := action.Payload["body"].(*QwenChatRequest)
	if !ok || body == nil {
		t.Fatalf("payload.body wrong type: %T", action.Payload["body"])
	}
	if body.Model != "tongyi-qwen3-max-model-agent" {
		t.Errorf("inner body model not mapped, got %q", body.Model)
	}
}

func TestProviderBuildClientAction_PropagatesError(t *testing.T) {
	p := New(config.ProviderConfig{})
	if _, err := p.BuildClientAction(&model.ChatCompletionRequest{Model: ""}); err == nil {
		t.Fatalf("expected error for empty model")
	}
}

func TestProviderStreamDecoderNilUntilM3(t *testing.T) {
	p := New(config.ProviderConfig{})
	if p.StreamDecoder() != nil {
		t.Errorf("StreamDecoder should be nil until M3")
	}
}

func TestProviderTimeout(t *testing.T) {
	p := New(config.ProviderConfig{})
	if got := p.Timeout().Seconds(); got != 120 {
		t.Errorf("default timeout = %v, want 120s", got)
	}
	p2 := New(config.ProviderConfig{QwenTimeoutSeconds: 90})
	if got := p2.Timeout().Seconds(); got != 90 {
		t.Errorf("custom timeout = %v, want 90s", got)
	}
}

func TestProviderLogChunks(t *testing.T) {
	p := New(config.ProviderConfig{QwenLogChunks: true})
	if !p.LogChunks() {
		t.Errorf("LogChunks() should follow config")
	}
}
