package api

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
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

const (
	chatCompletionGroup        = "qwenai"
	chatCompletionAction       = "chatCompletions"
	maxChatCompletionBodyBytes = 1 << 20
)

// ChatCompletionRequest 是 sekiro chat completions handler 的请求视图。
//
// 它嵌入 model.ChatCompletionRequest（OpenAI 完整规范字段：Model / Messages /
// Stream / Tools / Metadata / ...），并补上 sekiro 私有的路由 / 鉴权字段
// （Group / ClientID / ConstantInvoke / RpcToken）。
//
// Raw 保存原始 JSON map（用于诊断 / 日志），Params 是去掉 sekiro 私有字段
// 后透传到客户端的参数 map（用于 _chat_completions action）。
type ChatCompletionRequest struct {
	model.ChatCompletionRequest

	Group          string                 `json:"group,omitempty"`
	ClientID       string                 `json:"clientId,omitempty"`
	ConstantInvoke string                 `json:"constantInvoke,omitempty"`
	RpcToken       string                 `json:"sekiro_token,omitempty"`
	Raw            map[string]interface{} `json:"-"`
	Params         map[string]interface{} `json:"-"`
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

	rpcToken := resolveAccessToken(c)
	if !h.authorizeRegisteredGroupAccess(c, chatCompletionGroup, rpcToken) {
		return
	}

	targetClient, err := h.selectTargetClient(chatCompletionGroup, "", "", chatCompletionAction, rawMap)
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
	logger.Infof("chat completions: chatId=%s, model=%s, group=%s, clientId=%s, stream=%v",
		chatID, openAiReq.Model, chatCompletionGroup, targetClient.ClientID, openAiReq.Stream)

	chatReqParams := map[string]interface{}{
		"messages": prompt,
		"model":    openAiReq.Model,
		"chatId":   chatID,
	}
	reqDataJSON, err := marshalJSON(map[string]interface{}{
		"action": chatCompletionAction,
		"params": chatReqParams,
	})
	if err != nil {
		writeChatError(c, http.StatusOK, "Failed to marshal request data: "+err.Error())
		return
	}

	sequence := fmt.Sprintf("%s-%s-%d", chatCompletionGroup, chatCompletionAction, time.Now().UnixNano())

	req := &ChatCompletionRequest{
		ChatCompletionRequest: openAiReq,
		Group:                 chatCompletionGroup,
		RpcToken:              rpcToken,
		Raw:                   rawMap,
		Params:                chatReqParams,
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

	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, req.Group, targetClient.ClientID, reqDataJSON); err != nil {
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

	if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, req.Group, targetClient.ClientID, reqDataJSON); err != nil {
		targetClient.MarkFailure()
		writeChatError(c, http.StatusOK, "Failed to send request: "+err.Error())
		return
	}

	header := c.Writer.Header()
	header.Set("Content-Type", "text/event-stream; charset=utf-8")
	header.Set("Cache-Control", "no-cache")
	header.Set("X-Accel-Buffering", "no")
	header.Set("Connection", "keep-alive")
	c.Writer.WriteHeader(http.StatusOK)
	c.Writer.Flush()
	if err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Time{}); err != nil {
		logger.Debugf("Failed to clear SSE write deadline: %v", err)
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	chunkID := "chatcmpl-" + sequence
	parser := newQwenSSEParser()
	roleEmitted := false
	finished := false

	emit := func(delta map[string]interface{}, finishReason interface{}) {
		writeSSEData(c, chatCompletionStreamFrame(chunkID, req.Model, startTime, delta, finishReason))
	}
	emitFinish := func(reason string) {
		if finished {
			return
		}
		finished = true
		emit(map[string]interface{}{}, reason)
		writeSSEDone(c)
	}

	for {
		select {
		case <-ctx.Done():
			targetClient.MarkFailure()
			emit(map[string]interface{}{}, "error")
			writeSSEDone(c)
			return
		case chunk, ok := <-stream.ChunkChan:
			if !ok {
				if errMsg := stream.TerminalError(); errMsg != "" {
					targetClient.MarkFailure()
					writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, errMsg, startTime))
					if !finished {
						writeSSEDone(c)
					}
					return
				}
				if !finished {
					emitFinish("stop")
				}
				targetClient.MarkSuccess()
				return
			}
			if chunk.Error != "" {
				targetClient.MarkFailure()
				writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, chunk.Error, startTime))
				writeSSEDone(c)
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
				if ev.Done {
					emitFinish("stop")
					targetClient.MarkSuccess()
					return
				}
				if ev.Error != "" {
					targetClient.MarkFailure()
					writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, ev.Error, startTime))
					writeSSEDone(c)
					return
				}
				if ev.Finished {
					emitFinish("stop")
					targetClient.MarkSuccess()
					return
				}
				delta := map[string]interface{}{}
				if !roleEmitted {
					if ev.Role != "" {
						delta["role"] = ev.Role
					} else {
						delta["role"] = "assistant"
					}
					roleEmitted = true
				}
				if ev.Content != "" {
					if ev.Phase == "thinking" {
						delta["reasoning_content"] = ev.Content
					} else {
						delta["content"] = ev.Content
					}
				}
				if len(delta) == 0 {
					continue
				}
				emit(delta, nil)
			}
			if chunk.Done {
				emitFinish("stop")
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
	var raw interface{}
	if err := json.Unmarshal(data, &raw); err == nil {
		if rawMap, ok := raw.(map[string]interface{}); ok {
			if object, _ := rawMap["object"].(string); object == "chat.completion" {
				return rawMap
			}
			if content, ok := rawMap["content"]; ok {
				return chatCompletionResponse(req, sequence, content, startTime)
			}
		}
		return raw
	}
	return chatCompletionResponse(req, sequence, string(data), startTime)
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

func normalizeChatCompletionErrorChunk(req *ChatCompletionRequest, sequence, message string, startTime time.Time) interface{} {
	return map[string]interface{}{
		"id":      "chatcmpl-" + sequence,
		"object":  "chat.completion.chunk",
		"created": startTime.Unix(),
		"model":   req.Model,
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

func chatCompletionResponse(req *ChatCompletionRequest, sequence string, content interface{}, startTime time.Time) map[string]interface{} {
	return map[string]interface{}{
		"id":      "chatcmpl-" + sequence,
		"object":  "chat.completion",
		"created": startTime.Unix(),
		"model":   req.Model,
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

func writeSSEData(c *gin.Context, value interface{}) {
	data, err := json.Marshal(value)
	if err != nil {
		logger.Errorf("Failed to marshal chat completion stream chunk: %v", err)
		return
	}
	_, _ = fmt.Fprintf(c.Writer, "data: %s\n\n", data)
	c.Writer.Flush()
}

func writeSSEDone(c *gin.Context) {
	_, _ = fmt.Fprint(c.Writer, "data: [DONE]\n\n")
	c.Writer.Flush()
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
	return chatCompletionAction, r.Params, nil
}

func (r *ChatCompletionRequest) GetTimeout() time.Duration {
	return maxInvokeTimeout
}

func (r *ChatCompletionRequest) GetSequence(group string) string {
	return fmt.Sprintf("%s-%s-%d", group, chatCompletionAction, time.Now().UnixNano())
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

func (r *ChatCompletionRequest) GetAccessToken() string {
	return r.RpcToken
}

func (r *ChatCompletionRequest) IsStream() bool {
	return r.Stream
}
