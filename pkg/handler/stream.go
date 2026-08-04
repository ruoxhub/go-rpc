package handler

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/internal/toolcall"
	"github.com/mrh30000/go-rpc/internal/utils/logger"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
)

// streamHoldback 把流式 chat completions 路径里"累积 answer → 末尾扣住
// dsmlOpener → 末次 flush / 工具调用解析"这套公共 state + 行为集中起来。
//
// 两个调用方 (handleChatCompletionStream / qwenStreamToOpenAI) 原本各自用
// 闭包实现 flushSafeContent / finalizeAndEmit / adoptResponseID，逻辑 99% 相同，
// 仅 emit 帧的字段形状有差异（chat_completions 用 deepseek 风格带
// system_fingerprint / usage 占位；qwen 走精简 fields）。本结构把 state 抽出来
// 后由调用方提供 emit / writeDone 两个回调即可。
type streamHoldback struct {
	chunkID     string
	idAdopted   bool
	fullText    strings.Builder
	emittedLen  int
	roleEmitted bool
	finished    bool
}

// emitDelta 把一条 delta 包装成 OpenAI chunk 帧并写入 SSE。
// emit 由调用方提供，因为不同路径的帧字段不一致（deepseek 风格 vs 精简）。
type emitDelta func(delta map[string]interface{}, finishReason interface{})

// newStreamHoldback 创建初始 state，chunkID 用本地 sequence 兜底，
// 后续 adoptResponseID 命中上游 response_id 时再覆盖。
func newStreamHoldback(fallbackChunkID string) *streamHoldback {
	return &streamHoldback{chunkID: fallbackChunkID}
}

// adoptResponseID 首次见到的非空上游 id 覆盖 chunkID；之后忽略后续 id 变化，
// 保证整个流的 choices[].delta.id 稳定。
func (h *streamHoldback) adoptResponseID(id string) {
	if id == "" || h.idAdopted {
		return
	}
	h.chunkID = id
	h.idAdopted = true
}

// flushSafeContent 释放已确认安全的纯文本前缀。
// 末尾扣住 len(dsmlOpener) 字节防止 DSML 起手被先吐出去；
// 一旦定位到 dsmlOpener，则截断到该位置之前。
func (h *streamHoldback) flushSafeContent(emit emitDelta) {
	full := h.fullText.String()
	safeEnd := len(full) - len(dsmlOpener)
	if safeEnd < 0 {
		safeEnd = 0
	}
	if idx := strings.Index(full, dsmlOpener); idx >= 0 && idx < safeEnd {
		safeEnd = idx
	}
	if safeEnd <= h.emittedLen {
		return
	}
	delta := map[string]interface{}{}
	if !h.roleEmitted {
		delta["role"] = "assistant"
		h.roleEmitted = true
	}
	delta["content"] = full[h.emittedLen:safeEnd]
	emit(delta, nil)
	h.emittedLen = safeEnd
}

// finalizeAndEmit 在流结束时跑工具调用解析。
// 命中工具调用：补完 DSML 之前的纯文本 → emit tool_calls → finish="tool_calls"。
// 否则：把 holdback 扣住的尾巴吐完 → finish="stop"。
// onFinal 回调用于在收尾时写入 finish 帧和 [DONE]（由调用方决定是否打 DONE）。
func (h *streamHoldback) finalizeAndEmit(emit emitDelta, toolNames []string, toolsRaw any, onFinal func(reason string)) {
	full := h.fullText.String()
	parsed := toolcall.ParseToolCallsDetailed(full, toolNames)
	if len(parsed.Calls) > 0 {
		head := strings.Index(full, dsmlOpener)
		if head < 0 {
			head = len(full)
		}
		if head > h.emittedLen {
			delta := map[string]interface{}{}
			if !h.roleEmitted {
				delta["role"] = "assistant"
				h.roleEmitted = true
			}
			delta["content"] = full[h.emittedLen:head]
			emit(delta, nil)
			h.emittedLen = head
		}
		tcs := toolcall.FormatOpenAIStreamToolCalls(parsed.Calls, toolsRaw)
		tcDelta := map[string]interface{}{}
		if !h.roleEmitted {
			tcDelta["role"] = "assistant"
			h.roleEmitted = true
		}
		tcDelta["tool_calls"] = tcs
		emit(tcDelta, nil)
		if !h.finished {
			h.finished = true
			onFinal("tool_calls")
		}
		return
	}
	if len(full) > h.emittedLen {
		delta := map[string]interface{}{}
		if !h.roleEmitted {
			delta["role"] = "assistant"
			h.roleEmitted = true
		}
		delta["content"] = full[h.emittedLen:]
		emit(delta, nil)
		h.emittedLen = len(full)
	}
	if !h.finished {
		h.finished = true
		onFinal("stop")
	}
}

// flushThinking 把 reasoning_content 阶段的 delta 透传出去。
// 与 flushSafeContent 不同：thinking 不进 holdback，立即 emit。
func (h *streamHoldback) flushThinking(emit emitDelta, role, content string) bool {
	if content == "" && role == "" {
		return false
	}
	delta := map[string]interface{}{}
	if !h.roleEmitted {
		if role != "" {
			delta["role"] = role
		} else {
			delta["role"] = "assistant"
		}
		h.roleEmitted = true
	}
	if content != "" {
		delta["reasoning_content"] = content
	}
	if len(delta) == 0 {
		return false
	}
	emit(delta, nil)
	return true
}

// appendAnswer 把 answer 阶段 content 追加到 holdback 缓冲；空字符串忽略。
func (h *streamHoldback) appendAnswer(content string) {
	if content != "" {
		h.fullText.WriteString(content)
	}
}

// errInvokeTimeout is the typed sentinel returned when waitUnaryInvoke's
// context deadline fires. Callers must use errors.Is — never string match.
var errInvokeTimeout = errors.New("request timeout")

// waitUnaryInvoke 统一 "Add + Send + Wait" 三段式，不写 HTTP 响应。
// 调用方按业务错误形态（writeChatError / writeForwardError）自行渲染。
//
// 直接 select 在 InvokeRecord.ResponseChan 上，不另起 goroutine：
// timeoutManager.Remove 会 Close 该 channel，超时路径可立即唤醒。
func (h *APIHandler) waitUnaryInvoke(
	ctx context.Context,
	group string,
	target *client.RpcClient,
	sequence string,
	reqDataJSON []byte,
	timeout time.Duration,
	traceID string,
) (*forwarder.InvokeResponse, error) {
	if h.timeoutManager == nil || h.wsHandler == nil {
		return nil, fmt.Errorf("invoke dependencies not available")
	}
	rec := h.timeoutManager.Add(sequence, group, target.ClientID, reqDataJSON)
	rec.Timeout = timeout
	rec.TraceID = traceID

	if err := h.wsHandler.SendInvokeRequest(target, sequence, group, target.ClientID, reqDataJSON, traceID); err != nil {
		h.timeoutManager.Remove(sequence)
		logger.WithTraceID(traceID).Debugf("Invoke send failed: sequence=%s, group=%s, clientId=%s, err=%v", sequence, group, target.ClientID, err)
		return nil, fmt.Errorf("Failed to send request: %w", err)
	}

	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	select {
	case <-waitCtx.Done():
		// Match TimeoutManager.Wait: mark timed-out so Complete bails out,
		// then Remove closes ResponseChan (sync.Once).
		rec.SetTimedOut()
		h.timeoutManager.Remove(sequence)
		logger.WithTraceID(traceID).Debugf("Invoke timed out: sequence=%s, group=%s, clientId=%s", sequence, group, target.ClientID)
		return nil, errInvokeTimeout
	case resp, ok := <-rec.ResponseChan:
		if !ok {
			return nil, forwarder.ErrChannelClosed
		}
		// Complete may already have deleted the map entry; Remove is a no-op then.
		h.timeoutManager.Remove(sequence)
		return resp, nil
	}
}

// streamChunkEmitter writes one OpenAI-compatible SSE chunk.
// chunkID is the current stream id (may be updated after adoptResponseID).
type streamChunkEmitter func(chunkID string, delta map[string]interface{}, finishReason interface{})

// driveOpenAIChatStream 驱动 qwen/chat 共用的 SSE 流式循环。
// emit 由调用方决定 chunk 帧形状（deepseek 完整帧 vs 精简帧）。
func (h *APIHandler) driveOpenAIChatStream(
	c *gin.Context,
	stream *forwarder.StreamRecord,
	target *client.RpcClient,
	timeout time.Duration,
	model string,
	startTime time.Time,
	toolNames []string,
	toolsRaw any,
	chunkIDFallback string,
	emit streamChunkEmitter,
) {
	WriteSSEHeaders(c)
	c.Writer.Flush()
	if err := http.NewResponseController(c.Writer).SetWriteDeadline(time.Time{}); err != nil {
		logger.Debugf("Failed to clear SSE write deadline: %v", err)
	}

	ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
	defer cancel()

	holdback := newStreamHoldback(chunkIDFallback)
	parser := newQwenSSEParser()

	// Bind holdback.chunkID into the legacy emitDelta used by streamHoldback.
	boundEmit := func(delta map[string]interface{}, finishReason interface{}) {
		emit(holdback.chunkID, delta, finishReason)
	}

	onFinal := func(reason string) {
		boundEmit(map[string]interface{}{}, reason)
		WriteSSEDone(c)
	}
	finalize := func() {
		holdback.finalizeAndEmit(boundEmit, toolNames, toolsRaw, onFinal)
	}

	for {
		select {
		case <-ctx.Done():
			target.MarkFailure()
			boundEmit(map[string]interface{}{}, "error")
			WriteSSEDone(c)
			return
		case chunk, ok := <-stream.ChunkChan:
			if !ok {
				if errMsg := stream.TerminalError(); errMsg != "" {
					target.MarkFailure()
					WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, model, startTime, errMsg))
					if !holdback.finished {
						WriteSSEDone(c)
					}
					return
				}
				finalize()
				target.MarkSuccess()
				return
			}
			if chunk.Error != "" {
				target.MarkFailure()
				WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, model, startTime, chunk.Error))
				WriteSSEDone(c)
				return
			}
			text, err := decodeStreamChunkText(chunk.Data)
			if err != nil {
				logger.Warnf("openai stream decode chunk: %v", err)
				continue
			}
			if text == "" && !chunk.Done {
				continue
			}
			for _, ev := range parser.Feed(text) {
				holdback.adoptResponseID(ev.ResponseID)
				if ev.Done {
					finalize()
					target.MarkSuccess()
					return
				}
				if ev.Error != "" {
					target.MarkFailure()
					WriteSSEData(c, buildOpenAIErrorChunk(holdback.chunkID, model, startTime, ev.Error))
					WriteSSEDone(c)
					return
				}
				if ev.Finished {
					finalize()
					target.MarkSuccess()
					return
				}
				if ev.Content == "" && ev.Role == "" {
					continue
				}
				if ev.Phase == "thinking" {
					holdback.flushThinking(boundEmit, ev.Role, ev.Content)
					continue
				}
				holdback.appendAnswer(ev.Content)
				holdback.flushSafeContent(boundEmit)
			}
			if chunk.Done {
				finalize()
				target.MarkSuccess()
				return
			}
		}
	}
}
