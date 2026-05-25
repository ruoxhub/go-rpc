package claude

import (
	"strings"

	"github.com/mrh30000/go-rpc/internal/promptcompat"
	"github.com/mrh30000/go-rpc/internal/util"
)

func countClaudeInputTokens(stdReq promptcompat.StandardRequest) int {
	promptText := stdReq.PromptTokenText
	if strings.TrimSpace(promptText) == "" {
		promptText = stdReq.FinalPrompt
	}
	return countClaudeInputTokensFromText(promptText, stdReq.ResolvedModel)
}

func countClaudeInputTokensFromText(promptText, model string) int {
	return util.CountPromptTokens(promptText, model)
}
