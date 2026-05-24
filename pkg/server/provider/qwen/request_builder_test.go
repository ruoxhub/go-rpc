package qwen

import (
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
)

func newFixedOpts() *BuildOptions {
	calls := 0
	return &BuildOptions{
		Now: func() time.Time { return time.Date(2026, 5, 23, 10, 0, 0, 0, time.UTC) },
		NewID: func() string {
			calls++
			return fmt.Sprintf("id-%d", calls)
		},
	}
}

func userMsg(text string) model.ChatCompletionMessage {
	return model.ChatCompletionMessage{Role: model.ChatMessageRoleUser, Content: text}
}

func systemMsg(text string) model.ChatCompletionMessage {
	return model.ChatCompletionMessage{Role: model.ChatMessageRoleSystem, Content: text}
}

func assistantMsg(text string) model.ChatCompletionMessage {
	return model.ChatCompletionMessage{Role: model.ChatMessageRoleAssistant, Content: text}
}

func TestBuildRequest_BasicSingleTurn(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{userMsg("hello world")},
	}
	got, err := BuildRequest(req, newFixedOpts())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got.Model != "tongyi-qwen3-max-model-agent" {
		t.Errorf("model not mapped, got %q", got.Model)
	}
	if got.Scene != "chat" || got.SubScene != "chat" {
		t.Errorf("scene/sub_scene mismatch, got %q/%q", got.Scene, got.SubScene)
	}
	if got.ProtocolVersion != "v2" || got.BizID != "ai_qwen" {
		t.Errorf("protocol_version/biz_id mismatch")
	}
	if got.From != "default" || got.ParentReqID != "0" {
		t.Errorf("from/parent_req_id mismatch")
	}
	if got.BizData != `{"entryPoint":"tongyigw"}` {
		t.Errorf("biz_data mismatch, got %q", got.BizData)
	}
	if got.SceneParam != "first_turn" || got.ChatClient != "h5" {
		t.Errorf("scene_param/chat_client mismatch")
	}
	if got.DeepSearch != "0" || got.EnableSearch {
		t.Errorf("deep_search/enable_search should be off for plain Qwen3-Max")
	}
	if got.Temporary {
		t.Errorf("temporary must be false")
	}

	if len(got.Messages) != 1 {
		t.Fatalf("want 1 folded message, got %d", len(got.Messages))
	}
	msg := got.Messages[0]
	if msg.Content != "hello world" {
		t.Errorf("content mismatch, got %q", msg.Content)
	}
	if msg.MimeType != "text/plain" {
		t.Errorf("mime_type mismatch, got %q", msg.MimeType)
	}
	if got, want := msg.MetaData["ori_query"], "hello world"; got != want {
		t.Errorf("meta_data.ori_query mismatch, got %v want %v", got, want)
	}

	if got.ReqID == "" || got.SessionID == "" || got.ReqID == got.SessionID {
		t.Errorf("req_id/session_id should be non-empty and distinct, got %q/%q", got.ReqID, got.SessionID)
	}
	if got.ClientTM == "" {
		t.Errorf("client_tm must be non-empty")
	}
}

func TestBuildRequest_SystemMessageExtracted(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			systemMsg("you are a helpful agent"),
			userMsg("do thing"),
		},
	}
	got, err := BuildRequest(req, newFixedOpts())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := "you are a helpful agent\n\nUser: do thing"
	if got.Messages[0].Content != want {
		t.Errorf("folded content mismatch:\nwant %q\n got %q", want, got.Messages[0].Content)
	}
	if got.Messages[0].MetaData["ori_query"] != want {
		t.Errorf("ori_query should mirror final content")
	}
}

func TestBuildRequest_MultipleSystemMessagesAreJoined(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			systemMsg("rule one"),
			systemMsg("rule two"),
			userMsg("hi"),
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	if !strings.Contains(got.Messages[0].Content, "rule one\n\nrule two") {
		t.Errorf("multiple system messages should be joined: got %q", got.Messages[0].Content)
	}
}

func TestBuildRequest_MultiTurnFolds(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			userMsg("Q1"),
			assistantMsg("A1"),
			userMsg("Q2"),
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	want := "Q1\n\nAssistant: A1\n\nQ2"
	if got.Messages[0].Content != want {
		t.Errorf("multi-turn fold mismatch:\nwant %q\n got %q", want, got.Messages[0].Content)
	}
}

func TestBuildRequest_ThinkingModelInferenceAndDeepSearch(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    "Qwen3-Max-Thinking",
		Messages: []model.ChatCompletionMessage{userMsg("deep question")},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	if got.Model != "tongyi-qwen3-max-thinking-agent" {
		t.Errorf("thinking variant not selected, got %q", got.Model)
	}
	if got.DeepSearch != "1" {
		t.Errorf("deep_search must be 1 when thinking is enabled")
	}
}

func TestBuildRequest_WebSearchInferred(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    "qwen-search-experimental",
		Messages: []model.ChatCompletionMessage{userMsg("what's hot today")},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	if !got.EnableSearch {
		t.Errorf("enable_search must be true when model name contains 'search'")
	}
	if got.DeepSearch != "1" {
		t.Errorf("deep_search must be 1 when web search is enabled")
	}
}

func TestBuildRequest_OverridesTakePrecedence(t *testing.T) {
	thinkOff := false
	searchOn := true
	opts := newFixedOpts()
	opts.EnableThinkingOverride = &thinkOff
	opts.EnableWebSearchOverride = &searchOn

	req := &model.ChatCompletionRequest{
		// 关键字推断 thinking=true，但 override 关闭它
		Model:    "Qwen3-Max-Thinking",
		Messages: []model.ChatCompletionMessage{userMsg("hi")},
	}
	got, _ := BuildRequest(req, opts)
	if !got.EnableSearch {
		t.Errorf("explicit EnableWebSearchOverride=true must take effect")
	}
	if got.DeepSearch != "1" {
		t.Errorf("deep_search must be 1 because web search is on")
	}
	// thinking 显式关闭后，alias 仍然把 "Qwen3-Max-Thinking" 映射到 thinking-agent；
	// 但若用户显式说不要 thinking，未来 M3 的 decoder 可据此跳过 reasoning_content 提取。
	// 此处只断言 deep_search/enable_search 行为。
}

func TestBuildRequest_ToolsInjectedIntoSystemPromptAndHint(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{userMsg("do stuff")},
		Tools: []model.Tool{
			{
				Type: model.ToolTypeFunction,
				Function: &model.FunctionDefinition{
					Name:        "lookup_user",
					Description: "Look up a user by id",
					Parameters: map[string]interface{}{
						"type": "object",
					},
				},
			},
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	if !strings.Contains(got.Messages[0].Content, "lookup_user") {
		t.Errorf("tools prompt missing tool name; got: %q", got.Messages[0].Content)
	}
	if !strings.Contains(got.Messages[0].Content, "[function_calls]") {
		t.Errorf("tool wrap hint missing; got: %q", got.Messages[0].Content)
	}
}

func TestBuildRequest_SkipsToolPromptIfAlreadyInjected(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			systemMsg("...[function_calls] template..."),
			userMsg("go"),
		},
		Tools: []model.Tool{
			{Type: model.ToolTypeFunction, Function: &model.FunctionDefinition{Name: "noop"}},
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	// tools 系统 prompt 不再追加 noop，保持已有 system 不变
	if strings.Contains(got.Messages[0].Content, "noop") {
		t.Errorf("tools prompt re-injected when already present; got: %q", got.Messages[0].Content)
	}
	// TOOL_WRAP_HINT 也不应再追加；最终 content 里 [function_calls] 应只来自 system。
	if strings.Count(got.Messages[0].Content, "[function_calls]") != 1 {
		t.Errorf("TOOL_WRAP_HINT should not be re-added; got: %q", got.Messages[0].Content)
	}
}

func TestBuildRequest_MultimodalContentTextOnlyExtracted(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			{
				Role: model.ChatMessageRoleUser,
				MultiContent: []model.ChatMessagePart{
					{Type: model.ChatMessagePartTypeImageURL, ImageURL: &model.ChatMessageImageURL{URL: "https://x"}},
					{Type: model.ChatMessagePartTypeText, Text: "describe this"},
				},
			},
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	if got.Messages[0].Content != "describe this" {
		t.Errorf("multimodal text not extracted, got %q", got.Messages[0].Content)
	}
}

func TestBuildRequest_AssistantToolCallsInHistory(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model: "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{
			userMsg("look up alice"),
			{
				Role: model.ChatMessageRoleAssistant,
				ToolCalls: []model.ToolCall{
					{
						ID:   "tc-1",
						Type: model.ToolTypeFunction,
						Function: model.FunctionCall{
							Name:      "lookup_user",
							Arguments: `{"name":"alice"}`,
						},
					},
				},
			},
			{
				Role:       model.ChatMessageRoleTool,
				ToolCallID: "tc-1",
				Content:    `{"id":1,"name":"alice"}`,
			},
			userMsg("what's her email"),
		},
	}
	got, _ := BuildRequest(req, newFixedOpts())
	content := got.Messages[0].Content
	if !strings.Contains(content, "tc-1") || !strings.Contains(content, `"name":"alice"`) {
		t.Errorf("assistant tool_calls history not folded properly; got: %q", content)
	}
	if !strings.Contains(content, "tool_result(tc-1)") {
		t.Errorf("tool role result missing; got: %q", content)
	}
}

func TestBuildRequest_ErrorOnEmptyModel(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    " ",
		Messages: []model.ChatCompletionMessage{userMsg("x")},
	}
	if _, err := BuildRequest(req, newFixedOpts()); err == nil {
		t.Fatalf("expected error for empty model")
	}
}

func TestBuildRequest_ErrorOnEmptyMessages(t *testing.T) {
	req := &model.ChatCompletionRequest{Model: "Qwen3-Max"}
	if _, err := BuildRequest(req, newFixedOpts()); err == nil {
		t.Fatalf("expected error for empty messages")
	}
}

func TestBuildRequest_ErrorOnNil(t *testing.T) {
	if _, err := BuildRequest(nil, nil); err == nil {
		t.Fatalf("expected error for nil request")
	}
}

func TestBuildRequest_DefaultIDsAreNonEmpty(t *testing.T) {
	req := &model.ChatCompletionRequest{
		Model:    "Qwen3-Max",
		Messages: []model.ChatCompletionMessage{userMsg("hi")},
	}
	// 不传 opts，使用真实默认 ID 生成器
	got, err := BuildRequest(req, nil)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(got.ReqID) != 32 {
		t.Errorf("default req_id should be 32-char hex, got %q (len %d)", got.ReqID, len(got.ReqID))
	}
	if len(got.SessionID) != 32 {
		t.Errorf("default session_id should be 32-char hex, got %q (len %d)", got.SessionID, len(got.SessionID))
	}
	if got.ReqID == got.SessionID {
		t.Errorf("req_id and session_id must differ")
	}
}
