package qwen

import (
	"fmt"
	"strings"

	json "github.com/goccy/go-json"

	"github.com/mrh30000/go-rpc/pkg/model"
)

// ToolWrapHint 在请求里同时携带 tools 时，作为提示后缀追加到 user content。
// 模板对齐 Chat2API utils/tools.ts。
const ToolWrapHint = `

You have access to tools. When you need to call a tool, wrap your tool call in the following format:

[function_calls]
{"name": "tool_name", "arguments": {...}}
[/function_calls]

Otherwise, respond normally.`

// toolsToSystemPrompt 为 tools 字段生成 system prompt 注入文本。
// 输出形式与 Chat2API utils/tools.ts toolsToSystemPrompt 行为对齐：
// 列出每个 tool 的 name、description、parameters JSON。
func toolsToSystemPrompt(tools []model.Tool) string {
	if len(tools) == 0 {
		return ""
	}
	var sb strings.Builder
	sb.WriteString("You have access to the following tools:\n\n")
	for _, t := range tools {
		if t.Function == nil {
			continue
		}
		fn := t.Function
		sb.WriteString("- ")
		sb.WriteString(fn.Name)
		if fn.Description != "" {
			sb.WriteString(": ")
			sb.WriteString(fn.Description)
		}
		sb.WriteString("\n")
		if fn.Parameters != nil {
			schema, err := json.Marshal(fn.Parameters)
			if err == nil {
				sb.WriteString("  parameters: ")
				sb.Write(schema)
				sb.WriteString("\n")
			}
		}
	}
	return strings.TrimRight(sb.String(), "\n")
}

// hasToolPromptInjected 探测请求 messages 是否已经包含工具 prompt 痕迹，避免重复注入。
// 复用 Chat2API utils/tools.ts hasToolPromptInjected 简化版：扫描 system 消息
// 是否含 "[function_calls]"。
func hasToolPromptInjected(messages []model.ChatCompletionMessage) bool {
	for _, m := range messages {
		if m.Role != model.ChatMessageRoleSystem && m.Role != model.ChatMessageRoleDeveloper {
			continue
		}
		if text := messageText(m); strings.Contains(text, "[function_calls]") {
			return true
		}
	}
	return false
}

// formatAssistantToolCalls 把 assistant 历史消息里的 tool_calls 折成纯文本片段，
// 让上游 LLM 看到模型上一轮发起了哪些工具调用。
func formatAssistantToolCalls(calls []model.ToolCall) string {
	if len(calls) == 0 {
		return ""
	}
	var sb strings.Builder
	sb.WriteString("Assistant: [function_calls]\n")
	for i, c := range calls {
		if i > 0 {
			sb.WriteString("\n")
		}
		args := c.Function.Arguments
		if args == "" {
			args = "{}"
		}
		sb.WriteString(fmt.Sprintf(`{"id":%q,"name":%q,"arguments":%s}`, c.ID, c.Function.Name, args))
	}
	sb.WriteString("\n[/function_calls]")
	return sb.String()
}

// formatToolResult 把 tool role 的回包折成 "tool_result(<id>): <content>" 文本。
func formatToolResult(toolCallID, content string) string {
	return fmt.Sprintf("tool_result(%s): %s", toolCallID, content)
}
