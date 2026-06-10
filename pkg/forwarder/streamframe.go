package forwarder

import (
	"bytes"
	"encoding/base64"
	"fmt"

	json "github.com/goccy/go-json"
)

// StreamFramePayload 描述浏览器扩展通过 ws 回传字节流时使用的载荷协议。
//
// 这是 qwen-style provider 的"原始字节回流"契约（spec §5.2 钉死版本）：
// 不引入新的 ws 消息类型；浏览器扩展把以下结构序列化成 JSON，
// 写入现有 invoke_stream 消息的 data 字段（json.RawMessage）。
//
// 现有 invoke_stream 帧本身仍由 server/websocket.handleInvokeStream 处理：
//   - msg.Done / msg.Error 用现有字段
//   - msg.Data 透传到 forwarder.StreamChunk.Data
//
// 因此本结构是 StreamChunk.Data 的"内层"协议。Decoder 调用 DecodeStreamFrame
// 把 InvokeResponse/StreamChunk.Data 还原成原始 SSE 字节。
//
// 字段说明：
//   - Type: "chunk" 表示一段字节；"end" 表示流正常结束；"error" 表示上游错误。
//     兼容旧浏览器扩展：当 Type 为空且 Data 非空时按 "chunk" 处理。
//   - Data: 原始字节的 base64 编码。仅 Type=="chunk" 时有意义。
//     编码方式由 Encoding 指明，默认 "identity"。
//   - Encoding: 字节编码。"identity" / "gzip" / "br" / "zstd" 之一。浏览器
//     fetch 默认会自动解压上游响应，所以正常情况下永远是 "identity"。保留
//     此字段是为应对未来浏览器禁用自动解压或服务端做端到端透传的场景。
//   - Done: 是否是流的最后一帧。Type=="end"/"error" 时由上游隐含 true。
//   - Error: 错误描述。仅 Type=="error" 时有意义。
type StreamFramePayload struct {
	Sequence string `json:"sequence,omitempty"`
	Type     string `json:"type,omitempty"`
	Data     string `json:"data,omitempty"`
	Encoding string `json:"encoding,omitempty"`
	Done     bool   `json:"done,omitempty"`
	Error    string `json:"error,omitempty"`
}

// DecodedFrame 是解析 + base64 解码后的浏览器侧字节帧。
type DecodedFrame struct {
	// Bytes 是原始上游字节。Encoding 指明这些字节是否仍处于压缩状态。
	Bytes []byte
	// Encoding 见 StreamFramePayload.Encoding。
	Encoding string
	// Done 是否是流的最后一帧。
	Done bool
	// Error 流级错误。非空时 Bytes 应忽略。
	Error string
}

// DecodeStreamFrame 把 StreamChunk.Data（或 InvokeResponse.Data）还原成 DecodedFrame。
//
// 入参 raw 必须是 ws invoke_stream/invoke_response 消息的 data 字段原文。允许形态：
//
//  1. 完整 StreamFramePayload JSON：
//     { "type":"chunk", "data":"<base64>", "encoding":"identity", "done":false }
//
//  2. 兼容旧扩展：纯字符串 base64（直接是 base64-encoded 字节，不带外层 JSON 结构），
//     视为 type=chunk、encoding=identity。
//
//  3. nil / 空字节：返回空 DecodedFrame，Done=false。
//
// 解析失败时返回 error，调用方应把流标记为 decode 失败而非 panic。
func DecodeStreamFrame(raw []byte) (*DecodedFrame, error) {
	if len(raw) == 0 {
		return &DecodedFrame{}, nil
	}

	// 优先按 StreamFramePayload 解析。raw 是 RawMessage，浏览器把字段对象塞进
	// data 时它会是 {...}；如果直接是字符串则首字节是 '"'。
	trimmed := bytes.TrimLeft(raw, " \t\r\n")
	if len(trimmed) > 0 && trimmed[0] == '{' {
		var payload StreamFramePayload
		if err := json.Unmarshal(raw, &payload); err != nil {
			return nil, fmt.Errorf("decode stream frame: %w", err)
		}
		return decodePayload(&payload)
	}

	// 兼容路径：纯字符串 base64 或纯字符串 plain text（极少见）。
	if len(trimmed) > 0 && trimmed[0] == '"' {
		var s string
		if err := json.Unmarshal(raw, &s); err != nil {
			return nil, fmt.Errorf("decode stream frame string: %w", err)
		}
		bytes, err := base64.StdEncoding.DecodeString(s)
		if err != nil {
			// 如果解 base64 失败，按"普通字符串"原样返回（极少数旧客户端）。
			return &DecodedFrame{
				Bytes:    []byte(s),
				Encoding: "identity",
			}, nil
		}
		return &DecodedFrame{
			Bytes:    bytes,
			Encoding: "identity",
		}, nil
	}

	// 既非 JSON object 也非 JSON string，把整段当作原始字节透传。这种情况
	// 不在 spec 范围内但保留兜底以避免 panic。
	return &DecodedFrame{
		Bytes:    raw,
		Encoding: "identity",
	}, nil
}

func decodePayload(p *StreamFramePayload) (*DecodedFrame, error) {
	frame := &DecodedFrame{
		Encoding: defaultEncoding(p.Encoding),
		Done:     p.Done,
		Error:    p.Error,
	}

	switch p.Type {
	case "", "chunk":
		// 兼容空 Type：当 Data 非空时按 chunk 处理。
		if p.Data == "" {
			return frame, nil
		}
		bytes, err := base64.StdEncoding.DecodeString(p.Data)
		if err != nil {
			return nil, fmt.Errorf("decode stream frame base64: %w", err)
		}
		frame.Bytes = bytes
		return frame, nil
	case "end":
		frame.Done = true
		return frame, nil
	case "error":
		frame.Done = true
		if frame.Error == "" {
			frame.Error = "stream upstream error"
		}
		return frame, nil
	default:
		return nil, fmt.Errorf("decode stream frame: unknown type %q", p.Type)
	}
}

func defaultEncoding(s string) string {
	if s == "" {
		return "identity"
	}
	return s
}
