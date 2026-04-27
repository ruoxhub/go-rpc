---
phase: 1
plan: 2
type: feature
wave: 2
depends_on:
  - 000
  - 001
files_modified:
  - pkg/server/forwarder/timeout.go
  - pkg/server/forwarder/timeout_test.go
  - pkg/server/websocket/handler.go
  - pkg/server/websocket/handler_test.go
autonomous: true
requirements:
  - AI-CHAT-COMPLETIONS
must_haves:
  truths:
    - Streaming chunks are routed by `__sekiro_seq__` without affecting normal invoke responses.
    - Stream records are cleaned up on final chunk, error, timeout, and cancellation.
    - Existing `TimeoutManager.Complete` and `Wait` semantics remain unchanged for non-stream requests.
  artifacts:
    - `pkg/server/forwarder/timeout.go`
    - `pkg/server/websocket/handler.go`
  key_links:
    - `invoke_stream -> stream registry`
    - `invoke_response -> TimeoutManager.Complete`
---

# Plan 002: Streaming Transport Lifecycle

<objective>
Add the server-side stream registry and WebSocket message routing needed for
multiple chat completion chunks without regressing existing single-response
invokes.
</objective>

<implementation_contract>
- Fixed stream chunk message type: `invoke_stream`.
- Required correlation field: `__sekiro_seq__`.
- Chunk: `{"type":"invoke_stream","__sekiro_seq__":"...","data":{...},"done":false}`.
- Final: `{"type":"invoke_stream","__sekiro_seq__":"...","done":true}`.
- Error final: `{"type":"invoke_stream","__sekiro_seq__":"...","error":"...","status":-1,"done":true}`.
- Plain `invoke_response` keeps current one-shot completion behavior.
</implementation_contract>

<tasks>

<task type="tdd">
  <name>Specify stream registry behavior</name>
  <files>
    <file>pkg/server/forwarder/timeout_test.go</file>
  </files>
  <action>
    Add tests for stream registration, ordered chunk push, final completion,
    terminal error, timeout cleanup, remove cleanup, and coexistence with
    existing `Wait`/`Complete` behavior.
  </action>
  <verify>
    <automated>go test ./pkg/server/forwarder/... -run "TestStream|TestTimeoutManager"</automated>
  </verify>
  <done>
    Forwarder tests describe the full stream lifecycle and existing timeout
    manager regressions.
  </done>
</task>

<task type="auto">
  <name>Implement bounded stream registry</name>
  <files>
    <file>pkg/server/forwarder/timeout.go</file>
    <file>pkg/server/forwarder/timeout_test.go</file>
  </files>
  <action>
    Add stream registration, chunk push, complete, remove, and cleanup behavior
    with bounded channels. Keep existing `Add`, `Wait`, `Complete`, `Remove`,
    and cleanup semantics intact for non-stream requests.
  </action>
  <verify>
    <automated>go test ./pkg/server/forwarder/... -run "TestStream|TestTimeoutManager"</automated>
  </verify>
  <done>
    Stream registry tests and existing timeout manager tests pass together.
  </done>
</task>

<task type="auto">
  <name>Route invoke_stream WebSocket messages</name>
  <files>
    <file>pkg/server/websocket/handler.go</file>
    <file>pkg/server/websocket/handler_test.go</file>
  </files>
  <action>
    Add `MessageTypeInvokeStream`, parse `invoke_stream` messages, push chunks
    to the stream registry by `__sekiro_seq__`, and close streams on `done=true`
    or error. Preserve `invoke_response` routing through `TimeoutManager.Complete`.
  </action>
  <verify>
    <automated>go test ./pkg/server/websocket/... -run "TestInvokeStream|TestHandleInvokeResponse"</automated>
  </verify>
  <done>
    WebSocket tests prove stream chunks and normal invoke responses use separate
    paths and do not interfere.
  </done>
</task>

</tasks>

<verification>
<automated>go test ./pkg/server/forwarder/...</automated>
<automated>go test ./pkg/server/websocket/...</automated>
</verification>

<success_criteria>
- `invoke_stream` supports multiple chunks per request sequence.
- Final and error messages close and remove stream state.
- Existing `invoke_response` behavior remains unchanged.
</success_criteria>
