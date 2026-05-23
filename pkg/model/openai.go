package model

// openai.go defines OpenAI Chat Completions / Completions / streaming /
// tool-call related types used by the sekiro chat completions HTTP layer.
// The shapes mirror github.com/sashabaranov/go-openai but are kept dependency
// free so they can be reused inside server handlers, model layer and tests.

import (
	"encoding/json"
	"errors"
)

// Chat message roles defined by the OpenAI API.
const (
	ChatMessageRoleSystem    = "system"
	ChatMessageRoleUser      = "user"
	ChatMessageRoleAssistant = "assistant"
	ChatMessageRoleFunction  = "function"
	ChatMessageRoleTool      = "tool"
	ChatMessageRoleDeveloper = "developer"
)

// ErrContentFieldsMisused is returned when both Content and MultiContent are
// provided on a ChatCompletionMessage at the same time.
var ErrContentFieldsMisused = errors.New("can't use both Content and MultiContent properties simultaneously")

// ---------------------------------------------------------------------------
// Usage
// ---------------------------------------------------------------------------

// Usage represents the total token usage per request to OpenAI.
type Usage struct {
	PromptTokens            int                      `json:"prompt_tokens"`
	CompletionTokens        int                      `json:"completion_tokens"`
	TotalTokens             int                      `json:"total_tokens"`
	PromptTokensDetails     *PromptTokensDetails     `json:"prompt_tokens_details,omitempty"`
	CompletionTokensDetails *CompletionTokensDetails `json:"completion_tokens_details,omitempty"`
}

// CompletionTokensDetails breakdowns tokens used in a completion.
type CompletionTokensDetails struct {
	AudioTokens              int `json:"audio_tokens"`
	ReasoningTokens          int `json:"reasoning_tokens"`
	AcceptedPredictionTokens int `json:"accepted_prediction_tokens"`
	RejectedPredictionTokens int `json:"rejected_prediction_tokens"`
}

// PromptTokensDetails breakdowns tokens used in the prompt.
type PromptTokensDetails struct {
	AudioTokens  int `json:"audio_tokens"`
	CachedTokens int `json:"cached_tokens"`
}

// ---------------------------------------------------------------------------
// Content filter / annotation
// ---------------------------------------------------------------------------

type Hate struct {
	Filtered bool   `json:"filtered"`
	Severity string `json:"severity,omitempty"`
}

type SelfHarm struct {
	Filtered bool   `json:"filtered"`
	Severity string `json:"severity,omitempty"`
}

type Sexual struct {
	Filtered bool   `json:"filtered"`
	Severity string `json:"severity,omitempty"`
}

type Violence struct {
	Filtered bool   `json:"filtered"`
	Severity string `json:"severity,omitempty"`
}

type JailBreak struct {
	Filtered bool `json:"filtered"`
	Detected bool `json:"detected"`
}

type Profanity struct {
	Filtered bool `json:"filtered"`
	Detected bool `json:"detected"`
}

type ContentFilterResults struct {
	Hate      Hate      `json:"hate,omitempty"`
	SelfHarm  SelfHarm  `json:"self_harm,omitempty"`
	Sexual    Sexual    `json:"sexual,omitempty"`
	Violence  Violence  `json:"violence,omitempty"`
	JailBreak JailBreak `json:"jailbreak,omitempty"`
	Profanity Profanity `json:"profanity,omitempty"`
}

type PromptAnnotation struct {
	PromptIndex          int                  `json:"prompt_index,omitempty"`
	ContentFilterResults ContentFilterResults `json:"content_filter_results,omitempty"`
}

type PromptFilterResult struct {
	Index                int                  `json:"index"`
	ContentFilterResults ContentFilterResults `json:"content_filter_results,omitempty"`
}

// ---------------------------------------------------------------------------
// Multi-modal content parts
// ---------------------------------------------------------------------------

type ImageURLDetail string

const (
	ImageURLDetailHigh ImageURLDetail = "high"
	ImageURLDetailLow  ImageURLDetail = "low"
	ImageURLDetailAuto ImageURLDetail = "auto"
)

type ChatMessageImageURL struct {
	URL    string         `json:"url,omitempty"`
	Detail ImageURLDetail `json:"detail,omitempty"`
}

type ChatMessagePartType string

const (
	ChatMessagePartTypeText     ChatMessagePartType = "text"
	ChatMessagePartTypeImageURL ChatMessagePartType = "image_url"
)

type ChatMessagePart struct {
	Type     ChatMessagePartType  `json:"type,omitempty"`
	Text     string               `json:"text,omitempty"`
	ImageURL *ChatMessageImageURL `json:"image_url,omitempty"`
}

// ---------------------------------------------------------------------------
// Tool calls / function calls
// ---------------------------------------------------------------------------

type ToolType string

const (
	ToolTypeFunction ToolType = "function"
)

type Tool struct {
	Type     ToolType            `json:"type"`
	Function *FunctionDefinition `json:"function,omitempty"`
}

type ToolChoice struct {
	Type     ToolType     `json:"type"`
	Function ToolFunction `json:"function,omitempty"`
}

type ToolFunction struct {
	Name string `json:"name"`
}

type ToolCall struct {
	// Index is non-nil only inside chat completion stream chunks.
	Index    *int         `json:"index,omitempty"`
	ID       string       `json:"id,omitempty"`
	Type     ToolType     `json:"type"`
	Function FunctionCall `json:"function"`
}

type FunctionCall struct {
	Name string `json:"name,omitempty"`
	// Arguments holds the function call arguments as a JSON-encoded string.
	Arguments string `json:"arguments,omitempty"`
}

type FunctionDefinition struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Strict      bool   `json:"strict,omitempty"`
	// Parameters describes the function schema. Pass json.RawMessage for a
	// pre-built JSON Schema, or any value that serializes to a JSON Schema
	// object.
	Parameters any `json:"parameters"`
}

// FunctionDefine is kept as an alias for backwards compatibility.
//
// Deprecated: use FunctionDefinition instead.
type FunctionDefine = FunctionDefinition

// ---------------------------------------------------------------------------
// Chat completion message
// ---------------------------------------------------------------------------

type ChatCompletionMessage struct {
	Role         string `json:"role"`
	Content      string `json:"content,omitempty"`
	Refusal      string `json:"refusal,omitempty"`
	MultiContent []ChatMessagePart

	// Name is documented in the OpenAI Python library and chatml spec.
	Name string `json:"name,omitempty"`

	// ReasoningContent is used by deepseek-reasoner / qwen reasoning models.
	ReasoningContent string `json:"reasoning_content,omitempty"`

	FunctionCall *FunctionCall `json:"function_call,omitempty"`

	// ToolCalls is set on assistant messages to surface model-generated tool
	// calls (function calls).
	ToolCalls []ToolCall `json:"tool_calls,omitempty"`

	// ToolCallID is set on tool messages and links the tool result back to
	// the originating assistant tool call.
	ToolCallID string `json:"tool_call_id,omitempty"`
}

func (m ChatCompletionMessage) MarshalJSON() ([]byte, error) {
	if m.Content != "" && m.MultiContent != nil {
		return nil, ErrContentFieldsMisused
	}
	if len(m.MultiContent) > 0 {
		msg := struct {
			Role             string            `json:"role"`
			Content          string            `json:"-"`
			Refusal          string            `json:"refusal,omitempty"`
			MultiContent     []ChatMessagePart `json:"content,omitempty"`
			Name             string            `json:"name,omitempty"`
			ReasoningContent string            `json:"reasoning_content,omitempty"`
			FunctionCall     *FunctionCall     `json:"function_call,omitempty"`
			ToolCalls        []ToolCall        `json:"tool_calls,omitempty"`
			ToolCallID       string            `json:"tool_call_id,omitempty"`
		}(m)
		return json.Marshal(msg)
	}

	msg := struct {
		Role             string            `json:"role"`
		Content          string            `json:"content,omitempty"`
		Refusal          string            `json:"refusal,omitempty"`
		MultiContent     []ChatMessagePart `json:"-"`
		Name             string            `json:"name,omitempty"`
		ReasoningContent string            `json:"reasoning_content,omitempty"`
		FunctionCall     *FunctionCall     `json:"function_call,omitempty"`
		ToolCalls        []ToolCall        `json:"tool_calls,omitempty"`
		ToolCallID       string            `json:"tool_call_id,omitempty"`
	}(m)
	return json.Marshal(msg)
}

func (m *ChatCompletionMessage) UnmarshalJSON(bs []byte) error {
	msg := struct {
		Role             string `json:"role"`
		Content          string `json:"content"`
		Refusal          string `json:"refusal,omitempty"`
		MultiContent     []ChatMessagePart
		Name             string        `json:"name,omitempty"`
		ReasoningContent string        `json:"reasoning_content,omitempty"`
		FunctionCall     *FunctionCall `json:"function_call,omitempty"`
		ToolCalls        []ToolCall    `json:"tool_calls,omitempty"`
		ToolCallID       string        `json:"tool_call_id,omitempty"`
	}{}

	if err := json.Unmarshal(bs, &msg); err == nil {
		*m = ChatCompletionMessage(msg)
		return nil
	}
	multiMsg := struct {
		Role             string `json:"role"`
		Content          string
		Refusal          string            `json:"refusal,omitempty"`
		MultiContent     []ChatMessagePart `json:"content"`
		Name             string            `json:"name,omitempty"`
		ReasoningContent string            `json:"reasoning_content,omitempty"`
		FunctionCall     *FunctionCall     `json:"function_call,omitempty"`
		ToolCalls        []ToolCall        `json:"tool_calls,omitempty"`
		ToolCallID       string            `json:"tool_call_id,omitempty"`
	}{}
	if err := json.Unmarshal(bs, &multiMsg); err != nil {
		return err
	}
	*m = ChatCompletionMessage(multiMsg)
	return nil
}

// ---------------------------------------------------------------------------
// Response format / structured output
// ---------------------------------------------------------------------------

type ChatCompletionResponseFormatType string

const (
	ChatCompletionResponseFormatTypeJSONObject ChatCompletionResponseFormatType = "json_object"
	ChatCompletionResponseFormatTypeJSONSchema ChatCompletionResponseFormatType = "json_schema"
	ChatCompletionResponseFormatTypeText       ChatCompletionResponseFormatType = "text"
)

type ChatCompletionResponseFormat struct {
	Type       ChatCompletionResponseFormatType        `json:"type,omitempty"`
	JSONSchema *ChatCompletionResponseFormatJSONSchema `json:"json_schema,omitempty"`
}

// ChatCompletionResponseFormatJSONSchema mirrors the OpenAI structured output
// schema descriptor. Schema is kept as a raw JSON value so callers can pass
// any pre-built JSON Schema (json.RawMessage, struct that marshals to one,
// etc.) without depending on the go-openai internal jsonschema package.
type ChatCompletionResponseFormatJSONSchema struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	Schema      json.RawMessage `json:"schema"`
	Strict      bool            `json:"strict"`
}

// ---------------------------------------------------------------------------
// Streaming options / extensions / prediction / verbosity
// ---------------------------------------------------------------------------

type StreamOptions struct {
	// IncludeUsage requests a final chunk that contains aggregated token
	// usage. All preceding chunks then carry a null usage field.
	IncludeUsage bool `json:"include_usage,omitempty"`
}

// ChatCompletionRequestExtensions contains third-party OpenAI API extensions
// (e.g., vendor-specific implementations like vLLM).
type ChatCompletionRequestExtensions struct {
	// GuidedChoice is a vLLM extension that constrains the model's output to
	// one of the predefined string choices.
	GuidedChoice []string `json:"guided_choice,omitempty"`
}

type Prediction struct {
	Content string `json:"content"`
	Type    string `json:"type"`
}

type ServiceTier string

const (
	ServiceTierAuto     ServiceTier = "auto"
	ServiceTierDefault  ServiceTier = "default"
	ServiceTierFlex     ServiceTier = "flex"
	ServiceTierPriority ServiceTier = "priority"
)

// ---------------------------------------------------------------------------
// Chat completion request / response
// ---------------------------------------------------------------------------

// ChatCompletionRequest represents a request structure for the chat
// completion API.
type ChatCompletionRequest struct {
	Model    string                  `json:"model"`
	Messages []ChatCompletionMessage `json:"messages"`
	// MaxTokens is the maximum number of tokens that can be generated in the
	// chat completion. Deprecated: use MaxCompletionTokens. Not compatible
	// with o1-series models.
	MaxTokens int `json:"max_tokens,omitempty"`
	// MaxCompletionTokens is an upper bound for tokens generated for a
	// completion, including visible output tokens and reasoning tokens.
	MaxCompletionTokens int                           `json:"max_completion_tokens,omitempty"`
	Temperature         float32                       `json:"temperature,omitempty"`
	TopP                float32                       `json:"top_p,omitempty"`
	N                   int                           `json:"n,omitempty"`
	Stream              bool                          `json:"stream,omitempty"`
	Stop                []string                      `json:"stop,omitempty"`
	PresencePenalty     float32                       `json:"presence_penalty,omitempty"`
	ResponseFormat      *ChatCompletionResponseFormat `json:"response_format,omitempty"`
	Seed                *int                          `json:"seed,omitempty"`
	FrequencyPenalty    float32                       `json:"frequency_penalty,omitempty"`
	// LogitBias keys must be token ID strings (not raw words).
	LogitBias map[string]int `json:"logit_bias,omitempty"`
	// LogProbs toggles returning log probabilities of the output tokens.
	LogProbs bool `json:"logprobs,omitempty"`
	// TopLogProbs is an integer between 0 and 5 specifying the number of most
	// likely tokens to return at each token position. Requires LogProbs=true.
	TopLogProbs int    `json:"top_logprobs,omitempty"`
	User        string `json:"user,omitempty"`
	// Functions is deprecated: use Tools instead.
	Functions []FunctionDefinition `json:"functions,omitempty"`
	// FunctionCall is deprecated: use ToolChoice instead.
	FunctionCall any    `json:"function_call,omitempty"`
	Tools        []Tool `json:"tools,omitempty"`
	// ToolChoice is either a string ("auto"/"none"/...) or a ToolChoice value.
	ToolChoice any `json:"tool_choice,omitempty"`
	// StreamOptions tunes streaming behavior. Only set when Stream=true.
	StreamOptions *StreamOptions `json:"stream_options,omitempty"`
	// ParallelToolCalls disables parallel tool calling when set to false.
	ParallelToolCalls any `json:"parallel_tool_calls,omitempty"`
	// Store opts the request into OpenAI's distillation/eval storage.
	Store bool `json:"store,omitempty"`
	// ReasoningEffort controls reasoning effort: "low", "medium", "high".
	ReasoningEffort string `json:"reasoning_effort,omitempty"`
	// Metadata is stored alongside the completion.
	Metadata map[string]string `json:"metadata,omitempty"`
	// Prediction supplies a predicted output for speculative decoding.
	Prediction *Prediction `json:"prediction,omitempty"`
	// ChatTemplateKwargs adds non-standard kwargs forwarded to the chat
	// template renderer (e.g., qwen3 think mode).
	ChatTemplateKwargs map[string]any `json:"chat_template_kwargs,omitempty"`
	// ServiceTier selects the latency tier used for processing the request.
	ServiceTier ServiceTier `json:"service_tier,omitempty"`
	// Verbosity controls how many output tokens are generated; supported
	// values are "low", "medium", "high".
	Verbosity string `json:"verbosity,omitempty"`
	// SafetyIdentifier is a stable per-user identifier for abuse detection.
	SafetyIdentifier string `json:"safety_identifier,omitempty"`
	// Embedded struct for non-OpenAI vendor extensions.
	ChatCompletionRequestExtensions
}

type FinishReason string

const (
	FinishReasonStop          FinishReason = "stop"
	FinishReasonLength        FinishReason = "length"
	FinishReasonFunctionCall  FinishReason = "function_call"
	FinishReasonToolCalls     FinishReason = "tool_calls"
	FinishReasonContentFilter FinishReason = "content_filter"
	FinishReasonNull          FinishReason = "null"
)

func (r FinishReason) MarshalJSON() ([]byte, error) {
	if r == FinishReasonNull || r == "" {
		return []byte("null"), nil
	}
	return []byte(`"` + string(r) + `"`), nil
}

type TopLogProbs struct {
	Token   string  `json:"token"`
	LogProb float64 `json:"logprob"`
	Bytes   []byte  `json:"bytes,omitempty"`
}

// LogProb represents the probability information for a token.
type LogProb struct {
	Token       string        `json:"token"`
	LogProb     float64       `json:"logprob"`
	Bytes       []byte        `json:"bytes,omitempty"`
	TopLogProbs []TopLogProbs `json:"top_logprobs"`
}

// LogProbs is the top-level structure containing log probability information.
type LogProbs struct {
	Content []LogProb `json:"content"`
}

type ChatCompletionChoice struct {
	Index   int                   `json:"index"`
	Message ChatCompletionMessage `json:"message"`
	// FinishReason
	// stop:           normal completion or stopped at a stop sequence
	// length:         truncated due to max_tokens
	// function_call:  the model decided to call a function
	// tool_calls:     the model decided to call tools
	// content_filter: omitted content due to a content filter
	// null:           response still in progress
	FinishReason         FinishReason         `json:"finish_reason"`
	LogProbs             *LogProbs            `json:"logprobs,omitempty"`
	ContentFilterResults ContentFilterResults `json:"content_filter_results,omitempty"`
}

// ChatCompletionResponse represents a response structure for the chat
// completion API.
type ChatCompletionResponse struct {
	ID                  string                 `json:"id"`
	Object              string                 `json:"object"`
	Created             int64                  `json:"created"`
	Model               string                 `json:"model"`
	Choices             []ChatCompletionChoice `json:"choices"`
	Usage               Usage                  `json:"usage"`
	SystemFingerprint   string                 `json:"system_fingerprint"`
	PromptFilterResults []PromptFilterResult   `json:"prompt_filter_results,omitempty"`
	ServiceTier         ServiceTier            `json:"service_tier,omitempty"`
}

// ---------------------------------------------------------------------------
// Chat completion stream
// ---------------------------------------------------------------------------

type ChatCompletionStreamChoiceDelta struct {
	Content      string        `json:"content,omitempty"`
	Role         string        `json:"role,omitempty"`
	FunctionCall *FunctionCall `json:"function_call,omitempty"`
	ToolCalls    []ToolCall    `json:"tool_calls,omitempty"`
	Refusal      string        `json:"refusal,omitempty"`

	// ReasoningContent is used by deepseek-reasoner / qwen reasoning models.
	ReasoningContent string `json:"reasoning_content,omitempty"`
}

type ChatCompletionStreamChoiceLogprobs struct {
	Content []ChatCompletionTokenLogprob `json:"content,omitempty"`
	Refusal []ChatCompletionTokenLogprob `json:"refusal,omitempty"`
}

type ChatCompletionTokenLogprob struct {
	Token       string                                 `json:"token"`
	Bytes       []int64                                `json:"bytes,omitempty"`
	Logprob     float64                                `json:"logprob,omitempty"`
	TopLogprobs []ChatCompletionTokenLogprobTopLogprob `json:"top_logprobs"`
}

type ChatCompletionTokenLogprobTopLogprob struct {
	Token   string  `json:"token"`
	Bytes   []int64 `json:"bytes"`
	Logprob float64 `json:"logprob"`
}

type ChatCompletionStreamChoice struct {
	Index                int                                 `json:"index"`
	Delta                ChatCompletionStreamChoiceDelta     `json:"delta"`
	Logprobs             *ChatCompletionStreamChoiceLogprobs `json:"logprobs,omitempty"`
	FinishReason         FinishReason                        `json:"finish_reason"`
	ContentFilterResults ContentFilterResults                `json:"content_filter_results,omitempty"`
}

type ChatCompletionStreamResponse struct {
	ID                  string                       `json:"id"`
	Object              string                       `json:"object"`
	Created             int64                        `json:"created"`
	Model               string                       `json:"model"`
	Choices             []ChatCompletionStreamChoice `json:"choices"`
	SystemFingerprint   string                       `json:"system_fingerprint"`
	PromptAnnotations   []PromptAnnotation           `json:"prompt_annotations,omitempty"`
	PromptFilterResults []PromptFilterResult         `json:"prompt_filter_results,omitempty"`
	// Usage is only populated when stream_options.include_usage=true. When
	// present, every chunk except the last carries a null usage value.
	Usage *Usage `json:"usage,omitempty"`
}

// ---------------------------------------------------------------------------
// Legacy completion (text completion) request / response
// ---------------------------------------------------------------------------

// CompletionRequest represents a request structure for the legacy completion
// API.
type CompletionRequest struct {
	Model            string  `json:"model"`
	Prompt           any     `json:"prompt,omitempty"`
	BestOf           int     `json:"best_of,omitempty"`
	Echo             bool    `json:"echo,omitempty"`
	FrequencyPenalty float32 `json:"frequency_penalty,omitempty"`
	// LogitBias keys must be token ID strings (not raw words).
	LogitBias map[string]int `json:"logit_bias,omitempty"`
	// Store opts the request into OpenAI's distillation/eval storage.
	Store           bool              `json:"store,omitempty"`
	Metadata        map[string]string `json:"metadata,omitempty"`
	LogProbs        int               `json:"logprobs,omitempty"`
	MaxTokens       int               `json:"max_tokens,omitempty"`
	N               int               `json:"n,omitempty"`
	PresencePenalty float32           `json:"presence_penalty,omitempty"`
	Seed            *int              `json:"seed,omitempty"`
	Stop            []string          `json:"stop,omitempty"`
	Stream          bool              `json:"stream,omitempty"`
	Suffix          string            `json:"suffix,omitempty"`
	Temperature     float32           `json:"temperature,omitempty"`
	TopP            float32           `json:"top_p,omitempty"`
	User            string            `json:"user,omitempty"`
	// StreamOptions tunes streaming behavior. Only set when Stream=true.
	StreamOptions *StreamOptions `json:"stream_options,omitempty"`
}

// CompletionChoice represents one of the possible completions.
type CompletionChoice struct {
	Text         string        `json:"text"`
	Index        int           `json:"index"`
	FinishReason string        `json:"finish_reason"`
	LogProbs     LogprobResult `json:"logprobs"`
}

// LogprobResult represents logprob results for a CompletionChoice.
type LogprobResult struct {
	Tokens        []string             `json:"tokens"`
	TokenLogprobs []float32            `json:"token_logprobs"`
	TopLogprobs   []map[string]float32 `json:"top_logprobs"`
	TextOffset    []int                `json:"text_offset"`
}

// CompletionResponse represents a response structure for the legacy
// completion API.
type CompletionResponse struct {
	ID      string             `json:"id"`
	Object  string             `json:"object"`
	Created int64              `json:"created"`
	Model   string             `json:"model"`
	Choices []CompletionChoice `json:"choices"`
	Usage   *Usage             `json:"usage,omitempty"`
}
