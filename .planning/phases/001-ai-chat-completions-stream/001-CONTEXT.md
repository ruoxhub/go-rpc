# Phase 1: AI Chat Completions Stream - Context

**Gathered:** 2026-04-27
**Status:** Ready for planning
**Source:** `$gsd-plan-phase pkg\server\bootstrap.go 扩展新的路由 "/v1/chat/completions" AI的流式接口请求`

<domain>
## Phase Boundary

Add an OpenAI-compatible `POST /v1/chat/completions` endpoint to the active
server bootstrap path. The endpoint should forward chat completion requests to
registered Sekiro clients and support streaming responses using
`text/event-stream` when the request asks for `stream: true`.

This phase plans the implementation only. It does not implement the route.
</domain>

<decisions>
## Implementation Decisions

### Route Scope
- Register `/v1/chat/completions` from `pkg/server/bootstrap.go` in
  `Server.registerRoutes`, because that is the active Gin route registration
  point.
- Keep the existing `/business/*`, `/sekiro-api/*`, and SPA fallback behavior
  unchanged.

### API Shape
- Accept OpenAI-style chat completion JSON bodies with `model`, `messages`,
  `stream`, and pass-through optional fields.
- Support `stream=false` or missing `stream` as a normal JSON response.
- Support `stream=true` as SSE with `Content-Type: text/event-stream`,
  `Cache-Control: no-cache`, and `X-Accel-Buffering: no`.
- Emit OpenAI-style `data: {...}\n\n` chunks and terminate with
  `data: [DONE]\n\n`.

### Forwarding Model
- Reuse the existing Sekiro client routing concepts: `group`, `clientId`,
  `constantInvoke`, token-based registered-group access, and health marking.
- Prefer adding a chat-specific handler/builder near `pkg/server/api` over
  modifying the existing `HandleInvoke` response format.
- Preserve current `handleForwardRequest` behavior for `/business/invoke`.

### Streaming Transport
- Current `forwarder.TimeoutManager` completes a request with one
  `InvokeResponse`; stream support needs a separate streaming path or an
  extension that can deliver multiple chunks without breaking existing waiters.
- WebSocket response parsing must distinguish intermediate chat stream chunks
  from final completion, and must clean up on client disconnect, timeout, or
  upstream error.

### the agent's Discretion
- Exact request fields used to select `group` can be query params, headers, or
  JSON extension fields, but implementation should document and test the chosen
  contract.
- Exact client-side streamed chunk envelope can be chosen during implementation,
  as long as it is backward-compatible for non-chat requests.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Server Bootstrap
- `pkg/server/bootstrap.go` - active Gin engine setup, middleware, route groups,
  NoRoute behavior, and `Server.registerRoutes`.

### Existing Forwarding Pipeline
- `pkg/server/api/handlers.go` - `APIHandler`, `HandleInvoke`,
  `handleForwardRequest`, routing, auth, timeout, metrics, and JSON response
  shape.
- `pkg/server/websocket/handler.go` - WebSocket message parsing,
  `SendInvokeRequest`, and invoke response completion.
- `pkg/server/forwarder/timeout.go` - current single-response timeout manager.
- `pkg/server/router/strategy.go` - client selection strategies.

### Tests
- `pkg/server/api/handlers_test.go` - API handler unit test style.
- `pkg/server/websocket/handler_test.go` - WebSocket message tests.
- `pkg/server/api/http_server_test.go` - HTTP server route test style.

### External API Compatibility
- `https://platform.openai.com/docs/api-reference/chat/create-chat-completion` -
  current Chat Completions endpoint shape and `stream` option.
- `https://platform.openai.com/docs/api-reference/chat-streaming` - current chat
  completion chunk object and streaming behavior.
- `https://platform.openai.com/docs/guides/streaming-responses?api-mode=chat` -
  server-sent event streaming guide.
</canonical_refs>

<specifics>
## Specific Ideas

- Route: `POST /v1/chat/completions`
- Stream request: `{"model":"...","messages":[...],"stream":true}`
- Non-stream request: same body with missing or false `stream`.
- Client action name should be stable, for example `_chat_completions`, so
  Sekiro clients can register a handler explicitly.
- The plan should include regression tests proving existing `/business/invoke`
  behavior remains unchanged.
</specifics>

<deferred>
## Deferred Ideas

- Full OpenAI API surface beyond chat completions.
- Frontend management UI for AI endpoint configuration.
- New external LLM SDK dependencies.
</deferred>

---

*Phase: 001-ai-chat-completions-stream*
*Context gathered: 2026-04-27 via fallback plan-phase path*
