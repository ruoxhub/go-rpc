# Requirements

## AI-CHAT-COMPLETIONS

The server must expose `POST /v1/chat/completions` from the active Gin server
bootstrap and forward OpenAI-compatible chat completion requests to Sekiro
clients.

Acceptance criteria:
- `stream=false` or omitted `stream` returns JSON compatible with a chat
  completion response.
- `stream=true` returns `text/event-stream` chunks and terminates with
  `data: [DONE]`.
- Existing `/business/invoke` behavior is preserved.
- Existing Sekiro group/client routing and registered-group authorization are
  reused.
- No new third-party dependencies are introduced.
