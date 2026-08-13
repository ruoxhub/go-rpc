package client

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"
)

const maxInvokeResponseSize = 10 << 20

// RpcInvoker represents an HTTP RPC invoker.
type RpcInvoker struct {
	apiToken   string
	serverURLs []*url.URL
	httpClient *http.Client
	next       atomic.Uint64
}

// InvokeRequest represents an invoke request.
type InvokeRequest struct {
	Group   string
	Api     string
	Params  map[string]interface{}
	Timeout time.Duration
}

// InvokeResponse represents an invoke response.
type InvokeResponse struct {
	Code     int                    `json:"code"`
	Message  string                 `json:"message"`
	Data     interface{}            `json:"data"`
	Group    string                 `json:"group"`
	ClientID string                 `json:"clientId"`
	TraceID  string                 `json:"trace_id"`
	Raw      map[string]interface{} `json:"-"`
}

// NewRpcInvoker creates a new RpcInvoker.
func NewRpcInvoker(serverList []string) *RpcInvoker {
	return NewRpcInvokerWithToken("", serverList)
}

// NewRpcInvokerWithToken creates a new RpcInvoker with API token.
func NewRpcInvokerWithToken(apiToken string, serverList []string) *RpcInvoker {
	invoker := &RpcInvoker{
		apiToken:   apiToken,
		serverURLs: make([]*url.URL, 0, len(serverList)),
		httpClient: &http.Client{Transport: &http.Transport{}},
	}
	for _, raw := range serverList {
		if server, err := normalizeServer(raw); err == nil {
			invoker.serverURLs = append(invoker.serverURLs, server)
		}
	}
	return invoker
}

func normalizeServer(raw string) (*url.URL, error) {
	if !strings.Contains(raw, "://") {
		raw = "http://" + raw
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return nil, fmt.Errorf("invalid server address %q", raw)
	}
	u.Path = strings.TrimRight(u.Path, "/")
	return u, nil
}

// Invoke sends one HTTP invoke request.
func (s *RpcInvoker) Invoke(req *InvokeRequest) (*InvokeResponse, error) {
	return s.InvokeContext(context.Background(), req)
}

// InvokeContext sends one HTTP invoke request using ctx for cancellation.
func (s *RpcInvoker) InvokeContext(ctx context.Context, req *InvokeRequest) (*InvokeResponse, error) {
	if req == nil {
		return nil, errors.New("invoke request is nil")
	}
	server := s.nextServer()
	if server == nil {
		return nil, errors.New("no available server")
	}

	payload := map[string]interface{}{
		"group":  req.Group,
		"action": req.Api,
		"params": req.Params,
	}
	if req.Timeout > 0 {
		payload["timeout"] = int(math.Ceil(req.Timeout.Seconds()))
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal invoke request: %w", err)
	}

	if ctx == nil {
		ctx = context.Background()
	}
	requestCtx := ctx
	var cancel context.CancelFunc
	if req.Timeout > 0 {
		requestCtx, cancel = context.WithTimeout(ctx, req.Timeout)
		defer cancel()
	}
	endpoint := *server
	endpoint.Path = strings.TrimRight(server.Path, "/") + "/business/invoke"
	endpoint.RawPath = ""
	request, err := http.NewRequestWithContext(requestCtx, http.MethodPost, endpoint.String(), strings.NewReader(string(body)))
	if err != nil {
		return nil, fmt.Errorf("create invoke request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	if s.apiToken != "" {
		request.Header.Set("Authorization", "Bearer "+s.apiToken)
	}

	response, err := s.httpClient.Do(request)
	if err != nil {
		return nil, fmt.Errorf("send invoke request: %w", err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, maxInvokeResponseSize+1))
	if err != nil {
		return nil, fmt.Errorf("read invoke response: %w", err)
	}
	if len(responseBody) > maxInvokeResponseSize {
		return nil, fmt.Errorf("invoke response exceeds %d bytes", maxInvokeResponseSize)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf("invoke returned HTTP status %s", response.Status)
	}

	var result InvokeResponse
	if err := json.Unmarshal(responseBody, &result); err != nil {
		return nil, fmt.Errorf("decode invoke response: %w", err)
	}
	if err := json.Unmarshal(responseBody, &result.Raw); err != nil {
		return nil, fmt.Errorf("decode invoke response fields: %w", err)
	}
	if _, ok := result.Raw["data"]; !ok {
		result.Data = responseDataWithoutMetadata(result.Raw)
	}
	if result.Code != 0 {
		return &result, fmt.Errorf("invoke failed: code=%d message=%s", result.Code, result.Message)
	}
	return &result, nil
}

func (s *RpcInvoker) nextServer() *url.URL {
	if len(s.serverURLs) == 0 {
		return nil
	}
	index := (s.next.Add(1) - 1) % uint64(len(s.serverURLs))
	return s.serverURLs[index]
}

func responseDataWithoutMetadata(raw map[string]interface{}) map[string]interface{} {
	data := make(map[string]interface{}, len(raw))
	for key, value := range raw {
		switch key {
		case "code", "message", "group", "clientId", "trace_id":
			continue
		default:
			data[key] = value
		}
	}
	return data
}

// Destroy closes idle HTTP connections owned by the invoker.
func (s *RpcInvoker) Destroy() {
	if s.httpClient != nil {
		s.httpClient.CloseIdleConnections()
	}
}
