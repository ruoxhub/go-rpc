// Package qwen 把 OpenAI 协议入站请求适配为通义千问网页版 API。
//
// 详见 docs/superpowers/specs/2026-05-23-qwen-openai-completions-design.md。
package qwen

import "strings"

// Defaults for the qwen browser-side API target. Browsers append the dynamic
// query string (biz_id/nonce/timestamp/...) themselves, so this must NOT
// contain a query string.
const (
	DefaultChatTarget = "https://chat2.qianwen.com/api/v2/chat"
	ActionChatStream  = "qwen_chat_stream"
)

// modelAlias 直接覆盖 qwen 内部的 model id。从 Chat2API/qwen.ts MODEL_MAP 移植。
var modelAlias = map[string]string{
	"qwen3":                "tongyi-qwen3-max-model-agent",
	"qwen3-max":            "tongyi-qwen3-max-model-agent",
	"qwen3-max-thinking":   "tongyi-qwen3-max-thinking-agent",
	"qwen3-plus":           "tongyi-qwen-plus-agent",
	"qwen3.5-plus":         "Qwen3.5-Plus",
	"qwen3-flash":          "qwen3-flash",
	"qwen3-coder":          "qwen3-coder-plus",
}

// modelPrefixes 决定 model 名是否被本 provider 接管。任何已知别名命中（不分大小写）
// 或前缀以 "qwen" 开头都视为本 provider 的目标。
var modelPrefixes = []string{"qwen"}

// ResolvedModel 是 ResolveModel 的输出，描述对入站 model 名的最终解析。
//
// QwenID 是发给 chat2.qianwen.com 的真正 model 字段。
// EnableThinking / EnableWebSearch 用于驱动 deep_search 与 enable_search 字段，
// 以及把 Max 模型替换成 thinking 变体。
type ResolvedModel struct {
	QwenID          string
	EnableThinking  bool
	EnableWebSearch bool
}

// ShouldHandle 判断给定 model 名是否应交给 qwen provider。
//
// 命中规则（任一即接管）：
//   - 在 modelAlias 表里有显式映射
//   - 名字以已知前缀（qwen）开头
//
// 命中规则不区分大小写。
func ShouldHandle(model string) bool {
	if model == "" {
		return false
	}
	lower := strings.ToLower(strings.TrimSpace(model))
	if _, ok := modelAlias[lower]; ok {
		return true
	}
	for _, prefix := range modelPrefixes {
		if strings.HasPrefix(lower, prefix) {
			return true
		}
	}
	return false
}

// ResolveModel 把入站 model 名翻译成 qwen 内部 ID 并推断 thinking/search 开关。
//
// 推断规则（Chat2API/qwen.ts 移植）：
//   - 名字含 "think" / "thinking" / "r1" → enableThinking=true
//   - 名字含 "search" → enableWebSearch=true
//   - thinking 启用且基础模型是 max → 切到 max-thinking 变体
//   - 别名表未命中时，原样透传给上游（允许实验新模型）
//
// 输入空字符串时返回 zero ResolvedModel；调用方应在 BuildRequest 入口校验。
func ResolveModel(name string) ResolvedModel {
	trimmed := strings.TrimSpace(name)
	lower := strings.ToLower(trimmed)
	if trimmed == "" {
		return ResolvedModel{}
	}

	resolved := ResolvedModel{QwenID: trimmed}
	if mapped, ok := modelAlias[lower]; ok {
		resolved.QwenID = mapped
	}

	if strings.Contains(lower, "think") || strings.Contains(lower, "r1") {
		resolved.EnableThinking = true
	}
	if strings.Contains(lower, "search") {
		resolved.EnableWebSearch = true
	}

	if resolved.EnableThinking && resolved.QwenID == "tongyi-qwen3-max-model-agent" {
		resolved.QwenID = "tongyi-qwen3-max-thinking-agent"
	}

	return resolved
}
