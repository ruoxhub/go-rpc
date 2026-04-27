---
phase: 1
plan: 1
type: feature
wave: 1
depends_on:
  - 000
files_modified:
  - pkg/server/bootstrap.go
  - pkg/server/api/chat_completions.go
  - pkg/server/api/chat_completions_test.go
  - pkg/server/api/http_server_test.go
autonomous: true
requirements:
  - AI-CHAT-COMPLETIONS
must_haves:
  truths:
    - `POST /v1/chat/completions` is registered by the active server bootstrap.
    - Invalid chat completion requests fail before any WebSocket forwarding.
    - Existing API fallback behavior is preserved for `/business/*` and extended to `/v1/*`.
  artifacts:
    - `pkg/server/bootstrap.go`
    - `pkg/server/api/chat_completions.go`
    - `pkg/server/api/chat_completions_test.go`
  key_links:
    - `/v1/chat/completions -> APIHandler.HandleChatCompletions`
    - `/v1/* NoRoute -> JSON 404`
---

# Plan 001: Route and Chat Completion Contract

<objective>
Create the route and request/response contract for `POST /v1/chat/completions`
without implementing streaming transport internals.
</objective>

<implementation_contract>
- Apply `middleware.NewAuthMiddleware().OptionalAuth()` to `/v1`.
- Add `/v1/` to JSON API-prefix `NoRoute` handling.
- Accept `group`, `clientId`, `constantInvoke`, and `sekiro_token` from query
  params, with JSON extension fields as fallback.
- Require `model` and non-empty `messages`.
- Preserve unknown OpenAI request fields for downstream forwarding.
- Enforce `maxChatCompletionBodyBytes = 1 << 20` with `http.MaxBytesReader`.
- Change bootstrap HTTP `WriteTimeout` to `0`; later plans must enforce
  handler-level timeouts for stream safety.
</implementation_contract>

<tasks>

<task type="tdd">
  <name>Lock route and request parsing expectations</name>
  <files>
    <file>pkg/server/api/chat_completions_test.go</file>
    <file>pkg/server/api/http_server_test.go</file>
  </files>
  <action>
    Add failing tests for valid minimal request parsing, `stream` defaulting to
    false, unknown field preservation, invalid JSON, missing `model`, missing
    `messages`, oversized body, route registration, and `/v1/*` JSON 404.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionContract|TestChatCompletionsRoute|TestNoRoute"</automated>
  </verify>
  <done>
    Tests fail for the missing route/contract before implementation and describe
    the desired behavior precisely.
  </done>
</task>

<task type="auto">
  <name>Add chat completion contract helpers</name>
  <files>
    <file>pkg/server/api/chat_completions.go</file>
    <file>pkg/server/api/chat_completions_test.go</file>
  </files>
  <action>
    Implement request parsing and helper types for OpenAI-compatible
    `chat.completion` and `chat.completion.chunk` objects. Keep helpers local to
    `pkg/server/api`; do not add dependencies or call external LLM APIs.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionContract"</automated>
  </verify>
  <done>
    Contract tests pass, including body limit and unknown field preservation.
  </done>
</task>

<task type="auto">
  <name>Register /v1/chat/completions</name>
  <files>
    <file>pkg/server/bootstrap.go</file>
    <file>pkg/server/api/http_server_test.go</file>
  </files>
  <action>
    Add the `/v1` route group, attach optional auth middleware, register
    `POST /chat/completions`, extend `NoRoute` handling for `/v1/`, and set
    `WriteTimeout` to `0` in active HTTP config.
  </action>
  <verify>
    <automated>go test ./pkg/server/api/... -run "TestChatCompletionsRoute|TestNoRoute"</automated>
  </verify>
  <done>
    The active server route table reaches `HandleChatCompletions`, and unknown
    `/v1/*` requests do not serve the SPA.
  </done>
</task>

</tasks>

<verification>
<automated>go test ./pkg/server/api/...</automated>
</verification>

<success_criteria>
- Route is registered in `Server.registerRoutes`.
- Request contract helpers pass focused tests.
- `/v1/*` fallback behavior is API JSON, not frontend HTML.
- No new dependencies are introduced.
</success_criteria>
