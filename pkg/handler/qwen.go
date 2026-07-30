// Package api - qwen.go provides an OpenAI-compatible Chat Completions endpoint
// that forwards requests to a connected qwenai browser-extension client over the
// existing Rpc invoke/invoke_stream channel.
//
// 调用流程:
//
//	client → POST /api/chat/completions  (OpenAI 格式, stream=true)
//	     → messages 拼成 prompt
//	     → 选 qwenai 分组的浏览器客户端
//	     → invoke createChat (action="createChat")  拿 chat_id
//	     → invoke_stream chatCompletions (action="chatCompletions")  拿 SSE
//	     → 解析 qwen SSE chunk → 转 OpenAI chat.completion.chunk → 写回
package handler

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	json "github.com/goccy/go-json"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
)

const (
	qwenGroup            = "qwenai"
	qwenActionCreateChat = "createChat"
	qwenActionChat       = "chatCompletions"
	qwenStreamTimeout    = 5 * time.Minute
	qwenUnaryTimeout     = 30 * time.Second
)

// HandleQwenChatCompletions implements POST /api/chat/completions for the
// qwenai browser-extension provider.
//
// Input is the standard OpenAI Chat Completions JSON body. We always stream
// back to the caller (text/event-stream) regardless of the upstream "stream"
// flag — non-stream callers can still aggregate the chunks themselves.
func (h *APIHandler) HandleQwenChatCompletions(c *gin.Context) {
	startTime := time.Now()

	body, err := readJSONBody(c, maxChatCompletionBodyBytes)
	if err != nil {
		writeChatError(c, http.StatusBadRequest, err.Error())
		return
	}

	model, _ := body["model"].(string)
	if strings.TrimSpace(model) == "" {
		writeChatError(c, http.StatusBadRequest, "model is required")
		return
	}

	messagesRaw, ok := body["messages"].([]interface{})
	if !ok || len(messagesRaw) == 0 {
		writeChatError(c, http.StatusBadRequest, "messages is required")
		return
	}

	prompt, err := flattenMessagesToPrompt(messagesRaw)
	if err != nil {
		writeChatError(c, http.StatusBadRequest, err.Error())
		return
	}
	if prompt == "" {
		writeChatError(c, http.StatusBadRequest, "messages produced empty prompt")
		return
	}

	clientID := firstNonEmpty(c.Query("clientId"), stringFromRaw(body["clientId"]))
	constantInvoke := firstNonEmpty(c.Query("constantInvoke"), stringFromRaw(body["constantInvoke"]))
	streamWanted := boolFromRaw(body["stream"]) || parseBoolQuery(c.Query("stream"))

	toolsRaw := body["tools"]
	toolNames := extractToolNames(toolsRaw)

	if !h.authorizeRegisteredGroupAccess(c, qwenGroup) {
		return
	}

	targetClient, err := h.selectTargetClient(qwenGroup, clientID, false, constantInvoke, qwenActionChat, nil)
	if err != nil {
		writeChatError(c, http.StatusOK, err.Error())
		return
	}
	if targetClient == nil {
		writeChatError(c, http.StatusOK, "no qwenai client available")
		return
	}

	chatID, err := h.qwenCreateChat(c.Request.Context(), targetClient, model)
	if err != nil {
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "createChat failed: "+err.Error())
		return
	}
	logger.Debugf("qwen chat created: chatId=%s, model=%s, group=%s, clientId=%s", chatID, model, qwenGroup, targetClient.ClientID)

	chatReqParams := map[string]interface{}{
		"messages": prompt,
		"model":    model,
		"chatId":   chatID,
	}
	chatSeq := fmt.Sprintf("%s-%s-%d", qwenGroup, qwenActionChat, time.Now().UnixNano())
	chatReqJSON, err := json.Marshal(map[string]interface{}{
		"action": qwenActionChat,
		"params": chatReqParams,
	})
	if err != nil {
		writeChatError(c, http.StatusOK, "marshal chat request failed: "+err.Error())
		return
	}

	if streamWanted {
		h.qwenStreamToOpenAI(c, targetClient, chatSeq, chatReqJSON, model, startTime, toolNames, toolsRaw)
	} else {
		h.qwenAggregateToOpenAI(c, targetClient, chatSeq, chatReqJSON, model, startTime, toolNames, toolsRaw)
	}
}

// extractToolNames 从 OpenAI 风格 tools 数组里抽出工具名称。
// tools 形如 [{"type":"function","function":{"name":"webfetch", ...}}, ...]
func extractToolNames(toolsRaw any) []string {
	arr, ok := toolsRaw.([]any)
	if !ok {
		return nil
	}
	names := make([]string, 0, len(arr))
	for _, item := range arr {
		m, ok := item.(map[string]any)
		if !ok {
			continue
		}
		if fn, ok := m["function"].(map[string]any); ok {
			if name, ok := fn["name"].(string); ok && name != "" {
				names = append(names, name)
			}
		}
	}
	return names
}

// qwenCreateChat invokes the qwenai client's createChat action and returns the
// upstream chat_id. The returned id is used as chatId for the subsequent
// streaming chatCompletions invocation.
func (h *APIHandler) qwenCreateChat(ctx context.Context, target *client.RpcClient, model string) (string, error) {
	seq := fmt.Sprintf("%s-%s-%d", qwenGroup, qwenActionCreateChat, time.Now().UnixNano())
	reqJSON, err := json.Marshal(map[string]interface{}{
		"action": qwenActionCreateChat,
		"params": map[string]interface{}{"modelId": model},
	})
	if err != nil {
		return "", fmt.Errorf("marshal createChat request: %w", err)
	}

	resp, err := h.waitUnaryInvoke(ctx, qwenGroup, target, seq, reqJSON, qwenUnaryTimeout, "")
	if err != nil {
		return "", fmt.Errorf("createChat: %w", err)
	}
	if resp.Error != "" {
		return "", errors.New(resp.Error)
	}
	return extractQwenChatID(resp.Data)
}

// extractQwenChatID parses createChat response payload and pulls the chat id
// out of common upstream shapes.
//
// 已观察到的形态:
//   - {"chat":{"id":"<uuid>"}, ...}
//   - {"data":{"id":"<uuid>"}, ...}
//   - {"id":"<uuid>", ...}
//   - 服务端聚合后的 invoke 包络:
//     {"clientId":"...", "group":"...", "data":{"id":"<uuid>"},
//     "message":"success", "request_id":"...", "status":0, "success":true}
//     当 success=false 时，把 message 作为错误返回。
func extractQwenChatID(data []byte) (string, error) {
	if len(data) == 0 {
		return "", errors.New("empty createChat response")
	}
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		return "", fmt.Errorf("createChat response not JSON: %w", err)
	}

	// 包络层错误：success=false 时直接把 message 透出，避免被
	// 后续 "missing chat id" 兜底信息掩盖真实失败原因。
	if success, ok := raw["success"].(bool); ok && !success {
		if msg := pickString(raw, "message"); msg != "" {
			return "", fmt.Errorf("createChat failed: %s", msg)
		}
		return "", fmt.Errorf("createChat failed: %s", string(data))
	}

	if id := pickString(raw, "id"); id != "" {
		return id, nil
	}
	if chat, ok := raw["chat"].(map[string]interface{}); ok {
		if id := pickString(chat, "id"); id != "" {
			return id, nil
		}
	}
	if d, ok := raw["data"].(map[string]interface{}); ok {
		if id := pickString(d, "id"); id != "" {
			return id, nil
		}
		if chat, ok := d["chat"].(map[string]interface{}); ok {
			if id := pickString(chat, "id"); id != "" {
				return id, nil
			}
		}
	}
	return "", fmt.Errorf("createChat response missing chat id: %s", string(data))
}

func pickString(m map[string]interface{}, key string) string {
	if v, ok := m[key]; ok {
		if s, ok := v.(string); ok && s != "" {
			return s
		}
	}
	return ""
}

// qwenStreamToOpenAI consumes the qwenai invoke_stream chunks, parses each as a
// fragment of qwen-style SSE, and re-emits OpenAI chat.completion.chunk frames
// over text/event-stream.
//
// 关键点:
//  1. BaseClient 把上游 SSE 字节按 chunk 编码成 JSON 字符串字面量塞进
//     invoke_stream.data — 服务端这里 chunk.Data 就是 RawMessage，需要
//     json.Unmarshal 到 string 才能拿到 SSE 文本。
//  2. SSE 文本可能跨 invoke_stream 帧切分，必须用 buffer 累积按 \n\n 切分事件。
//  3. 每条 qwen event 形如 `data: {choices:[{delta:{content,phase,status}}]}` 或
//     `data: [DONE]`；status === "finished" 也表示流终止。
func (h *APIHandler) qwenStreamToOpenAI(
	c *gin.Context,
	target *client.RpcClient,
	seq string,
	reqJSON []byte,
	model string,
	startTime time.Time,
	toolNames []string,
	toolsRaw any,
) {
	stream := h.timeoutManager.RegisterStream(seq, qwenGroup, target.ClientID, qwenStreamTimeout)
	defer h.timeoutManager.RemoveStream(seq)

	if err := h.wsHandler.SendInvokeRequest(target, seq, qwenGroup, target.ClientID, reqJSON, ""); err != nil {
		target.MarkFailure()
		writeChatError(c, http.StatusOK, "Failed to send chatCompletions: "+err.Error())
		return
	}

	h.driveOpenAIChatStream(
		c, stream, target, qwenStreamTimeout, model, startTime,
		toolNames, toolsRaw, "chatcmpl-"+seq,
		func(chunkID string, delta map[string]interface{}, finishReason interface{}) {
			WriteSSEData(c, map[string]interface{}{
				"id":      chunkID,
				"object":  "chat.completion.chunk",
				"created": startTime.Unix(),
				"model":   model,
				"choices": []map[string]interface{}{
					{
						"index":         0,
						"delta":         delta,
						"finish_reason": finishReason,
					},
				},
			})
		},
	)
}

// qwenAggregateToOpenAI handles the non-stream branch. It runs the same
// invoke_stream pipeline but aggregates content into a single chat.completion
// JSON response.
func (h *APIHandler) qwenAggregateToOpenAI(
	c *gin.Context,
	target *client.RpcClient,
	seq string,
	reqJSON []byte,
	model string,
	startTime time.Time,
	toolNames []string,
	toolsRaw any,
) {
	stream := h.timeoutManager.RegisterStream(seq, qwenGroup, target.ClientID, qwenStreamTimeout)
	defer h.timeoutManager.RemoveStream(seq)

	if err := h.wsHandler.SendInvokeRequest(target, seq, qwenGroup, target.ClientID, reqJSON, ""); err != nil {
		target.MarkFailure()
		writeChatError(c, http.StatusOK, "Failed to send chatCompletions: "+err.Error())
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), qwenStreamTimeout)
	defer cancel()

	parser := newQwenSSEParser()
	var builder strings.Builder
	// chatID 优先用上游 response_id，找到前先用本地 sequence 兜底。
	chatID := "chatcmpl-" + seq
	idAdopted := false
	adoptResponseID := func(id string) {
		if id == "" || idAdopted {
			return
		}
		chatID = id
		idAdopted = true
	}

	emitFinal := func() {
		full := builder.String()
		if resp, hit := buildOpenAIToolCallResponse(chatID, model, full, startTime, toolNames, toolsRaw); hit {
			c.JSON(http.StatusOK, resp)
			return
		}
		c.JSON(http.StatusOK, buildOpenAIChatResponse(chatID, model, startTime, full))
	}

	for {
		select {
		case <-ctx.Done():
			target.MarkFailure()
			writeChatError(c, http.StatusOK, "request timeout")
			return
		case chunk, ok := <-stream.ChunkChan:
			if !ok {
				if errMsg := stream.TerminalError(); errMsg != "" {
					target.MarkFailure()
					writeChatError(c, http.StatusOK, errMsg)
					return
				}
				target.MarkSuccess()
				emitFinal()
				return
			}
			if chunk.Error != "" {
				target.MarkFailure()
				writeChatError(c, http.StatusOK, chunk.Error)
				return
			}
			text, err := decodeStreamChunkText(chunk.Data)
			if err != nil {
				logger.Warnf("qwen aggregate decode chunk: %v", err)
				continue
			}
			events := parser.Feed(text)
			for _, ev := range events {
				adoptResponseID(ev.ResponseID)
				if ev.Error != "" {
					target.MarkFailure()
					writeChatError(c, http.StatusOK, ev.Error)
					return
				}
				if ev.Content != "" && ev.Phase != "thinking" {
					builder.WriteString(ev.Content)
				}
				if ev.Done || ev.Finished {
					target.MarkSuccess()
					emitFinal()
					return
				}
			}
			if chunk.Done {
				target.MarkSuccess()
				emitFinal()
				return
			}
		}
	}
}

// decodeStreamChunkText converts a forwarder.StreamChunk.Data RawMessage into
// the SSE text the upstream extension wrote. BaseClient sends the chunk text
// as a JSON string literal, so we first try Unmarshal-into-string; if that
// fails we fall back to the raw bytes.
func decodeStreamChunkText(raw []byte) (string, error) {
	if len(raw) == 0 {
		return "", nil
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return s, nil
	}
	return string(raw), nil
}

// readJSONBody reads up to maxBytes bytes from c.Request.Body and decodes it
// as a generic JSON object.
func readJSONBody(c *gin.Context, maxBytes int64) (map[string]interface{}, error) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxBytes)
	var raw map[string]interface{}
	dec := json.NewDecoder(c.Request.Body)
	if err := dec.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON request body: %w", err)
	}
	return raw, nil
}

// flattenMessagesToPrompt converts a list of OpenAI ChatMessage maps to a
// single textual prompt the qwenai web client can submit through its
// chatCompletions hook (which only accepts a single user message string).
//
// 实现策略:
//   - system / user / assistant / tool 消息按 "Role: content" 行序列化
//   - content 是数组（multi-modal）时只取 type=text 的 text 字段
//   - 其它角色被忽略
//   - 末尾追加 "Assistant:" 前缀以引导回答
func flattenMessagesToPrompt(messagesRaw []interface{}) (string, error) {
	var b strings.Builder
	for _, item := range messagesRaw {
		msg, ok := item.(map[string]interface{})
		if !ok {
			return "", errors.New("messages must contain objects")
		}
		role, _ := msg["role"].(string)
		role = strings.TrimSpace(role)
		if role == "" {
			role = "user"
		}
		text := messageContentText(msg["content"])
		if text == "" {
			continue
		}
		label := titleCase(role)
		b.WriteString(label)
		b.WriteString(": ")
		b.WriteString(text)
		b.WriteString("\n\n")
	}
	if b.Len() == 0 {
		return "", nil
	}
	b.WriteString("Assistant: ")
	return b.String(), nil
}

func messageContentText(v interface{}) string {
	switch c := v.(type) {
	case string:
		return c
	case []interface{}:
		var b strings.Builder
		for _, part := range c {
			pm, ok := part.(map[string]interface{})
			if !ok {
				continue
			}
			t, _ := pm["type"].(string)
			if t == "" || t == "text" {
				if s, ok := pm["text"].(string); ok {
					b.WriteString(s)
				}
			}
		}
		return b.String()
	case map[string]interface{}:
		if s, ok := c["text"].(string); ok {
			return s
		}
		return ""
	default:
		return ""
	}
}

// ---------------------------------------------------------------------------
// qwen SSE parser
// ---------------------------------------------------------------------------

// qwenSSEEvent represents one parsed qwen event, with content/role flattened
// out of the upstream {choices:[{delta:{...}}]} envelope.
//
// Phase is the qwen-specific stream phase (typically "answer" or "thinking").
// We surface it so reasoning models can route Chain-of-Thought output to the
// OpenAI `reasoning_content` field instead of leaking it as user-visible text.
type qwenSSEEvent struct {
	Role       string
	Content    string
	Phase      string // qwen phase: "answer" / "thinking" / ""
	Finished   bool   // upstream signaled status="finished"
	Done       bool   // upstream sent "data: [DONE]"
	Error      string // upstream-level error
	ResponseID string // upstream "response_id"，存在时用作 chat.completion id
}

// qwenSSEParser accumulates partial SSE text across invoke_stream chunks and
// emits whole events once \n\n delimiters arrive.
type qwenSSEParser struct {
	buf strings.Builder
}

func newQwenSSEParser() *qwenSSEParser { return &qwenSSEParser{} }

// Feed appends the new SSE text and returns any whole events that became
// available. Partial trailing data stays in the buffer for the next call.
func (p *qwenSSEParser) Feed(text string) []qwenSSEEvent {
	if text == "" {
		return nil
	}
	p.buf.WriteString(text)
	combined := p.buf.String()
	// Normalize CRLF so the \n\n boundary works regardless of upstream encoding.
	combined = strings.ReplaceAll(combined, "\r\n", "\n")

	parts := strings.Split(combined, "\n\n")
	// Last element is unfinished if no trailing "\n\n" was seen.
	tail := parts[len(parts)-1]
	parts = parts[:len(parts)-1]

	p.buf.Reset()
	p.buf.WriteString(tail)

	out := make([]qwenSSEEvent, 0, len(parts))
	for _, raw := range parts {
		ev, ok := parseQwenSSEBlock(raw)
		if !ok {
			continue
		}
		out = append(out, ev)
	}
	return out
}

// parseQwenSSEBlock parses one SSE event block (everything between two \n\n
// boundaries). Supports multi-line "data:" continuation per the SSE spec.
func parseQwenSSEBlock(block string) (qwenSSEEvent, bool) {
	block = strings.TrimSpace(block)
	if block == "" {
		return qwenSSEEvent{}, false
	}
	var dataLines []string
	for _, line := range strings.Split(block, "\n") {
		line = strings.TrimRight(line, "\r")
		if strings.HasPrefix(line, ":") {
			// SSE comment / heartbeat
			continue
		}
		if strings.HasPrefix(line, "data:") {
			dataLines = append(dataLines, strings.TrimSpace(line[len("data:"):]))
		}
	}
	if len(dataLines) == 0 {
		return qwenSSEEvent{}, false
	}
	data := strings.Join(dataLines, "\n")
	if data == "" {
		return qwenSSEEvent{}, false
	}
	if data == "[DONE]" {
		return qwenSSEEvent{Done: true}, true
	}

	var raw map[string]interface{}
	if err := json.Unmarshal([]byte(data), &raw); err != nil {
		// Tolerate malformed frames (heartbeats, partial JSON) by emitting nothing.
		return qwenSSEEvent{}, false
	}

	if errVal, ok := raw["error"]; ok {
		if msg := errorMessage(errVal); msg != "" {
			return qwenSSEEvent{Error: msg}, true
		}
	}

	// 顶层 response_id 在多种帧（response.created / delta / finished）里都可能出现，
	// 任意非空值都先收下，调用方按"首次见到即采纳"处理。
	respID, _ := raw["response_id"].(string)

	choices, _ := raw["choices"].([]interface{})
	if len(choices) == 0 {
		// 非 choices 帧（response.created / response.in_progress 等）跳过即可，
		// 但 response_id 仍要透出。
		if respID != "" {
			return qwenSSEEvent{ResponseID: respID}, true
		}
		return qwenSSEEvent{}, false
	}
	first, _ := choices[0].(map[string]interface{})
	if first == nil {
		if respID != "" {
			return qwenSSEEvent{ResponseID: respID}, true
		}
		return qwenSSEEvent{}, false
	}
	delta, _ := first["delta"].(map[string]interface{})
	if delta == nil {
		if respID != "" {
			return qwenSSEEvent{ResponseID: respID}, true
		}
		return qwenSSEEvent{}, false
	}

	ev := qwenSSEEvent{ResponseID: respID}
	if r, ok := delta["role"].(string); ok {
		ev.Role = r
	}
	if c, ok := delta["content"].(string); ok {
		ev.Content = c
	}
	if phase, ok := delta["phase"].(string); ok {
		ev.Phase = phase
	}
	if status, ok := delta["status"].(string); ok && status == "finished" {
		ev.Finished = true
	}
	if fr, ok := first["finish_reason"].(string); ok && fr != "" {
		ev.Finished = true
	}
	return ev, true
}

func errorMessage(v interface{}) string {
	switch x := v.(type) {
	case string:
		return x
	case map[string]interface{}:
		if s, ok := x["message"].(string); ok {
			return s
		}
		if s, ok := x["error"].(string); ok {
			return s
		}
	}
	return ""
}

// titleCase upper-cases the first ASCII letter of role labels for the rendered
// prompt. Replacement for strings.Title (deprecated since Go 1.18). The role
// values we care about — "system", "user", "assistant", "tool", "function" —
// are pure ASCII, so a one-byte shift is sufficient.
func titleCase(s string) string {
	if s == "" {
		return s
	}
	c := s[0]
	if c >= 'a' && c <= 'z' {
		return string(c-('a'-'A')) + s[1:]
	}
	return s
}
