# Roadmap

## Phase 1: AI Chat Completions Stream

**Goal:** Extend the active server route bootstrap with
`POST /v1/chat/completions` and plan an OpenAI-compatible chat completions
forwarding interface with streaming SSE support.

**Requirements:** AI-CHAT-COMPLETIONS

**Canonical refs:**
- `pkg/server/bootstrap.go`
- `pkg/server/api/handlers.go`
- `pkg/server/websocket/handler.go`
- `pkg/server/forwarder/timeout.go`

**Status:** Complete
