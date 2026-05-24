package qwen

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/mrh30000/go-rpc/pkg/model"
)

// QwenChatRequest 是 chat2.qianwen.com /api/v2/chat 的请求体。
//
// 字段名严格对齐 qwen 网页版 v2 协议。详见 spec §5.1 与 Chat2API/qwen.ts。
type QwenChatRequest struct {
	DeepSearch      string         `json:"deep_search"`
	ReqID           string         `json:"req_id"`
	Model           string         `json:"model"`
	Scene           string         `json:"scene"`
	SessionID       string         `json:"session_id"`
	SubScene        string         `json:"sub_scene"`
	Temporary       bool           `json:"temporary"`
	Messages        []QwenMessage  `json:"messages"`
	From            string         `json:"from"`
	ParentReqID     string         `json:"parent_req_id"`
	EnableSearch    bool           `json:"enable_search"`
	BizData         string         `json:"biz_data"`
	SceneParam      string         `json:"scene_param"`
	ChatClient      string         `json:"chat_client"`
	ClientTM        string         `json:"client_tm"`
	ProtocolVersion string         `json:"protocol_version"`
	BizID           string         `json:"biz_id"`
}

// QwenMessage 是 qwen 协议中的单条消息。Content 是把整段 OpenAI 多轮对话
// 折叠后的最终文本——qwen 网页版本身只接受单轮 prompt。
type QwenMessage struct {
	Content  string                 `json:"content"`
	MimeType string                 `json:"mime_type"`
	MetaData map[string]interface{} `json:"meta_data"`
}

// BuildOptions 是 BuildRequest 的可选参数。
//
// Now 用于注入时间戳，便于测试；为 nil 时使用 time.Now。
// NewID 用于注入 req_id/session_id 生成器，便于测试；为 nil 时使用 UUIDv4 去横线。
//
// EnableThinkingOverride / EnableWebSearchOverride 让 handler 在解析请求阶段
// 把外部显式开关注入进来（例如 reasoning_effort、自定义 query 参数等）。
// nil 表示未指定，沿用关键字推断。
type BuildOptions struct {
	Now                     func() time.Time
	NewID                   func() string
	EnableThinkingOverride  *bool
	EnableWebSearchOverride *bool
}

// ErrEmptyMessages 表示请求体没有任何 user/system/assistant 消息。
var ErrEmptyMessages = errors.New("qwen: messages must not be empty")

// ErrEmptyModel 表示请求体未指定 model。
var ErrEmptyModel = errors.New("qwen: model is required")

// BuildRequest 把 OpenAI 风格请求体翻译成 qwen 网页版请求体。
//
// 翻译规则严格对齐 spec §5.1：
//   - model 经 ResolveModel 翻译为 qwen 内部 ID，并推断 thinking/search 开关
//   - system 消息抽离为 systemPrompt
//   - 其余 user/assistant/tool 消息按顺序折叠为 conversationParts
//   - 当 tools 非空时，注入 tools system prompt 并在 user 末尾追加 TOOL_WRAP_HINT
//   - finalContent = systemPrompt 存在时 "{system}\n\nUser: {user}"，否则 user
//   - deep_search = (enableThinking || enableWebSearch) ? "1" : "0"
//   - enable_search = enableWebSearch
//   - req_id / session_id 用 UUIDv4 去横线
//
// req 不能为 nil；req.Messages 不能为空；req.Model 不能为空。
func BuildRequest(req *model.ChatCompletionRequest, opts *BuildOptions) (*QwenChatRequest, error) {
	if req == nil {
		return nil, errors.New("qwen: nil request")
	}
	if strings.TrimSpace(req.Model) == "" {
		return nil, ErrEmptyModel
	}
	if len(req.Messages) == 0 {
		return nil, ErrEmptyMessages
	}

	now := time.Now
	newID := defaultNewID
	if opts != nil {
		if opts.Now != nil {
			now = opts.Now
		}
		if opts.NewID != nil {
			newID = opts.NewID
		}
	}

	resolved := ResolveModel(req.Model)
	if resolved.QwenID == "" {
		resolved.QwenID = req.Model
	}

	// 显式 override 优先级最高，覆盖关键字推断。
	enableThinking := resolved.EnableThinking
	enableWebSearch := resolved.EnableWebSearch
	if opts != nil {
		if opts.EnableThinkingOverride != nil {
			enableThinking = *opts.EnableThinkingOverride
		}
		if opts.EnableWebSearchOverride != nil {
			enableWebSearch = *opts.EnableWebSearchOverride
		}
	}

	// thinking 启用时回退到对应模型变体。
	qwenID := resolved.QwenID
	if enableThinking && qwenID == "tongyi-qwen3-max-model-agent" {
		qwenID = "tongyi-qwen3-max-thinking-agent"
	}

	systemPrompt, conversationParts := foldMessages(req.Messages)
	userContent := strings.Join(conversationParts, "\n\n")

	if len(req.Tools) > 0 && !hasToolPromptInjected(req.Messages) {
		toolsPrompt := toolsToSystemPrompt(req.Tools)
		if systemPrompt != "" {
			systemPrompt = systemPrompt + "\n\n" + toolsPrompt
		} else {
			systemPrompt = toolsPrompt
		}
		userContent = userContent + ToolWrapHint
	}

	finalContent := userContent
	if systemPrompt != "" {
		finalContent = fmt.Sprintf("%s\n\nUser: %s", systemPrompt, userContent)
	}

	timestamp := now().UnixMilli()

	deepSearch := "0"
	if enableThinking || enableWebSearch {
		deepSearch = "1"
	}

	body := &QwenChatRequest{
		DeepSearch:      deepSearch,
		ReqID:           newID(),
		Model:           qwenID,
		Scene:           "chat",
		SessionID:       newID(),
		SubScene:        "chat",
		Temporary:       false,
		Messages: []QwenMessage{
			{
				Content:  finalContent,
				MimeType: "text/plain",
				MetaData: map[string]interface{}{
					"ori_query": finalContent,
				},
			},
		},
		From:            "default",
		ParentReqID:     "0",
		EnableSearch:    enableWebSearch,
		BizData:         `{"entryPoint":"tongyigw"}`,
		SceneParam:      "first_turn",
		ChatClient:      "h5",
		ClientTM:        fmt.Sprintf("%d", timestamp),
		ProtocolVersion: "v2",
		BizID:           "ai_qwen",
	}

	return body, nil
}

// foldMessages 把 OpenAI 多轮 messages 折叠成单 prompt。
//
// 返回：systemPrompt 是抽离出来的 system 内容，conversationParts 是按原顺序
// 处理后的 user / assistant / tool 文本块（assistant 文本带 "Assistant: " 前缀；
// tool 调用与 tool 结果走 toolProfile 模板格式化）。
func foldMessages(messages []model.ChatCompletionMessage) (string, []string) {
	var systemPrompt string
	parts := make([]string, 0, len(messages))

	for _, msg := range messages {
		text := messageText(msg)
		switch msg.Role {
		case model.ChatMessageRoleSystem, model.ChatMessageRoleDeveloper:
			// 多个 system 消息按顺序拼接，与 qwen.ts 行为一致。
			if systemPrompt == "" {
				systemPrompt = text
			} else {
				systemPrompt = systemPrompt + "\n\n" + text
			}
		case model.ChatMessageRoleUser:
			parts = append(parts, text)
		case model.ChatMessageRoleAssistant:
			if len(msg.ToolCalls) > 0 {
				parts = append(parts, formatAssistantToolCalls(msg.ToolCalls))
				continue
			}
			parts = append(parts, "Assistant: "+text)
		case model.ChatMessageRoleTool, model.ChatMessageRoleFunction:
			if msg.ToolCallID == "" {
				continue
			}
			parts = append(parts, formatToolResult(msg.ToolCallID, text))
		}
	}

	return systemPrompt, parts
}

// messageText 返回消息的纯文本内容。
//
// 优先使用 MultiContent（多模态结构化数组）中的 type=text 部分；如果没有
// MultiContent 则使用 Content。两者互斥：openai.go ChatCompletionMessage
// 的 MarshalJSON 已强制约束。
func messageText(msg model.ChatCompletionMessage) string {
	if len(msg.MultiContent) > 0 {
		var sb strings.Builder
		for i, p := range msg.MultiContent {
			if p.Type != model.ChatMessagePartTypeText {
				continue
			}
			if i > 0 && sb.Len() > 0 {
				sb.WriteString("\n")
			}
			sb.WriteString(p.Text)
		}
		return sb.String()
	}
	return msg.Content
}

// defaultNewID 生成 32-char hex 字符串，等价于 qwen.ts 的 uuid(false)。
// 用 crypto/rand 而不是 google/uuid 避免再加一层依赖。
func defaultNewID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		// 不应到达：rand.Read 在受支持平台上不会失败。
		return fmt.Sprintf("%016x", time.Now().UnixNano())
	}
	// 标记为 v4 / variant 1，与 UUIDv4 等价但去横线。
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return hex.EncodeToString(b[:])
}
