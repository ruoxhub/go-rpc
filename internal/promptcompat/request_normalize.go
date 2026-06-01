package promptcompat

import (
	"fmt"
	"strings"

	"github.com/mrh30000/go-rpc/internal/config"
	"github.com/mrh30000/go-rpc/internal/util"
)

type ConfigReader interface {
	ModelAliases() map[string]string
}

func NormalizeOpenAIChatRequest(store ConfigReader, req map[string]any, traceID string) (StandardRequest, error) {
	model, _ := req["model"].(string)
	messagesRaw, _ := req["messages"].([]any)
	if strings.TrimSpace(model) == "" || len(messagesRaw) == 0 {
		return StandardRequest{}, fmt.Errorf("request must include 'model' and 'messages'")
	}
	resolvedModel, ok := config.ResolveModel(store, model)
	if !ok {
		return StandardRequest{}, fmt.Errorf("model %q is not available", model)
	}
	defaultThinkingEnabled, searchEnabled, _ := config.GetModelConfig(resolvedModel)
	thinkingEnabled := util.ResolveThinkingEnabled(req, defaultThinkingEnabled)
	if config.IsNoThinkingModel(resolvedModel) {
		thinkingEnabled = false
	}
	responseModel := strings.TrimSpace(model)
	if responseModel == "" {
		responseModel = resolvedModel
	}
	toolPolicy := DefaultToolChoicePolicy()
	finalPrompt, toolNames := BuildOpenAIPrompt(messagesRaw, req["tools"], traceID, toolPolicy, thinkingEnabled)
	toolNames = ensureToolDetectionEnabled(toolNames, req["tools"])
	passThrough := collectOpenAIChatPassThrough(req)
	refFileIDs := CollectOpenAIRefFileIDs(req)

	return StandardRequest{
		Surface:         "openai_chat",
		RequestedModel:  strings.TrimSpace(model),
		ResolvedModel:   resolvedModel,
		ResponseModel:   responseModel,
		Messages:        messagesRaw,
		PromptTokenText: finalPrompt,
		ToolsRaw:        req["tools"],
		FinalPrompt:     finalPrompt,
		ToolNames:       toolNames,
		ToolChoice:      toolPolicy,
		Stream:          util.ToBool(req["stream"]),
		Thinking:        thinkingEnabled,
		Search:          searchEnabled,
		RefFileIDs:      refFileIDs,
		RefFileTokens:   estimateInlineFileTokens(req),
		PassThrough:     passThrough,
	}, nil
}

func ensureToolDetectionEnabled(toolNames []string, toolsRaw any) []string {
	if len(toolNames) > 0 {
		return toolNames
	}
	tools, _ := toolsRaw.([]any)
	if len(tools) == 0 {
		return toolNames
	}
	return []string{"__any_tool__"}
}

func collectOpenAIChatPassThrough(req map[string]any) map[string]any {
	out := map[string]any{}
	for _, k := range []string{
		"temperature",
		"top_p",
		"max_tokens",
		"max_completion_tokens",
		"presence_penalty",
		"frequency_penalty",
		"stop",
	} {
		if v, ok := req[k]; ok {
			out[k] = v
		}
	}
	return out
}



func extractDeclaredToolNames(toolsRaw any) []string {
	tools, ok := toolsRaw.([]any)
	if !ok || len(tools) == 0 {
		return nil
	}
	out := make([]string, 0, len(tools))
	seen := map[string]struct{}{}
	for _, t := range tools {
		tool, ok := t.(map[string]any)
		if !ok {
			continue
		}
		fn, _ := tool["function"].(map[string]any)
		if len(fn) == 0 {
			fn = tool
		}
		name := strings.TrimSpace(asString(fn["name"]))
		if name == "" {
			continue
		}
		if _, ok := seen[name]; ok {
			continue
		}
		seen[name] = struct{}{}
		out = append(out, name)
	}
	return out
}

func namesToSet(names []string) map[string]struct{} {
	if len(names) == 0 {
		return nil
	}
	out := make(map[string]struct{}, len(names))
	for _, name := range names {
		trimmed := strings.TrimSpace(name)
		if trimmed == "" {
			continue
		}
		out[trimmed] = struct{}{}
	}
	if len(out) == 0 {
		return nil
	}
	return out
}

// estimateInlineFileTokens extracts the byte count stashed by PreprocessInlineFileInputs
// and converts it to a conservative token estimate. Inline files are typically images or
// documents that the upstream model will process; we use bytes/3 (rather than bytes/4)
// as a slightly pessimistic approximation so the returned context token count stays
// safely above the real value.
func estimateInlineFileTokens(req map[string]any) int {
	raw, ok := req["_inline_file_bytes"]
	if !ok {
		return 0
	}
	var bytes int
	switch v := raw.(type) {
	case int:
		bytes = v
	case int64:
		bytes = int(v)
	case float64:
		bytes = int(v)
	default:
		return 0
	}
	if bytes <= 0 {
		return 0
	}
	return bytes / 3
}
