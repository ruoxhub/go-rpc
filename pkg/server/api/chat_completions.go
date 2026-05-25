package api

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	json "github.com/goccy/go-json"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/client"
	"github.com/mrh30000/go-rpc/pkg/server/forwarder"
)

const (
	chatCompletionAction       = "_chat_completions"
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

func (h *APIHandler) HandleChatCompletions(c *gin.Context) {
	startTime := time.Now()
	req, err := parseChatCompletionRequest(c)
	if err != nil {
		writeChatError(c, http.StatusBadRequest, err.Error())
		return
	}

	if req.RpcToken == "" {
		req.RpcToken = resolveAccessToken(c)
	}

	if !h.authorizeRegisteredGroupAccess(c, req.Group, req.RpcToken) {
		return
	}

	targetClient, err := h.selectTargetClient(req.Group, req.ClientID, req.ConstantInvoke, chatCompletionAction, req.Params)
	if err != nil {
		writeChatError(c, http.StatusOK, err.Error())
		return
	}
	if targetClient == nil {
		writeChatError(c, http.StatusOK, "no client available")
		return
	}

	reqData := map[string]interface{}{
		"action": chatCompletionAction,
		"params": req.Params,
	}
	reqDataJSON, err := marshalJSON(reqData)
	if err != nil {
		writeChatError(c, http.StatusOK, "Failed to marshal request data: "+err.Error())
		return
	}

	sequence := fmt.Sprintf("%s-%s-%d", req.Group, chatCompletionAction, time.Now().UnixNano())
	timeout := maxInvokeTimeout

	if req.Stream {
		h.handleChatCompletionStream(c, req, targetClient, sequence, reqDataJSON, timeout, startTime)
		return
	}

	h.handleChatCompletionNonStream(c, req, targetClient, sequence, reqDataJSON, timeout, startTime)
}

// parseChatCompletionRequest 读取 OpenAI Chat Completions HTTP 请求，把 body
// 拆成 model.ChatCompletionRequest（标准字段）+ sekiro 私有字段。
//
// model 字段通过 json.Unmarshal 到嵌入的 model.ChatCompletionRequest 解析；
// 未识别的 OpenAI 扩展字段保留在 Raw 和 Params 里供下游透传。
func parseChatCompletionRequest(c *gin.Context) (*ChatCompletionRequest, error) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxChatCompletionBodyBytes)

	var raw map[string]interface{}
	decoder := json.NewDecoder(c.Request.Body)
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON request body")
	}

	req := &ChatCompletionRequest{Raw: raw}

	// 把 raw 重新编回 JSON 解到 model.ChatCompletionRequest，避免再写一遍
	// 字段映射逻辑；同时保留 raw map 给透传用。
	rawJSON, err := json.Marshal(raw)
	if err != nil {
		return nil, fmt.Errorf("re-encode request body: %w", err)
	}
	if err := json.Unmarshal(rawJSON, &req.ChatCompletionRequest); err != nil {
		return nil, fmt.Errorf("decode chat completion fields: %w", err)
	}

	if strings.TrimSpace(req.Model) == "" {
		return nil, fmt.Errorf("model is required")
	}
	if len(req.Messages) == 0 {
		return nil, fmt.Errorf("messages is required")
	}

	req.Group = firstNonEmpty(c.Query("group"), stringFromRaw(raw["group"]))
	req.ClientID = firstNonEmpty(c.Query("clientId"), stringFromRaw(raw["clientId"]))
	req.ConstantInvoke = firstNonEmpty(c.Query("constantInvoke"), stringFromRaw(raw["constantInvoke"]))
	req.RpcToken = firstNonEmpty(c.Query("sekiro_token"), stringFromRaw(raw["sekiro_token"]))

	params := make(map[string]interface{}, len(raw))
	for k, v := range raw {
		params[k] = v
	}
	delete(params, "group")
	delete(params, "clientId")
	delete(params, "constantInvoke")
	delete(params, "sekiro_token")
	req.Params = params

	if req.Group == "" {
		return nil, fmt.Errorf("group parameter required")
	}

	return req, nil
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
	header.Set("Content-Type", "text/event-stream")
	header.Set("Cache-Control", "no-cache")
	header.Set("X-Accel-Buffering", "no")
	if err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Time{}); err != nil {
		logger.Debugf("Failed to clear SSE write deadline: %v", err)
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	for {
		select {
		case <-ctx.Done():
			targetClient.MarkFailure()
			writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, "Request timeout", startTime))
			writeSSEDone(c)
			return
		case chunk, ok := <-stream.ChunkChan:
			if !ok {
				if errMsg := stream.TerminalError(); errMsg != "" {
					targetClient.MarkFailure()
					writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, errMsg, startTime))
					writeSSEDone(c)
					return
				}
				targetClient.MarkSuccess()
				writeSSEDone(c)
				return
			}
			if chunk.Error != "" {
				targetClient.MarkFailure()
				writeSSEData(c, normalizeChatCompletionErrorChunk(req, sequence, chunk.Error, startTime))
				writeSSEDone(c)
				return
			}
			if len(chunk.Data) > 0 {
				writeSSEData(c, normalizeChatCompletionChunk(req, chunk.Data, sequence, startTime))
			}
			if chunk.Done {
				targetClient.MarkSuccess()
				writeSSEDone(c)
				return
			}
		}
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
