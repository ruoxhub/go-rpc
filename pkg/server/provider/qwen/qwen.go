package qwen

import (
	"errors"
	"fmt"
	"time"

	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/mrh30000/go-rpc/pkg/server/provider"
)

// Provider 实现 provider.Provider 接口。它把 OpenAI Chat Completions 请求转换为
// 通过 ws action `qwen_chat_stream` 下发给浏览器扩展的调用。
//
// StreamDecoder 在 M2 阶段返回 nil（M3 实装），调用方需要在 chat_completions
// handler 里检查 nil 并 fallback——直到 M3 落地后这个 provider 才能完整接管流式响应。
type Provider struct {
	cfg config.ProviderConfig
}

// New 用 yaml 配置创建一个 qwen provider 实例。
func New(cfg config.ProviderConfig) *Provider {
	return &Provider{cfg: cfg}
}

// Name 返回 "qwen"，用于日志/指标标签。
func (p *Provider) Name() string { return "qwen" }

// Match 判断 model 名是否归 qwen 接管。详见 ShouldHandle。
func (p *Provider) Match(modelName string) bool {
	return ShouldHandle(modelName)
}

// Timeout 返回 qwen 调用的超时时间。
// 当 cfg.QwenTimeoutSeconds <= 0 时使用 spec 默认 120s。
func (p *Provider) Timeout() time.Duration {
	if p.cfg.QwenTimeoutSeconds > 0 {
		return time.Duration(p.cfg.QwenTimeoutSeconds) * time.Second
	}
	return 120 * time.Second
}

// LogChunks 返回是否打印每个 ws chunk 的 DEBUG 日志。
func (p *Provider) LogChunks() bool {
	return p.cfg.QwenLogChunks
}

// BuildClientAction 把 OpenAI 请求转成 qwen_chat_stream ws action。
//
// 输出 Payload 结构：
//
//	{
//	    "body":   { ...完整 qwen body... },
//	    "target": "https://chat2.qianwen.com/api/v2/chat"
//	}
//
// 浏览器扩展端 sample/web/content/qwen/api.js 接收后自行附加 query string
// （nonce/timestamp/device_id 等）和 ticket cookie 后转发到 chat2.qianwen.com，
// 详见 spec §5.2。
func (p *Provider) BuildClientAction(req *model.ChatCompletionRequest) (provider.ClientAction, error) {
	body, err := BuildRequest(req, nil)
	if err != nil {
		return provider.ClientAction{}, fmt.Errorf("qwen build request: %w", err)
	}
	return provider.ClientAction{
		Action: ActionChatStream,
		Payload: map[string]any{
			"body":   body,
			"target": DefaultChatTarget,
		},
	}, nil
}

// StreamDecoder 在 M2 阶段返回 nil。M3 接入 qwenDecoder 后会替换。
//
// 调用方必须把 nil 当作"无法接管流式响应"对待，回退到旧的 _chat_completions
// 透传链路，避免破坏现有可用功能。
func (p *Provider) StreamDecoder() provider.StreamDecoder {
	return nil
}

// ErrStreamDecoderNotReady 用于在更上层暴露"qwen 暂不能完整接管流式响应"。
// 当前未在生产路径使用，预留给 chat_completions handler 在 M5 决定如何回退。
var ErrStreamDecoderNotReady = errors.New("qwen stream decoder not implemented yet (M3)")
