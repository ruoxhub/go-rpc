package client

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestInvokerHTTPContract(t *testing.T) {
	var method, path, authorization string
	var body map[string]interface{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		method = r.Method
		path = r.URL.Path
		authorization = r.Header.Get("Authorization")
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Errorf("decode request: %v", err)
		}
		_, _ = io.WriteString(w, `{"code":0,"message":"ok","data":{"value":1}}`)
	}))
	defer server.Close()

	invoker := NewRpcInvokerWithToken("test-token", []string{server.URL})
	defer invoker.Destroy()
	resp, err := invoker.InvokeContext(context.Background(), &InvokeRequest{
		Group: "g", Api: "echo", Params: map[string]interface{}{"value": 1}, Timeout: 2 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	if method != http.MethodPost || path != "/business/invoke" || authorization != "Bearer test-token" {
		t.Fatalf("request = %s %s auth=%q", method, path, authorization)
	}
	if body["group"] != "g" || body["action"] != "echo" || body["timeout"] != float64(2) {
		t.Fatalf("request body = %#v", body)
	}
	params, ok := body["params"].(map[string]interface{})
	if !ok || params["value"] != float64(1) {
		t.Fatalf("request params = %#v", body["params"])
	}
	data, ok := resp.Data.(map[string]interface{})
	if !ok || data["value"] != float64(1) || resp.Code != 0 {
		t.Fatalf("response = %#v", resp)
	}
}

func TestInvokerDoesNotRetry(t *testing.T) {
	tests := []struct {
		name   string
		status int
		body   string
	}{
		{name: "non-2xx", status: http.StatusInternalServerError, body: `server error`},
		{name: "invalid json", status: http.StatusOK, body: `{invalid`},
		{name: "business failure", status: http.StatusOK, body: `{"code":123,"message":"failed"}`},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var secondRequests atomic.Int32
			first := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.status)
				_, _ = io.WriteString(w, tt.body)
			}))
			defer first.Close()
			second := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				secondRequests.Add(1)
				_, _ = io.WriteString(w, `{"code":0}`)
			}))
			defer second.Close()

			invoker := NewRpcInvoker([]string{first.URL, second.URL})
			defer invoker.Destroy()
			if _, err := invoker.InvokeContext(context.Background(), &InvokeRequest{Group: "g", Api: "echo"}); err == nil {
				t.Fatal("InvokeContext() error = nil, want failure")
			}
			if got := secondRequests.Load(); got != 0 {
				t.Fatalf("second endpoint requests = %d, want 0", got)
			}
		})
	}
}

func TestInvokerDoesNotRetryTransportFailure(t *testing.T) {
	first := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	firstURL := first.URL
	first.Close()
	var secondRequests atomic.Int32
	second := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		secondRequests.Add(1)
	}))
	defer second.Close()

	invoker := NewRpcInvoker([]string{firstURL, second.URL})
	defer invoker.Destroy()
	if _, err := invoker.InvokeContext(context.Background(), &InvokeRequest{Group: "g", Api: "echo"}); err == nil {
		t.Fatal("InvokeContext() error = nil, want failure")
	}
	if got := secondRequests.Load(); got != 0 {
		t.Fatalf("second endpoint requests = %d, want 0", got)
	}
}

func TestInvokerResponseFallbackAndLimit(t *testing.T) {
	tests := []struct {
		name  string
		body  []byte
		check func(*testing.T, *InvokeResponse)
	}{
		{
			name: "flattened response",
			body: []byte(`{"code":0,"message":"ok","group":"g","clientId":"c","trace_id":"t","value":42}`),
			check: func(t *testing.T, resp *InvokeResponse) {
				data, ok := resp.Data.(map[string]interface{})
				if !ok || data["value"] != float64(42) {
					t.Fatalf("fallback data = %#v", resp.Data)
				}
				if data["code"] != nil || data["message"] != nil || data["group"] != nil || data["clientId"] != nil || data["trace_id"] != nil {
					t.Fatalf("fallback metadata = %#v", data)
				}
				if resp.Raw["value"] != float64(42) || resp.TraceID != "t" {
					t.Fatalf("raw response = %#v", resp)
				}
			},
		},
		{
			name: "response over limit",
			body: bytes.Repeat([]byte("x"), 10<<20+1),
			check: func(t *testing.T, resp *InvokeResponse) {
				t.Fatal("over-limit response unexpectedly succeeded")
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = w.Write(tt.body)
			}))
			defer server.Close()
			invoker := NewRpcInvoker([]string{server.URL})
			defer invoker.Destroy()
			resp, err := invoker.InvokeContext(context.Background(), &InvokeRequest{Group: "g", Api: "echo"})
			if tt.name == "response over limit" {
				if err == nil {
					t.Fatal("InvokeContext() error = nil, want response limit failure")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			tt.check(t, resp)
		})
	}
}

func TestInvokerTimeoutUsesSmallerDeadline(t *testing.T) {
	tests := []struct {
		name       string
		requestCtx time.Duration
		reqTimeout time.Duration
	}{
		{name: "caller context", requestCtx: 40 * time.Millisecond, reqTimeout: time.Second},
		{name: "request timeout", requestCtx: time.Second, reqTimeout: 40 * time.Millisecond},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				time.Sleep(200 * time.Millisecond)
			}))
			defer server.Close()
			invoker := NewRpcInvoker([]string{server.URL})
			defer invoker.Destroy()
			ctx, cancel := context.WithTimeout(context.Background(), tt.requestCtx)
			defer cancel()
			start := time.Now()
			_, err := invoker.InvokeContext(ctx, &InvokeRequest{Group: "g", Api: "echo", Timeout: tt.reqTimeout})
			if err == nil {
				t.Fatal("InvokeContext() error = nil, want timeout")
			}
			if elapsed := time.Since(start); elapsed > 500*time.Millisecond {
				t.Fatalf("timeout took %v", elapsed)
			}
		})
	}
}

func TestNewRpcInvokerDoesNotDial(t *testing.T) {
	invoker := NewRpcInvoker([]string{"127.0.0.1:1"})
	if invoker == nil || len(invoker.serverURLs) != 1 {
		t.Fatalf("invoker = %#v", invoker)
	}
	invoker.Destroy()
}
