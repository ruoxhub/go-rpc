# Phase 1: AI Chat Completions Stream - Research

## Existing System Findings

- The active server boot path is `pkg/server/bootstrap.go`.
- `Server.registerRoutes` currently registers embedded frontend routes,
  `/health`, `/business/*`, management routes, `/sekiro-api/*`, and a `NoRoute`
  fallback.
- `/business/invoke` enters `APIHandler.HandleInvoke`, which builds an
  `InvokeBuilder` and delegates to `handleForwardRequest`.
- `handleForwardRequest` is intentionally synchronous: select a client, send one
  WebSocket invoke message, wait for one `forwarder.InvokeResponse`, then write
  one JSON response through Gin.
- `websocket.Handler.handleInvokeResponse` currently completes a request by
  calling `TimeoutManager.Complete(sequence, response)`. That model cannot carry
  multiple streaming chunks without extension.
- The project already uses Gin and gorilla/websocket; no new dependency is
  required for SSE because Gin exposes `c.Stream`, `c.SSEvent`, and the response
  writer implements flushing in normal HTTP servers.

## External Compatibility Findings

- OpenAI's current Chat Completions API uses `POST /v1/chat/completions`.
- The `stream` field defaults to false; when true, response data is streamed
  using server-sent events.
- Chat completion stream chunks use a different object shape from non-streaming
  responses, so tests should distinguish `chat.completion` and
  `chat.completion.chunk`.
- `stream_options.include_usage` can emit an additional usage chunk before
  `[DONE]`; implementation can pass this through if the upstream Sekiro client
  already emits it.

Sources checked on 2026-04-27:
- `https://platform.openai.com/docs/api-reference/chat/create-chat-completion`
- `https://platform.openai.com/docs/api-reference/chat-streaming`
- `https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat`

## Planning Implications

- Implement chat completions as a new handler path rather than overloading
  `HandleInvoke`. It can share routing/auth helper methods while keeping the
  existing response contract stable.
- Introduce explicit streaming coordination instead of forcing stream chunks
  through `TimeoutManager.Wait`.
- Keep the WebSocket client protocol backward-compatible by adding fields or a
  new message type/action for streaming chunks, while leaving existing
  `invoke_response` behavior intact.
- Tests should not depend on PostgreSQL. Existing test style uses nil database
  fallback and in-memory mock client managers.

## Validation Architecture

- Unit tests for request parsing:
  - missing `group`
  - missing `model`
  - missing or empty `messages`
  - invalid JSON
  - `stream=false`
  - `stream=true`
- Unit tests for SSE formatting:
  - content type and cache headers
  - chunk lines prefixed with `data: `
  - final `[DONE]`
- WebSocket/forwarder tests for streaming lifecycle:
  - intermediate chunk does not close stream
  - final chunk closes stream
  - timeout and client disconnect cleanup records
- Regression tests:
  - existing `HandleInvoke` round-robin and invalid-connection tests still pass.

## Risks

- GitNexus MCP index for `sekiro-go` was unavailable in this session; impact
  analysis must be re-run once the repository is available in GitNexus.
- `http.Server.WriteTimeout` is currently 30 seconds in bootstrap config. Long
  AI streams may be cut off unless implementation explicitly accounts for this
  or makes timeout behavior configurable.
- Streaming through WebSocket requires a concrete client message contract. The
  current Go server cannot infer stream chunks unless clients send identifiable
  chunk/final messages.
