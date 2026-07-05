package handler

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	json "github.com/goccy/go-json"

	"github.com/gin-gonic/gin"
	internalconfig "github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/internal/promptcompat"
	"github.com/mrh30000/go-rpc/internal/toolcall"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/mrh30000/go-rpc/pkg/model"
)

// dsmlOpener 是 promptcompat 强制约定的工具调用块起手标记。
// 流式输出在尾部至少扣住这么长再 emit，避免把工具调用前缀当成普通文本吐出去。
const dsmlOpener = "<|DSML|"

const maxChatCompletionBodyBytes = 1 << 20

// ChatCompletionRequest 是 sekiro chat completions handler 的请求视图。
//
// 它嵌入 model.ChatCompletionRequest（OpenAI 完整规范字段：Model / Messages /
// Stream / Tools / Metadata / ...），并补上 sekiro 私有的路由字段
// （Group / ClientID / ConstantInvoke）。
//
// Raw 保存原始 JSON map（用于诊断 / 日志），Params 是去掉 sekiro 私有字段
// 后透传到客户端的参数 map（用于 _chat_completions action）。
//
// 鉴权字段 (sekiro_token) 已删除: 鉴权由 AuthMiddleware 解析 Authorization
// 头并把 user 写入 context，本 handler 不再读取 body / query 中的 token。
type ChatCompletionRequest struct {
	model.ChatCompletionRequest

	Group          string                 `json:"group,omitempty"`
	ClientID       string                 `json:"clientId,omitempty"`
	ConstantInvoke string                 `json:"constantInvoke,omitempty"`
	Raw            map[string]interface{} `json:"-"`
	Params         map[string]interface{} `json:"-"`
	// ToolNames 由 promptcompat 规范化阶段产出，用于 toolcall 解析时识别合法工具。
	ToolNames []string `json:"-"`
	// ToolsRaw 是 OpenAI 请求里原始的 tools 数组，传给 toolcall.FormatOpenAI* 用于参数 schema 归一化。
	ToolsRaw any `json:"-"`
}

type configReader struct {
	requestedModel string
}

func (c configReader) ModelAliases() map[string]string {
	aliases := internalconfig.DefaultModelAliases()
	reqModel := strings.ToLower(strings.TrimSpace(c.requestedModel))
	if reqModel != "" {
		if _, ok := aliases[reqModel]; !ok && !internalconfig.IsSupportedDeepSeekModel(reqModel) {
			aliases[reqModel] = "deepseek-v4-flash"
		}
	}
	return aliases
}

// HandleChatCompletions 接收标准 OpenAI Chat Completions 请求体（不含 group/action/params），
// 内部固定路由到 group=qwenai、action=chatCompletions，把 messages/tools 经
// promptcompat 规范化后发到客户端，并按 stream 标志走流式或一次性应答。
func (h *APIHandler) HandleChatCompletions(c *gin.Context) {
	startTime := time.Now()

	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxChatCompletionBodyBytes)
	rawBody, err := io.ReadAll(c.Request.Body)
	if err != nil {
		writeChatError(c, http.StatusBadRequest, "read request body failed: "+err.Error())
		return
	}

	var rawMap map[string]interface{}
	if err := json.Unmarshal(rawBody, &rawMap); err != nil {
		writeChatError(c, http.StatusBadRequest, "invalid JSON request body: "+err.Error())
		return
	}

	var openAiReq model.ChatCompletionRequest
	if err := json.Unmarshal(rawBody, &openAiReq); err != nil {
		writeChatError(c, http.StatusBadRequest, "invalid OpenAI chat request: "+err.Error())
		return
	}

	if strings.TrimSpace(openAiReq.Model) == "" {
		writeChatError(c, http.StatusBadRequest, "model is required")
		return
	}
	if len(openAiReq.Messages) == 0 {
		writeChatError(c, http.StatusBadRequest, "messages is required")
		return
	}

	normalizedReq, err := promptcompat.NormalizeOpenAIChatRequest(configReader{requestedModel: openAiReq.Model}, rawMap, "")
	if err != nil {
		writeChatError(c, http.StatusBadRequest, err.Error())
		return
	}
	prompt := normalizedReq.FinalPrompt
	if prompt == "" {
		writeChatError(c, http.StatusBadRequest, "messages produced empty prompt")
		return
	}

	if !h.authorizeRegisteredGroupAccess(c, qwenGroup) {
		return
	}

	targetClient, err := h.selectTargetClient(qwenGroup, "", false, "", qwenActionChat, rawMap)
	if err != nil {
		writeChatError(c, http.StatusOK, err.Error())
		return
	}
	if targetClient == nil {
		writeChatError(c, http.StatusOK, "no client available")
		return
	}

	chatID, err := h.qwenCreateChat(c.Request.Context(), targetClient, openAiReq.Model)
	if err != nil {
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "createChat failed: "+err.Error())
		return
	}
	logger.Debugf("chat completions: chatId=%s, model=%s, group=%s, clientId=%s, stream=%v",
		chatID, openAiReq.Model, qwenGroup, targetClient.ClientID, openAiReq.Stream)

	chatReqParams := map[string]interface{}{
		"messages": prompt,
		"model":    openAiReq.Model,
		"chatId":   chatID,
	}
	reqDataJSON, err := json.Marshal(map[string]interface{}{
		"action": qwenActionChat,
		"params": chatReqParams,
	})
	if err != nil {
		writeChatError(c, http.StatusOK, "Failed to marshal request data: "+err.Error())
		return
	}

	sequence := fmt.Sprintf("%s-%s-%d", qwenGroup, qwenActionChat, time.Now().UnixNano())

	req := &ChatCompletionRequest{
		ChatCompletionRequest: openAiReq,
		Group:                 qwenGroup,
		Raw:                   rawMap,
		Params:                chatReqParams,
		ToolNames:             normalizedReq.ToolNames,
		ToolsRaw:              normalizedReq.ToolsRaw,
	}

	if openAiReq.Stream {
		h.handleChatCompletionStream(c, req, targetClient, sequence, reqDataJSON, maxInvokeTimeout, startTime)
		return
	}
	h.handleChatCompletionNonStream(c, req, targetClient, sequence, reqDataJSON, maxInvokeTimeout, startTime)
}

func (h *APIHandler) handleChatCompletionNonStream(c *gin.Context, req *ChatCompletionRequest, targetClient *client.RpcClient, sequence string, reqDataJSON []byte, timeout time.Duration, startTime time.Time) {
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, req.Group, targetClient.ClientID, reqDataJSON, ""); err != nil {
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "Failed to send request: "+err.Error())
		return
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	responseChan := make(chan *forwarder.InvokeResponse, 1)
	go func() {
		resp, err := h.timeoutManager.Wait(sequence)
		if err != nil {
			responseChan <- &forwarder.InvokeResponse{Error: err.Error(), Status: -1}
			return
		}
		responseChan <- resp
	}()

	select {
	case <-ctx.Done():
		h.timeoutManager.Remove(sequence)
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "Request timeout")
	case resp := <-responseChan:
		if resp.Status >= 0 && resp.Error == "" {
			targetClient.MarkSuccess()
		} else {
			targetClient.MarkFailure()
		}
		if resp.Error != "" {
			writeChatError(c, http.StatusOK, resp.Error)
			return
		}
		c.JSON(http.StatusOK, normalizeChatCompletionResponse(req, resp.Data, sequence, startTime))
	}
}

func (h *APIHandler) handleChatCompletionStream(c *gin.Context, req *ChatCompletionRequest, targetClient *client.RpcClient, sequence string, reqDataJSON []byte, timeout time.Duration, startTime time.Time) {
	stream := h.timeoutManager.RegisterStream(sequence, req.Group, targetClient.ClientID, timeout)
	defer h.timeoutManager.RemoveStream(sequence)

	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, req.Group, targetClient.ClientID, reqDataJSON, ""); err != nil {
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "Failed to send request: "+err.Error())
		return
	}

	WriteSSEHeaders(c)
	c.Writer.Flush()
	if err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Time{}); err != nil {
		logger.Debugf("Failed to clear SSE write deadline: %v", err)
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	holdback := newStreamHoldback("chatcmpl-" + sequence)
	parser := newQwenSSEParser()

	emit := func(delta map[string]interface{}, finishReason interface{}) {
		WriteSSEData(c, chatCompletionStreamFrame(holdback.chunkID, req.Model, startTime, delta, finishReason))
	}
	onFinal := func(reason string) {
		emit(map[string]interface{}{}, reason)
		WriteSSEDone(c)
	}
	finalize := func() {
		holdback.finalizeAndEmit(emit, req.ToolNames, req.ToolsRaw, onFinal)
	}

	for {
		select {
		case <-ctx.Done():
			targetClient.MarkFailure()
			emit(map[string]interface{}{}, "error")
			WriteSSEDone(c)
			return
		case chunk, ok := <-stream.ChunkChan:
			if !ok {
				if errMsg := stream.TerminalError(); errMsg != "" {
					targetClient.MarkFailure()
					WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, req.Model, startTime, errMsg))
					if !holdback.finished {
						WriteSSEDone(c)
					}
					return
				}
				finalize()
				targetClient.MarkSuccess()
				return
			}
			if chunk.Error != "" {
				targetClient.MarkFailure()
				WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, req.Model, startTime, chunk.Error))
				WriteSSEDone(c)
				return
			}
			text, err := decodeStreamChunkText(chunk.Data)
			if err != nil {
				logger.Warnf("chat completions decode chunk: %v", err)
				continue
			}
			if text == "" && !chunk.Done {
				continue
			}
			for _, ev := range parser.Feed(text) {
				holdback.adoptResponseID(ev.ResponseID)
				if ev.Done {
					finalize()
					targetClient.MarkSuccess()
					return
				}
				if ev.Error != "" {
					targetClient.MarkFailure()
					WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, req.Model, startTime, ev.Error))
					WriteSSEDone(c)
					return
				}
				if ev.Finished {
					finalize()
					targetClient.MarkSuccess()
					return
				}
				if ev.Content == "" && ev.Role == "" {
					continue
				}
				if ev.Phase == "thinking" {
					// Chain-of-Thought 段不参与工具调用解析，立即透传。
					holdback.flushThinking(emit, ev.Role, ev.Content)
					continue
				}
				holdback.appendAnswer(ev.Content)
				holdback.flushSafeContent(emit)
			}
			if chunk.Done {
				finalize()
				targetClient.MarkSuccess()
				return
			}
		}
	}
}

// chatCompletionStreamFrame 构造 deepseek 风格的 chat.completion.chunk 帧。
// 与 completions_response.txt 样例对齐:
//   - delta 始终包含 role / content / tool_calls / function_calls / reasoning_content
//   - choices[0] 额外带一份占位 message 对象 (字段全 null/"")
//   - 顶层带 system_fingerprint 和 usage 占位
func chatCompletionStreamFrame(id, model string, startTime time.Time, delta map[string]interface{}, finishReason interface{}) map[string]interface{} {
	fullDelta := map[string]interface{}{
		"role":              nil,
		"content":           "",
		"tool_calls":        nil,
		"function_calls":    nil,
		"reasoning_content": "",
	}
	for k, v := range delta {
		fullDelta[k] = v
	}
	return map[string]interface{}{
		"id":                 id,
		"object":             "chat.completion.chunk",
		"created":            startTime.Unix(),
		"model":              model,
		"system_fingerprint": "",
		"choices": []map[string]interface{}{
			{
				"index":         0,
				"delta":         fullDelta,
				"finish_reason": finishReason,
				"message": map[string]interface{}{
					"role":              nil,
					"content":           "",
					"tool_calls":        nil,
					"function_calls":    nil,
					"reasoning_content": "",
				},
			},
		},
		"usage": map[string]interface{}{
			"prompt_tokens":     0,
			"completion_tokens": 0,
			"total_tokens":      0,
		},
	}
}

func normalizeChatCompletionResponse(req *ChatCompletionRequest, data []byte, sequence string, startTime time.Time) interface{} {
	fallbackID := "chatcmpl-" + sequence
	var raw interface{}
	if err := json.Unmarshal(data, &raw); err == nil {
		if rawMap, ok := raw.(map[string]interface{}); ok {
			if object, _ := rawMap["object"].(string); object == "chat.completion" {
				return rawMap
			}
			respID, _ := rawMap["response_id"].(string)
			id := fallbackID
			if respID != "" {
				id = respID
			}
			if content, ok := rawMap["content"]; ok {
				if s, isStr := content.(string); isStr {
					if resp, hit := buildOpenAIToolCallResponse(id, req.Model, s, startTime, req.ToolNames, req.ToolsRaw); hit {
						return resp
					}
				}
				return buildOpenAIChatResponse(id, req.Model, startTime, content)
			}
		}
		return raw
	}
	if resp, hit := buildOpenAIToolCallResponse(fallbackID, req.Model, string(data), startTime, req.ToolNames, req.ToolsRaw); hit {
		return resp
	}
	return buildOpenAIChatResponse(fallbackID, req.Model, startTime, string(data))
}

// buildOpenAIToolCallResponse checks content for DSML tool call blocks and wraps
// them in a chat.completion with tool_calls. Shared across chat_completions and qwen paths.
// Returns (nil, false) if no tool calls are found.
func buildOpenAIToolCallResponse(id, model, content string, startTime time.Time, toolNames []string, toolsRaw any) (map[string]interface{}, bool) {
	parsed := toolcall.ParseToolCallsDetailed(content, toolNames)
	if len(parsed.Calls) == 0 {
		return nil, false
	}
	head := strings.Index(content, dsmlOpener)
	if head < 0 {
		head = len(content)
	}
	tcs := toolcall.FormatOpenAIToolCalls(parsed.Calls, toolsRaw)
	return map[string]interface{}{
		"id":      id,
		"object":  "chat.completion",
		"created": startTime.Unix(),
		"model":   model,
		"choices": []map[string]interface{}{
			{
				"index": 0,
				"message": map[string]interface{}{
					"role":       "assistant",
					"content":    content[:head],
					"tool_calls": tcs,
				},
				"finish_reason": "tool_calls",
			},
		},
	}, true
}

func normalizeChatCompletionChunk(req *ChatCompletionRequest, data []byte, sequence string, startTime time.Time) interface{} {
	var raw interface{}
	if err := json.Unmarshal(data, &raw); err == nil {
		if rawMap, ok := raw.(map[string]interface{}); ok {
			if object, _ := rawMap["object"].(string); object == "chat.completion.chunk" {
				return rawMap
			}
			if delta, ok := rawMap["delta"]; ok {
				return chatCompletionChunk(req, sequence, delta, rawMap["finish_reason"], startTime)
			}
			if content, ok := rawMap["content"]; ok {
				return chatCompletionChunk(req, sequence, content, rawMap["finish_reason"], startTime)
			}
		}
	}
	return chatCompletionChunk(req, sequence, string(data), nil, startTime)
}

// buildOpenAIErrorChunk constructs a chat.completion.chunk error frame.
// Shared across chat_completions and qwen paths.
func buildOpenAIErrorChunk(id, model string, startTime time.Time, message string) map[string]interface{} {
	return map[string]interface{}{
		"id":      id,
		"object":  "chat.completion.chunk",
		"created": startTime.Unix(),
		"model":   model,
		"choices": []map[string]interface{}{
			{
				"index":         0,
				"delta":         map[string]interface{}{},
				"finish_reason": "error",
			},
		},
		"error": map[string]interface{}{
			"message": message,
			"type":    "sekiro_error",
		},
	}
}

// buildOpenAIChatResponse constructs a standard chat.completion response.
// Shared across chat_completions and qwen paths.
func buildOpenAIChatResponse(id, model string, startTime time.Time, content interface{}) map[string]interface{} {
	return map[string]interface{}{
		"id":      id,
		"object":  "chat.completion",
		"created": startTime.Unix(),
		"model":   model,
		"choices": []map[string]interface{}{
			{
				"index": 0,
				"message": map[string]interface{}{
					"role":    "assistant",
					"content": content,
				},
				"finish_reason": "stop",
			},
		},
	}
}

func chatCompletionChunk(req *ChatCompletionRequest, sequence string, delta interface{}, finishReason interface{}, startTime time.Time) map[string]interface{} {
	deltaPayload, ok := delta.(map[string]interface{})
	if !ok {
		deltaPayload = map[string]interface{}{
			"content": delta,
		}
	}
	return map[string]interface{}{
		"id":      "chatcmpl-" + sequence,
		"object":  "chat.completion.chunk",
		"created": startTime.Unix(),
		"model":   req.Model,
		"choices": []map[string]interface{}{
			{
				"index":         0,
				"delta":         deltaPayload,
				"finish_reason": finishReason,
			},
		},
	}
}

func writeChatError(c *gin.Context, statusCode int, message string) {
	c.JSON(statusCode, gin.H{
		"error": gin.H{
			"message": message,
			"type":    "sekiro_error",
		},
	})
}

func boolFromRaw(value interface{}) bool {
	switch v := value.(type) {
	case bool:
		return v
	case string:
		parsed, err := strconv.ParseBool(v)
		return err == nil && parsed
	default:
		return false
	}
}

func stringFromRaw(value interface{}) string {
	if str, ok := value.(string); ok {
		return str
	}
	return ""
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

// RequestBuilder implementation for *ChatCompletionRequest

func (r *ChatCompletionRequest) BuildRequestData() (string, interface{}, error) {
	return qwenActionChat, r.Params, nil
}

func (r *ChatCompletionRequest) GetTimeout() time.Duration {
	return maxInvokeTimeout
}

func (r *ChatCompletionRequest) GetSequence(group string) string {
	return fmt.Sprintf("%s-%s-%d", group, qwenActionChat, time.Now().UnixNano())
}

func (r *ChatCompletionRequest) ShouldRecordMetrics() bool {
	return true
}

func (r *ChatCompletionRequest) GetMetricAPI(action string) string {
	return action
}

func (r *ChatCompletionRequest) GetGroup() string {
	return r.Group
}

func (r *ChatCompletionRequest) GetClientID() string {
	return r.ClientID
}

func (r *ChatCompletionRequest) GetConstantInvoke() string {
	return r.ConstantInvoke
}

func (r *ChatCompletionRequest) IsStream() bool {
	return r.Stream
}

func (r *ChatCompletionRequest) IsFuzzy() bool { return false }
