package forwarder

import (
	"encoding/base64"
	"testing"
)

func TestDecodeStreamFrame_Empty(t *testing.T) {
	got, err := DecodeStreamFrame(nil)
	if err != nil {
		t.Fatalf("nil input: unexpected error %v", err)
	}
	if got == nil || len(got.Bytes) != 0 || got.Done {
		t.Fatalf("nil input: want empty frame, got %+v", got)
	}

	got, err = DecodeStreamFrame([]byte{})
	if err != nil {
		t.Fatalf("empty input: unexpected error %v", err)
	}
	if len(got.Bytes) != 0 {
		t.Fatalf("empty input: want zero bytes, got %d", len(got.Bytes))
	}
}

func TestDecodeStreamFrame_StructuredChunk(t *testing.T) {
	raw := []byte(`{"sequence":"qwen-test-1","type":"chunk","data":"aGVsbG8=","encoding":"identity","done":false}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got.Bytes) != "hello" {
		t.Fatalf("want bytes=hello, got %q", string(got.Bytes))
	}
	if got.Encoding != "identity" {
		t.Fatalf("want encoding=identity, got %q", got.Encoding)
	}
	if got.Done {
		t.Fatalf("want done=false")
	}
}

func TestDecodeStreamFrame_DefaultEncoding(t *testing.T) {
	raw := []byte(`{"type":"chunk","data":"YWJj"}`)
	got, _ := DecodeStreamFrame(raw)
	if got.Encoding != "identity" {
		t.Fatalf("want default encoding=identity, got %q", got.Encoding)
	}
	if string(got.Bytes) != "abc" {
		t.Fatalf("want abc, got %q", string(got.Bytes))
	}
}

func TestDecodeStreamFrame_EmptyType_TreatedAsChunk(t *testing.T) {
	raw := []byte(`{"data":"YWJj"}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("empty type with data: unexpected error %v", err)
	}
	if string(got.Bytes) != "abc" {
		t.Fatalf("want abc, got %q", string(got.Bytes))
	}
}

func TestDecodeStreamFrame_End(t *testing.T) {
	raw := []byte(`{"type":"end"}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !got.Done {
		t.Fatalf("end frame should mark done")
	}
	if len(got.Bytes) != 0 {
		t.Fatalf("end frame should have no bytes")
	}
}

func TestDecodeStreamFrame_Error(t *testing.T) {
	raw := []byte(`{"type":"error","error":"upstream 401"}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !got.Done {
		t.Fatalf("error frame should mark done")
	}
	if got.Error != "upstream 401" {
		t.Fatalf("want error=upstream 401, got %q", got.Error)
	}
}

func TestDecodeStreamFrame_LegacyBase64String(t *testing.T) {
	encoded := base64.StdEncoding.EncodeToString([]byte("legacy"))
	raw := []byte(`"` + encoded + `"`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got.Bytes) != "legacy" {
		t.Fatalf("want bytes=legacy, got %q", string(got.Bytes))
	}
	if got.Encoding != "identity" {
		t.Fatalf("want encoding=identity, got %q", got.Encoding)
	}
}

func TestDecodeStreamFrame_LegacyPlainString(t *testing.T) {
	// 既不是 valid JSON object 也不是 valid base64：兜底当字符串透传
	raw := []byte(`"not!base64!"`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// "not!base64!" 实际上能被 base64 标准库忽略某些字符，但不严格相等；
	// 我们只校验不 panic、Encoding 落到 identity。
	if got.Encoding != "identity" {
		t.Fatalf("want encoding=identity, got %q", got.Encoding)
	}
}

func TestDecodeStreamFrame_BadBase64(t *testing.T) {
	raw := []byte(`{"type":"chunk","data":"???not_base64???"}`)
	if _, err := DecodeStreamFrame(raw); err == nil {
		t.Fatalf("expected error for bad base64")
	}
}

func TestDecodeStreamFrame_UnknownType(t *testing.T) {
	raw := []byte(`{"type":"weird"}`)
	if _, err := DecodeStreamFrame(raw); err == nil {
		t.Fatalf("expected error for unknown type")
	}
}

func TestDecodeStreamFrame_GzipEncoding(t *testing.T) {
	raw := []byte(`{"type":"chunk","data":"aGVsbG8=","encoding":"gzip"}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Encoding != "gzip" {
		t.Fatalf("want encoding=gzip, got %q", got.Encoding)
	}
	// Bytes 仍未解压；Decoder 自己负责。
	if string(got.Bytes) != "hello" {
		t.Fatalf("want raw bytes preserved, got %q", string(got.Bytes))
	}
}

func TestDecodeStreamFrame_LeadingWhitespace(t *testing.T) {
	raw := []byte("   \n\t" + `{"type":"chunk","data":"YWJj"}`)
	got, err := DecodeStreamFrame(raw)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if string(got.Bytes) != "abc" {
		t.Fatalf("want abc, got %q", string(got.Bytes))
	}
}
