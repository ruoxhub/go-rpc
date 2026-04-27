package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/sekiro-go/sekiro-go/internal/utils/logger"
	"github.com/sekiro-go/sekiro-go/pkg/server/client"
	"github.com/sekiro-go/sekiro-go/pkg/server/forwarder"
)

const (
	chatCompletionAction       = "_chat_completions"
	maxChatCompletionBodyBytes = 1 << 20
)

type ChatCompletionRequest struct {
	Model          string                 `json:"model"`
	Messages       []ChatMessage          `json:"messages"`
	Stream         bool                   `json:"stream,omitempty"`
	Group          string                 `json:"group,omitempty"`
	ClientID       string                 `json:"clientId,omitempty"`
	ConstantInvoke string                 `json:"constantInvoke,omitempty"`
	SekiroToken    string                 `json:"sekiro_token,omitempty"`
	Raw            map[string]interface{} `json:"-"`
	Params         map[string]interface{} `json:"-"`
}

type ChatMessage struct {
	Role    string      `json:"role"`
	Content interface{} `json:"content"`
}

func (h *APIHandler) HandleChatCompletions(c *gin.Context) {
	startTime := time.Now()
	req, err := parseChatCompletionRequest(c)
	if err != nil {
		writeChatError(c, http.StatusBadRequest, err.Error())
		return
	}

	if req.SekiroToken == "" {
		req.SekiroToken = resolveAccessToken(c)
	}

	if !h.authorizeRegisteredGroupAccess(c, req.Group, req.SekiroToken) {
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

func parseChatCompletionRequest(c *gin.Context) (*ChatCompletionRequest, error) {
	c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxChatCompletionBodyBytes)

	var raw map[string]interface{}
	decoder := json.NewDecoder(c.Request.Body)
	if err := decoder.Decode(&raw); err != nil {
		return nil, fmt.Errorf("invalid JSON request body")
	}

	model, _ := raw["model"].(string)
	if strings.TrimSpace(model) == "" {
		return nil, fmt.Errorf("model is required")
	}

	messagesRaw, ok := raw["messages"].([]interface{})
	if !ok || len(messagesRaw) == 0 {
		return nil, fmt.Errorf("messages is required")
	}

	messages := make([]ChatMessage, 0, len(messagesRaw))
	for _, item := range messagesRaw {
		msgMap, ok := item.(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("messages must contain objects")
		}
		role, _ := msgMap["role"].(string)
		messages = append(messages, ChatMessage{
			Role:    role,
			Content: msgMap["content"],
		})
	}

	params := make(map[string]interface{}, len(raw))
	for k, v := range raw {
		params[k] = v
	}

	req := &ChatCompletionRequest{
		Model:          model,
		Messages:       messages,
		Stream:         boolFromRaw(raw["stream"]),
		Group:          firstNonEmpty(c.Query("group"), stringFromRaw(raw["group"])),
		ClientID:       firstNonEmpty(c.Query("clientId"), stringFromRaw(raw["clientId"])),
		ConstantInvoke: firstNonEmpty(c.Query("constantInvoke"), stringFromRaw(raw["constantInvoke"])),
		SekiroToken:    firstNonEmpty(c.Query("sekiro_token"), stringFromRaw(raw["sekiro_token"])),
		Raw:            raw,
		Params:         params,
	}

	delete(req.Params, "group")
	delete(req.Params, "clientId")
	delete(req.Params, "constantInvoke")
	delete(req.Params, "sekiro_token")

	if req.Group == "" {
		return nil, fmt.Errorf("group parameter required")
	}

	return req, nil
}

func (h *APIHandler) handleChatCompletionNonStream(c *gin.Context, req *ChatCompletionRequest, targetClient *client.SekiroClient, sequence string, reqDataJSON []byte, timeout time.Duration, startTime time.Time) {
	invokeRecord := h.timeoutManager.Add(sequence, req.Group, targetClient.ClientID, reqDataJSON)
	invokeRecord.Timeout = timeout

	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		h.timeoutManager.Remove(sequence)
		writeChatError(c, http.StatusOK, "Invalid client connection")
		return
	}

	if err := h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON, targetClient); err != nil {
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

func (h *APIHandler) handleChatCompletionStream(c *gin.Context, req *ChatCompletionRequest, targetClient *client.SekiroClient, sequence string, reqDataJSON []byte, timeout time.Duration, startTime time.Time) {
	stream := h.timeoutManager.RegisterStream(sequence, req.Group, targetClient.ClientID, timeout)
	defer h.timeoutManager.RemoveStream(sequence)

	conn, ok := targetClient.Connection.(*websocket.Conn)
	if !ok {
		writeChatError(c, http.StatusOK, "Invalid client connection")
		return
	}

	if err := h.wsHandler.SendInvokeRequest(conn, sequence, req.Group, targetClient.ClientID, reqDataJSON, targetClient); err != nil {
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
