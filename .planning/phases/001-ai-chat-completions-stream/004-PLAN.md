---
phase: 1
plan: 4
type: feature
wave: 4
depends_on:
  - 000
  - 001
  - 002
  - 003
files_modified:
  - pkg/server/api/chat_completions.go
  - pkg/server/api/chat_completions_test.go
  - pkg/server/api/handlers_test.go
  - pkg/server/bootstrap.go
  - pkg/server/websocket/handler.go
  - pkg/server/forwarder/timeout.go
autonomous: true
requirements:
  - AI-CHAT-COMPLETIONS
must_haves:
  truths:
    - `stream=true` returns ordered SSE chunks and terminates with `data: [DONE]`.
    - Stream state is cleaned up on success, timeout, upstream error, and caller disconnect.
    - Focused and broad verification pass before commit.
  artifacts:
    - `pkg/server/api/chat_completions.go`
    - `pkg/server/api/chat_completions_test.go`
  key_links:
    - `HandleChatCompletions stream=true -> stream registry -> SSE flush`
    - `final verification -> gitnexus_detect_changes`
---

# Plan 004: SSE Streaming and Final Verification

<objective>
Complete the streaming branch for `/v1/chat/completions` and run final
cross-package verification.
</objective>

<implementation_contract>
- `stream=true`: register stream, send request, flush every chunk as
  `data: <json>\n\n`, and finish with `data: [DONE]\n\n`.
- SSE headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
  and `X-Accel-Buffering: no`.
- Handler timeout is capped by existing `maxInvokeTimeout` of 5 minutes.
- Logs must not include prompts, raw body, authorization headers, or full chunks.
</implementation_contract>

<tasks>

<task type="tdd">
  <name>Specify SSE behavior and cleanup</name>
  <files>
    <file>pkg/server/api/chat_completions_test.go</file>
    <file>pkg/server/api/handlers_test.go</file>
  </files>
  <action>
    Add tests for SSE headers, ordered chunks, `[DONE]`, timeout behavior,
    WebSocket send failure cleanup, upstream error behavior, caller cancellation
    cleanup, and no prompt/chunk leakage in logs.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionStream"</automated>
  </verify>
  <done>
    Streaming tests fail before implementation and cover all terminal paths,
    including stream registry cleanup after send failure.
  </done>
</task>

<task type="auto">
  <name>Implement SSE stream response</name>
  <files>
    <file>pkg/server/api/chat_completions.go</file>
    <file>pkg/server/api/chat_completions_test.go</file>
  </files>
  <action>
    Implement the `stream=true` branch using the Plan 002 stream registry. Flush
    every chunk, emit `[DONE]` once on normal completion, surface upstream
    errors as SSE error chunks, remove the stream immediately when
    `SendInvokeRequest` fails, and cleanup on every terminal path.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionStream|TestChatCompletionNonStream|TestHandleInvoke"</automated>
  </verify>
  <done>
    Streaming and non-streaming API tests pass together with existing invoke
    regression tests. Send failure removes stream registry state before the
    handler returns.
  </done>
</task>

<task type="auto">
  <name>Run final verification and change-scope checks</name>
  <files>
    <file>pkg/server/bootstrap.go</file>
    <file>pkg/server/api/chat_completions.go</file>
    <file>pkg/server/api/chat_completions_test.go</file>
    <file>pkg/server/api/handlers.go</file>
    <file>pkg/server/api/handlers_test.go</file>
    <file>pkg/server/websocket/handler.go</file>
    <file>pkg/server/websocket/handler_test.go</file>
    <file>pkg/server/forwarder/timeout.go</file>
    <file>pkg/server/forwarder/timeout_test.go</file>
  </files>
  <action>
    Run gofmt, focused tests, broad tests, and GitNexus detect-changes before
    commit. If GitNexus is unavailable at this point, stop before commit and
    record the blocker.
  </action>
  <verify>
    <automated>gofmt -w pkg/server/bootstrap.go pkg/server/api/chat_completions.go pkg/server/api/chat_completions_test.go pkg/server/api/handlers.go pkg/server/api/handlers_test.go pkg/server/websocket/handler.go pkg/server/websocket/handler_test.go pkg/server/forwarder/timeout.go pkg/server/forwarder/timeout_test.go</automated>
    <automated>go test ./pkg/server/api/...</automated>
    <automated>go test ./pkg/server/websocket/...</automated>
    <automated>go test ./pkg/server/forwarder/...</automated>
    <automated>go test ./...</automated>
    <automated>gitnexus_detect_changes({scope:"all", repo:"sekiro-go"})</automated>
  </verify>
  <done>
    All tests pass and affected scope is verified before commit.
  </done>
</task>

</tasks>

<verification>
<automated>go test ./pkg/server/api/...</automated>
<automated>go test ./pkg/server/websocket/...</automated>
<automated>go test ./pkg/server/forwarder/...</automated>
<automated>go test ./...</automated>
</verification>

<success_criteria>
- Streaming requests return ordered SSE chunks and `[DONE]`.
- Stream state is cleaned up on success, timeout, upstream error, and caller
  disconnect.
- Stream state is cleaned up when WebSocket send fails before any chunk is
  received.
- Non-streaming behavior from Plan 003 remains green.
- Final focused and broad test commands pass.
</success_criteria>
