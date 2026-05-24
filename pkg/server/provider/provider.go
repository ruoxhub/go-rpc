// Package provider 把"OpenAI 协议入站请求 → 上游服务" 的转换逻辑抽象成
// 可注册的 Provider，供 /v1/chat/completions 路由按 model 名分发。
//
// 设计要点（详见 docs/superpowers/specs/2026-05-23-qwen-openai-completions-design.md）：
//   - Provider.Match 决定"什么 model 名走哪个上游"
//   - BuildClientAction 把 OpenAI 请求体转换成下发给浏览器扩展的 ws action
//   - StreamDecoder 把扩展回流的原始上游字节翻译成 OpenAI SSE chunk
//
// Resolve(model) 在 chat_completions handler 进入时调用，未命中则继续走旧的
// `_chat_completions` 透传链路（fallback）。
package provider

import "github.com/mrh30000/go-rpc/pkg/model"

// Provider 表示一个上游协议适配器。每个 provider 内部状态应是只读的，运行期
// 不会被并发修改；它每次请求会返回一个新的 StreamDecoder（带请求级状态）。
type Provider interface {
	// Name 返回 provider 标识，主要用于日志和指标。例如 "qwen"。
	Name() string

	// Match 在解析完入站请求后被调用，判断该 model 名是否归本 provider 处理。
	// 一个 model 名最多命中一个 provider；多个 provider 同时 Match 时，
	// 注册顺序靠前者优先（参见 registry.go）。
	Match(model string) bool

	// BuildClientAction 把 OpenAI 入站请求转换成下发到浏览器扩展的 ws action。
	// 错误意味着请求体本身有问题（缺字段、tools 不合法等），handler 会用 HTTP 400
	// 返给上游客户端，因此应在写 SSE header 之前调用。
	BuildClientAction(req *model.ChatCompletionRequest) (ClientAction, error)

	// StreamDecoder 返回一个新的 per-request decoder。每次调用必须返回新实例，
	// 不要复用——decoder 内部维护 SSE 拆帧 buffer、状态机、tool parser 等。
	StreamDecoder() StreamDecoder
}

// ClientAction 描述要通过 ws 下发给浏览器扩展的一次调用。
//
// Action 是浏览器扩展端 actions 表的 key（例如 "qwen_chat_stream"）。
// Payload 是 action 的参数，最终会被序列化成
//
//	{"action": Action, "params": Payload}
//
// 由 chat_completions handler 通过 wsHandler.SendInvokeRequest 发送。
type ClientAction struct {
	Action  string
	Payload map[string]any
}

// StreamDecoder 把浏览器回流的"原始上游字节"翻译成 OpenAI SSE chunk。
//
// Push 接受任意大小的字节切片（可能跨 SSE event 边界），返回 0..N 个 OpenAI
// 格式的 stream chunk。decoder 必须能容忍任意切片大小（包括 1 字节切片），
// 内部维护 SSE 拆帧 buffer。
//
// Flush 在流终止时被调用，吐出 decoder 内部残余的内容（例如未闭合的 tool
// 标签兜底文本、补一个 finish_reason="stop" chunk 等）。
//
// 错误代表 decoder 进入不可恢复状态（例如 base64 解码失败、JSON 突变到无法继
// 续）。返回错误后调用方应停止继续 Push，并把错误透传成 SSE error chunk。
type StreamDecoder interface {
	Push(raw []byte) ([]model.ChatCompletionStreamResponse, error)
	Flush() ([]model.ChatCompletionStreamResponse, error)
}
