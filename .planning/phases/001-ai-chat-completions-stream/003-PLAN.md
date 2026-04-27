---
phase: 1
plan: 3
type: feature
wave: 3
depends_on:
  - 000
  - 001
  - 002
files_modified:
  - pkg/server/api/chat_completions.go
  - pkg/server/api/chat_completions_test.go
  - pkg/server/api/handlers.go
  - pkg/server/api/handlers_test.go
autonomous: true
requirements:
  - AI-CHAT-COMPLETIONS
must_haves:
  truths:
    - `stream=false` returns OpenAI-compatible JSON.
    - Existing `/business/invoke` behavior remains unchanged.
    - No new third-party dependencies are introduced.
  artifacts:
    - `pkg/server/api/chat_completions.go`
    - `pkg/server/api/handlers_test.go`
  key_links:
    - `HandleChatCompletions stream=false -> TimeoutManager.Wait`
---

# Plan 003: Non-Streaming Chat Completion Forwarding

<objective>
Wire the route contract into `APIHandler` so non-streaming OpenAI-compatible
chat completion calls work through Sekiro clients.
</objective>

<implementation_contract>
- Forward action name: `_chat_completions`.
- `stream=false`: wait for one upstream response and return OpenAI-compatible
  JSON.
- Handler timeout is capped by existing `maxInvokeTimeout` of 5 minutes.
- Logs must not include prompts, raw body, authorization headers, or full chunks.
</implementation_contract>

<tasks>

<task type="tdd">
  <name>Specify non-stream and stream API behavior</name>
  <files>
    <file>pkg/server/api/chat_completions_test.go</file>
    <file>pkg/server/api/handlers_test.go</file>
  </files>
  <action>
    Add tests for non-stream JSON forwarding, simplified content wrapping,
    timeout response, WebSocket send failure cleanup, registered-group auth,
    and `/business/invoke` regression.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletion|TestHandleInvoke"</automated>
  </verify>
  <done>
    API tests fail before implementation and cover non-stream behavior plus
    critical regressions, including timeout record cleanup after send failure.
  </done>
</task>

<task type="auto">
  <name>Implement non-streaming chat completion forwarding</name>
  <files>
    <file>pkg/server/api/chat_completions.go</file>
    <file>pkg/server/api/handlers.go</file>
  </files>
  <action>
    Implement `HandleChatCompletions` non-stream branch. Reuse existing routing,
    authorization, WebSocket send, timeout wait, and client health concepts.
    Return upstream OpenAI-shaped JSON as-is or wrap simplified content into
    `chat.completion`. If `SendInvokeRequest` fails, remove the timeout record
    before returning the error response and mark the target client failed.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionNonStream|TestHandleInvoke"</automated>
  </verify>
  <done>
    Non-streaming responses are JSON-compatible and existing invoke tests remain
    green. Send failure removes timeout records and does not leave waiters.
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
- Non-streaming requests return OpenAI-compatible JSON.
- WebSocket send failure removes the non-stream timeout record.
- Existing `/business/invoke` tests still pass.
- No new dependencies are introduced.
</success_criteria>
