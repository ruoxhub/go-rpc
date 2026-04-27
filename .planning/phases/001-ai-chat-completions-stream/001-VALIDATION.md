---
phase: 1
artifact: validation
created: 2026-04-27
---

# Validation Strategy: AI Chat Completions Stream

## Dimensions

### 1. Route Registration

- `POST /v1/chat/completions` reaches `APIHandler.HandleChatCompletions`.
- Unknown `/v1/*` paths return JSON 404 instead of SPA fallback.
- Existing `/business/*` route behavior is unchanged.

### 2. Request Parsing

- Valid minimal request with `model`, `messages`, and omitted `stream`.
- Valid stream request with `stream=true`.
- Invalid JSON.
- Missing `model`.
- Missing or empty `messages`.
- Oversized body above `maxChatCompletionBodyBytes`.
- Unknown OpenAI fields such as `tools`, `tool_choice`, `metadata`, and
  `response_format` are preserved for forwarding.

### 3. Non-Streaming Forwarding

- Uses action `_chat_completions`.
- Selects target client using existing routing helpers.
- Enforces registered-group authorization.
- Returns upstream OpenAI-shaped JSON as-is where valid.
- Wraps simplified upstream content into `chat.completion`.
- Cleans timeout records on success, send failure, and timeout.

### 4. Streaming Forwarding

- Registers a stream before sending the WebSocket request.
- Uses fixed WebSocket envelope `type: "invoke_stream"`.
- Writes every chunk as `data: <json>\n\n`.
- Flushes after every chunk.
- Writes `data: [DONE]\n\n` once on normal completion.
- Cleans records on final chunk, error chunk, timeout, send failure, and caller
  cancellation.

### 5. Regression

- Existing `HandleInvoke` missing-group, round-robin, constantInvoke, and
  specified-client tests continue to pass.
- Existing WebSocket `invoke_response` tests continue to pass.
- Existing `TimeoutManager.Wait` and `Complete` behavior remains unchanged for
  non-stream requests.

### 6. Security

- Existing Sekiro token/group authorization protects registered groups.
- Prompt body, message content, authorization headers, and full chunks are not
  logged.
- Stream channels are bounded.
- Handler-level timeout is capped at 5 minutes after HTTP server WriteTimeout is
  set to 0 for SSE compatibility.

## Required Commands

```bash
go test ./pkg/server/api/...
go test ./pkg/server/websocket/...
go test ./pkg/server/forwarder/...
go test ./...
```

## Manual Smoke Test

```bash
curl -N -X POST "http://localhost:5612/v1/chat/completions?group=test-group" \
  -H "Authorization: Bearer <api_token>" \
  -H "Content-Type: application/json" \
  -d '{"model":"sekiro-client","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

Expected:
- Response header contains `text/event-stream`.
- At least one line starts with `data: {`.
- Final line is `data: [DONE]`.
