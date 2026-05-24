package provider_test

import (
	"sync"
	"testing"

	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/provider"
)

type stubProvider struct {
	name    string
	matchFn func(string) bool
}

func (s *stubProvider) Name() string         { return s.name }
func (s *stubProvider) Match(m string) bool  { return s.matchFn(m) }
func (s *stubProvider) BuildClientAction(*model.ChatCompletionRequest) (provider.ClientAction, error) {
	return provider.ClientAction{Action: s.name, Payload: map[string]any{}}, nil
}
func (s *stubProvider) StreamDecoder() provider.StreamDecoder { return nil }

func newStub(name string, accept ...string) *stubProvider {
	set := make(map[string]struct{}, len(accept))
	for _, a := range accept {
		set[a] = struct{}{}
	}
	return &stubProvider{
		name: name,
		matchFn: func(m string) bool {
			_, ok := set[m]
			return ok
		},
	}
}

func TestResolveHit(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	provider.Register(newStub("qwen", "Qwen3-Max"))
	got := provider.Resolve("Qwen3-Max")
	if got == nil || got.Name() != "qwen" {
		t.Fatalf("want qwen provider, got %v", got)
	}
}

func TestResolveMiss(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	provider.Register(newStub("qwen", "Qwen3-Max"))
	if got := provider.Resolve("gpt-5"); got != nil {
		t.Fatalf("want nil for unmatched model, got %v", got)
	}
}

func TestResolveOrderedFirstWins(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	provider.Register(newStub("alpha", "shared"))
	provider.Register(newStub("beta", "shared"))
	got := provider.Resolve("shared")
	if got == nil || got.Name() != "alpha" {
		t.Fatalf("first-registered should win, got %v", got)
	}
}

func TestRegisterReplaceSameName(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	v1 := newStub("qwen", "old-model")
	provider.Register(v1)
	v2 := newStub("qwen", "new-model")
	provider.Register(v2)

	if provider.Resolve("old-model") != nil {
		t.Fatalf("old version should have been replaced")
	}
	got := provider.Resolve("new-model")
	if got == nil || got.Name() != "qwen" {
		t.Fatalf("replacement provider not active, got %v", got)
	}
	names := provider.List()
	if len(names) != 1 || names[0] != "qwen" {
		t.Fatalf("List should contain only qwen, got %v", names)
	}
}

func TestRegisterNilNoop(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	provider.Register(nil)
	if names := provider.List(); len(names) != 0 {
		t.Fatalf("registering nil should not add entries, got %v", names)
	}
}

func TestConcurrentResolveSafe(t *testing.T) {
	provider.Reset()
	defer provider.Reset()

	provider.Register(newStub("qwen", "Qwen3-Max"))
	provider.Register(newStub("openai", "gpt-5"))

	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 200; j++ {
				_ = provider.Resolve("Qwen3-Max")
				_ = provider.Resolve("gpt-5")
				_ = provider.Resolve("unknown")
			}
		}()
	}
	wg.Wait()
}
