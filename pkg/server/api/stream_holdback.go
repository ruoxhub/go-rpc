package api

import (
	"strings"

	"github.com/mrh30000/go-rpc/internal/toolcall"
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
