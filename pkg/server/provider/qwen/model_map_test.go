package qwen

import "testing"

func TestShouldHandle(t *testing.T) {
	cases := []struct {
		name string
		want bool
	}{
		{"Qwen3-Max", true},
		{"qwen3-max", true},
		{"QWEN3-MAX-THINKING", true},
		{"qwen-something-experimental", true},
		{"  Qwen3-Plus  ", true}, // 接受首尾空白
		{"gpt-4o", false},
		{"claude-opus-4", false},
		{"", false},
	}
	for _, c := range cases {
		c := c
		t.Run(c.name, func(t *testing.T) {
			if got := ShouldHandle(c.name); got != c.want {
				t.Fatalf("ShouldHandle(%q)=%v, want %v", c.name, got, c.want)
			}
		})
	}
}

func TestResolveModel_KnownAliases(t *testing.T) {
	cases := []struct {
		input string
		want  ResolvedModel
	}{
		{"Qwen3-Max", ResolvedModel{QwenID: "tongyi-qwen3-max-model-agent"}},
		{"qwen3-max", ResolvedModel{QwenID: "tongyi-qwen3-max-model-agent"}},
		{
			"Qwen3-Max-Thinking",
			ResolvedModel{QwenID: "tongyi-qwen3-max-thinking-agent", EnableThinking: true},
		},
		{"Qwen3-Plus", ResolvedModel{QwenID: "tongyi-qwen-plus-agent"}},
		{"Qwen3.5-Plus", ResolvedModel{QwenID: "Qwen3.5-Plus"}},
		{"Qwen3-Flash", ResolvedModel{QwenID: "qwen3-flash"}},
		{"Qwen3-Coder", ResolvedModel{QwenID: "qwen3-coder-plus"}},
	}
	for _, c := range cases {
		c := c
		t.Run(c.input, func(t *testing.T) {
			got := ResolveModel(c.input)
			if got != c.want {
				t.Fatalf("ResolveModel(%q)=%+v, want %+v", c.input, got, c.want)
			}
		})
	}
}

func TestResolveModel_KeywordInference(t *testing.T) {
	cases := []struct {
		input        string
		wantThink    bool
		wantSearch   bool
		wantQwenID   string
	}{
		{"Qwen3-Max", false, false, "tongyi-qwen3-max-model-agent"},
		// "think" → 切换到 max-thinking 变体
		{"Qwen3-Max-Thinking", true, false, "tongyi-qwen3-max-thinking-agent"},
		// 仅含 "r1" 也算 thinking
		{"qwen-r1", true, false, "qwen-r1"},
		// search 关键字
		{"qwen-search-experimental", false, true, "qwen-search-experimental"},
		// 同时含 think 和 search
		{"qwen-thinking-search", true, true, "qwen-thinking-search"},
	}
	for _, c := range cases {
		c := c
		t.Run(c.input, func(t *testing.T) {
			got := ResolveModel(c.input)
			if got.EnableThinking != c.wantThink {
				t.Errorf("EnableThinking: got %v, want %v", got.EnableThinking, c.wantThink)
			}
			if got.EnableWebSearch != c.wantSearch {
				t.Errorf("EnableWebSearch: got %v, want %v", got.EnableWebSearch, c.wantSearch)
			}
			if got.QwenID != c.wantQwenID {
				t.Errorf("QwenID: got %q, want %q", got.QwenID, c.wantQwenID)
			}
		})
	}
}

func TestResolveModel_UnknownPassThrough(t *testing.T) {
	got := ResolveModel("qwen-some-future-model")
	if got.QwenID != "qwen-some-future-model" {
		t.Fatalf("unknown qwen models should be passed through verbatim, got %q", got.QwenID)
	}
}

func TestResolveModel_Empty(t *testing.T) {
	got := ResolveModel("")
	if (got != ResolvedModel{}) {
		t.Fatalf("empty input should yield zero ResolvedModel, got %+v", got)
	}
}

func TestResolveModel_TrimsWhitespace(t *testing.T) {
	got := ResolveModel("  Qwen3-Max  ")
	if got.QwenID != "tongyi-qwen3-max-model-agent" {
		t.Fatalf("whitespace-trimmed lookup failed: got %q", got.QwenID)
	}
}
