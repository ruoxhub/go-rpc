package handler

import (
	"bytes"
	json "github.com/goccy/go-json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
)

// fixtureRoot resolves the repository root by walking up from the package
// directory until go.mod is found. The qwenai_completions_response.txt and
// completions_request_body.json fixtures live in the repo root.
func fixtureRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	t.Fatalf("repo root (containing go.mod) not found from %s", dir)
	return ""
}

// TestQwenSSEParser_RealFixture feeds the recorded qwenai_completions_response.txt
// into the parser and verifies that the concatenated content reconstructs the
// upstream answer exactly. This pins behavior against the real qwen SSE shape
// (response.created envelope + delta.{role,content,phase,status} per chunk).
func TestQwenSSEParser_RealFixture(t *testing.T) {
	root := fixtureRoot(t)
	data, err := os.ReadFile(filepath.Join(root, "qwenai_completions_response.txt"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}

	parser := newQwenSSEParser()
	events := parser.Feed(string(data))

	var content strings.Builder
	var roleSeen string
	var finished bool
	for _, ev := range events {
		if ev.Role != "" && roleSeen == "" {
			roleSeen = ev.Role
		}
		if ev.Content != "" {
			content.WriteString(ev.Content)
		}
		if ev.Finished {
			finished = true
		}
	}

	if got := content.String(); got != "Hello! How can I help you today?" {
		t.Fatalf("reconstructed content mismatch:\n got=%q\nwant=%q", got, "Hello! How can I help you today?")
	}
	if roleSeen != "assistant" {
		t.Fatalf("expected role=assistant, got %q", roleSeen)
	}
	if !finished {
		t.Fatalf("expected finished=true (status:finished frame missing)")
	}
}

// TestQwenSSEParser_ChunkSplit guarantees the parser tolerates upstream byte
// boundaries that fall mid-event. The browser extension can deliver a single
// SSE event split across two invoke_stream frames; the parser must buffer.
func TestQwenSSEParser_ChunkSplit(t *testing.T) {
	full := `data: {"choices":[{"delta":{"role":"assistant","content":"Hello"}}]}` + "\n\n" +
		`data: {"choices":[{"delta":{"content":", world"}}]}` + "\n\n" +
		`data: [DONE]` + "\n\n"

	// Split right inside the second event's JSON body.
	splitAt := strings.Index(full, `world`)
	if splitAt <= 0 {
		t.Fatalf("could not find split point in fixture")
	}

	parser := newQwenSSEParser()
	first := parser.Feed(full[:splitAt])
	second := parser.Feed(full[splitAt:])

	var content strings.Builder
	var done bool
	for _, ev := range append(first, second...) {
		content.WriteString(ev.Content)
		if ev.Done {
			done = true
		}
	}
	if got := content.String(); got != "Hello, world" {
		t.Fatalf("split-resilient parse failed: got=%q", got)
	}
	if !done {
		t.Fatalf("parser missed the [DONE] sentinel")
	}
}

// TestQwenSSEParser_IgnoresEnvelopeFrames ensures non-choices frames such as
// `response.created` are silently skipped and produce no spurious events.
func TestQwenSSEParser_IgnoresEnvelopeFrames(t *testing.T) {
	input := `data: {"response.created":{"chat_id":"abc","response_id":"xyz"}}` + "\n\n"
	parser := newQwenSSEParser()
	events := parser.Feed(input)
	for _, ev := range events {
		if ev.Content != "" || ev.Role != "" || ev.Finished || ev.Done {
			t.Fatalf("envelope frame should not produce content event, got %+v", ev)
		}
	}
}

// TestExtractQwenChatID_Shapes covers the createChat response shapes we have
// observed (and a couple of plausible ones) so future upstream tweaks are
// caught here rather than as an opaque "missing chat id" runtime failure.
func TestExtractQwenChatID_Shapes(t *testing.T) {
	cases := []struct {
		name string
		body string
		want string
	}{
		{"top_level_id", `{"id":"chat-123"}`, "chat-123"},
		{"chat_object", `{"chat":{"id":"chat-456"},"success":true}`, "chat-456"},
		{"data_id", `{"data":{"id":"chat-789"}}`, "chat-789"},
		{"data_chat_id", `{"data":{"chat":{"id":"chat-aaa"}}}`, "chat-aaa"},
		{
			"server_envelope_success",
			`{"clientId":"g9wwwonwe","data":{"id":"584279d0-e7ad-4dc4-a6d6-49da4720bf73"},"group":"qwenai","message":"success","request_id":"f19832d5-e47d-4459-85c2-4b0ac2686e83","status":0,"success":true}`,
			"584279d0-e7ad-4dc4-a6d6-49da4720bf73",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := extractQwenChatID([]byte(tc.body))
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.want {
				t.Fatalf("got %q want %q", got, tc.want)
			}
		})
	}

	if _, err := extractQwenChatID([]byte(`{"foo":"bar"}`)); err == nil {
		t.Fatalf("expected error for response without id")
	}
	if _, err := extractQwenChatID(nil); err == nil {
		t.Fatalf("expected error for empty body")
	}

	// success=false envelope must surface the upstream message rather than
	// a generic "missing chat id" error.
	failBody := `{"success":false,"message":"rate limited","data":null}`
	_, err := extractQwenChatID([]byte(failBody))
	if err == nil {
		t.Fatalf("expected error for success=false envelope")
	}
	if !strings.Contains(err.Error(), "rate limited") {
		t.Fatalf("expected error to surface upstream message, got %q", err.Error())
	}
}

// TestFlattenMessagesToPrompt_Basic covers role labelling, multi-modal content
// arrays, and the trailing "Assistant:" guidance suffix that nudges the
// upstream model to actually answer.
func TestFlattenMessagesToPrompt_Basic(t *testing.T) {
	messages := []interface{}{
		map[string]interface{}{"role": "system", "content": "You are helpful."},
		map[string]interface{}{"role": "user", "content": "Hi"},
		map[string]interface{}{
			"role": "user",
			"content": []interface{}{
				map[string]interface{}{"type": "text", "text": "image attached"},
				map[string]interface{}{"type": "image_url", "image_url": map[string]interface{}{"url": "x"}},
			},
		},
		map[string]interface{}{"role": "", "content": ""}, // skipped
	}
	got, err := flattenMessagesToPrompt(messages)
	if err != nil {
		t.Fatalf("flatten failed: %v", err)
	}
	if !strings.Contains(got, "System: You are helpful.") {
		t.Fatalf("missing system label: %q", got)
	}
	if !strings.Contains(got, "User: Hi") {
		t.Fatalf("missing user label: %q", got)
	}
	if !strings.Contains(got, "image attached") {
		t.Fatalf("missing multi-modal text part: %q", got)
	}
	if !strings.HasSuffix(strings.TrimRight(got, " "), "Assistant:") {
		t.Fatalf("missing trailing assistant guidance: %q", got)
	}
}

// TestFlattenMessagesToPrompt_RealRequest verifies the shape from the
// completions_request_body.json fixture (the test-data file referenced in
// prd.md). We avoid loading the whole 435 KB blob into the parser; instead we
// pick the system + user roles directly via the json decoder used by the
// handler and ensure they survive flattening.
func TestFlattenMessagesToPrompt_RealRequest(t *testing.T) {
	root := fixtureRoot(t)
	body, err := os.ReadFile(filepath.Join(root, "completions_request_body.json"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}

	var raw map[string]interface{}
	if err := jsonUnmarshal(body, &raw); err != nil {
		t.Fatalf("decode fixture: %v", err)
	}
	msgs, ok := raw["messages"].([]interface{})
	if !ok || len(msgs) < 2 {
		t.Fatalf("fixture missing messages")
	}
	prompt, err := flattenMessagesToPrompt(msgs)
	if err != nil {
		t.Fatalf("flatten failed: %v", err)
	}
	if !strings.Contains(prompt, "System:") || !strings.Contains(prompt, "User:") {
		t.Fatalf("expected System/User labels in flattened prompt, head=%q", head(prompt, 200))
	}
	if !strings.HasSuffix(strings.TrimRight(prompt, " "), "Assistant:") {
		t.Fatalf("expected Assistant: trailer in flattened prompt")
	}
}

// TestDecodeStreamChunkText handles both the JSON-string-literal form that
// BaseClient sends and the rare raw-bytes fallback path.
func TestDecodeStreamChunkText(t *testing.T) {
	literal := []byte(`"data: hi\n\n"`)
	got, err := decodeStreamChunkText(literal)
	if err != nil {
		t.Fatalf("string literal decode failed: %v", err)
	}
	if got != "data: hi\n\n" {
		t.Fatalf("string literal decode wrong: %q", got)
	}

	raw := []byte(`raw bytes not json`)
	got2, err := decodeStreamChunkText(raw)
	if err != nil {
		t.Fatalf("fallback decode errored: %v", err)
	}
	if got2 != "raw bytes not json" {
		t.Fatalf("fallback decode wrong: %q", got2)
	}

	if got3, err := decodeStreamChunkText(nil); err != nil || got3 != "" {
		t.Fatalf("empty decode wrong: got=%q err=%v", got3, err)
	}
}

// TestQwenSSEParser_PhaseSurfacing checks that the parser carries the
// upstream `delta.phase` value through unchanged. The streaming handler uses
// it to route Chain-of-Thought output to OpenAI's `reasoning_content` field
// instead of leaking it into the user-visible answer.
func TestQwenSSEParser_PhaseSurfacing(t *testing.T) {
	input := `data: {"choices":[{"delta":{"role":"assistant","content":"thinking...","phase":"thinking"}}]}` + "\n\n" +
		`data: {"choices":[{"delta":{"content":"final","phase":"answer"}}]}` + "\n\n"

	parser := newQwenSSEParser()
	events := parser.Feed(input)
	if len(events) != 2 {
		t.Fatalf("expected 2 events, got %d", len(events))
	}
	if events[0].Phase != "thinking" || events[0].Content != "thinking..." {
		t.Fatalf("event 0 wrong: %+v", events[0])
	}
	if events[1].Phase != "answer" || events[1].Content != "final" {
		t.Fatalf("event 1 wrong: %+v", events[1])
	}
}

// TestQwenSSEParser_RealFixturePhase locks in the assertion that the recorded
// qwenai_completions_response.txt fixture only carries phase="answer" content.
// If qwen ever adds an upstream "thinking" preamble, this test will trip and
// flag the change so we can audit reasoning_content routing behavior.
func TestQwenSSEParser_RealFixturePhase(t *testing.T) {
	root := fixtureRoot(t)
	data, err := os.ReadFile(filepath.Join(root, "qwenai_completions_response.txt"))
	if err != nil {
		t.Fatalf("read fixture: %v", err)
	}
	parser := newQwenSSEParser()
	events := parser.Feed(string(data))
	for i, ev := range events {
		if ev.Content != "" && ev.Phase != "answer" {
			t.Fatalf("event %d carries content %q under unexpected phase=%q (want \"answer\")", i, ev.Content, ev.Phase)
		}
	}
}

// TestQwenSSEParser_CommentsAndEmptyData ensures the parser silently drops
// SSE comment lines (": heartbeat") and `data:` lines whose payload is empty,
// so they don't manifest as spurious empty events that would trigger an
// assistant-role chunk with no content.
func TestQwenSSEParser_CommentsAndEmptyData(t *testing.T) {
	input := ": ping\n\n" + // pure comment block
		"data:   \n\n" + // empty data line
		"data: \n\n" + // another empty data line
		`data: {"choices":[{"delta":{"content":"x"}}]}` + "\n\n"

	parser := newQwenSSEParser()
	events := parser.Feed(input)
	if len(events) != 1 {
		t.Fatalf("expected exactly 1 emitted event from real-content frame, got %d: %+v", len(events), events)
	}
	if events[0].Content != "x" {
		t.Fatalf("emitted event should carry content=x, got %+v", events[0])
	}
}

// jsonUnmarshal delegates to the same goccy/go-json decoder the production
// handler uses, so the test stays in the same JSON dialect.
func jsonUnmarshal(data []byte, v interface{}) error {
	return json.Unmarshal(data, v)
}

func head(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// TestHandleQwenChatCompletions_RejectsBadRequests covers the input validation
// path of the qwen handler. We don't need a real wsHandler / clientManager
// here because all four cases bail out before client selection.
func TestHandleQwenChatCompletions_RejectsBadRequests(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()
	handler.timeoutManager = forwarder.NewTimeoutManager(nil)
	defer handler.timeoutManager.Shutdown()

	r := gin.New()
	r.POST("/api/chat/completions", handler.HandleQwenChatCompletions)

	cases := []struct {
		name     string
		body     string
		wantCode int
	}{
		{"invalid_json", `{`, http.StatusBadRequest},
		{"missing_model", `{"messages":[{"role":"user","content":"hi"}]}`, http.StatusBadRequest},
		{"missing_messages", `{"model":"qwen3.7-max"}`, http.StatusBadRequest},
		{"empty_messages", `{"model":"qwen3.7-max","messages":[]}`, http.StatusBadRequest},
		{"empty_prompt", `{"model":"qwen3.7-max","messages":[{"role":"user","content":""}]}`, http.StatusBadRequest},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			w := performJSON(r, http.MethodPost, "/api/chat/completions", tc.body)
			if w.Code != tc.wantCode {
				t.Fatalf("status = %d, want %d (body=%s)", w.Code, tc.wantCode, w.Body.String())
			}
			var got map[string]interface{}
			if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
				t.Fatalf("decode response: %v", err)
			}
			if errObj, ok := got["error"].(map[string]interface{}); !ok || errObj["message"] == "" {
				t.Fatalf("expected error.message in response, got %+v", got)
			}
		})
	}
}

// TestHandleQwenChatCompletions_NoClientAvailable verifies the handler returns
// a graceful "no qwenai client available" error when the qwenai group is
// empty (e.g. nobody is plugged in via the browser extension).
func TestHandleQwenChatCompletions_NoClientAvailable(t *testing.T) {
	gin.SetMode(gin.TestMode)
	mockManager := newMockClientManager()
	defer mockManager.Close()

	handler := newTestAPIHandler(mockManager)
	handler.router = newDefaultTestRouter()
	handler.timeoutManager = forwarder.NewTimeoutManager(nil)
	defer handler.timeoutManager.Shutdown()

	r := gin.New()
	r.POST("/api/chat/completions", handler.HandleQwenChatCompletions)

	body := `{"model":"qwen3.7-max","messages":[{"role":"user","content":"hi"}]}`
	w := performJSON(r, http.MethodPost, "/api/chat/completions", body)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (body=%s)", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	errObj, ok := got["error"].(map[string]interface{})
	if !ok {
		t.Fatalf("expected error in response, got %+v", got)
	}
	msg, _ := errObj["message"].(string)
	if !strings.Contains(msg, "no qwenai client available") {
		t.Fatalf("expected no-client message, got %q", msg)
	}
}

// performJSON is a JSON-body convenience wrapper around the package's
// performRequest helper so the qwen tests don't need to reimplement HTTP
// boilerplate. Lives next to the qwen tests because handlers_test.go
// already exposes the underlying helper.
func performJSON(r *gin.Engine, method, path string, body string) *httptest.ResponseRecorder {
	w := httptest.NewRecorder()
	req := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	r.ServeHTTP(w, req)
	return w
}
