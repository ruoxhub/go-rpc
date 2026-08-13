package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	client "github.com/mrh30000/go-rpc/pkg/client/sdk"
	"github.com/mrh30000/go-rpc/pkg/protocol"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	baseURL := os.Getenv("RPC_TEST_BASE_URL")
	if baseURL == "" {
		return fmt.Errorf("RPC_TEST_BASE_URL is required")
	}
	fixture, err := os.ReadFile(filepath.Join("conformance", "fixtures", "invoke-context-v1.json"))
	if err != nil {
		return err
	}
	var expected struct {
		Fields []string `json:"rpc_context_required_fields"`
	}
	if err := json.Unmarshal(fixture, &expected); err != nil || len(expected.Fields) != 9 {
		return fmt.Errorf("invalid invoke context fixture")
	}
	group, clientID := "conformance-go", "go-client"
	wsURL := strings.Replace(baseURL, "http://", "ws://", 1) + "/business/register"
	executor, err := client.NewRpcClientURL(group, clientID, wsURL)
	if err != nil {
		return err
	}
	contextCh := make(chan protocol.WireInvocationContext, 1)
	if err := executor.RegisterActionContext("conformance.echo", func(ctx context.Context, wire protocol.WireInvocationContext, request map[string]interface{}) (interface{}, error) {
		contextCh <- wire
		return map[string]interface{}{"echo": requestParamsEcho(request)}, nil
	}); err != nil {
		return err
	}
	if err := executor.Start(); err != nil {
		return err
	}
	defer executor.Destroy(2)

	invoker := client.NewRpcInvoker([]string{baseURL})
	defer invoker.Destroy()
	waitDeadline := time.Now().Add(10 * time.Second)
	for {
		ready, err := clientVisible(baseURL, group, clientID)
		if err != nil {
			return err
		}
		if ready {
			break
		}
		if time.Now().After(waitDeadline) {
			return fmt.Errorf("client %s did not become visible", clientID)
		}
		time.Sleep(100 * time.Millisecond)
	}
	response, err := invoker.InvokeContext(context.Background(), &client.InvokeRequest{Group: group, Api: "conformance.echo", Params: map[string]interface{}{"echo": "go"}, Timeout: 10 * time.Second})
	if err != nil {
		return err
	}
	select {
	case received := <-contextCh:
		if response.Group != group || response.ClientID != clientID || response.TraceID == "" || response.TraceID != received.TraceID || !strings.Contains(fmt.Sprint(response.Data), "go") || received.Sequence == "" || received.TraceID == "" || received.Group != group || received.Action != "conformance.echo" || received.ClientID != clientID || received.DeadlineUnixMS <= 0 || received.Idempotent || received.IdempotencyKey != "" || received.Attempt != 1 {
			return fmt.Errorf("conformance mismatch: response=%+v context=%+v", response, received)
		}
	case <-time.After(10 * time.Second):
		return fmt.Errorf("timed out waiting for invocation context")
	}
	return nil
}

func clientVisible(baseURL, group, clientID string) (bool, error) {
	query := url.Values{"group": {group}}
	request, err := http.NewRequest(http.MethodGet, baseURL+"/business/clientQueue?"+query.Encode(), nil)
	if err != nil {
		return false, err
	}
	client := &http.Client{Timeout: 2 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return false, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return false, fmt.Errorf("clientQueue returned HTTP status %s", response.Status)
	}
	var envelope struct {
		Code int      `json:"code"`
		Data []string `json:"data"`
	}
	if err := json.NewDecoder(response.Body).Decode(&envelope); err != nil {
		return false, fmt.Errorf("decode clientQueue response: %w", err)
	}
	if envelope.Code != 0 {
		return false, fmt.Errorf("clientQueue returned code %d", envelope.Code)
	}
	for _, current := range envelope.Data {
		if current == clientID {
			return true, nil
		}
	}
	return false, nil
}

func requestParamsEcho(request map[string]interface{}) interface{} {
	params, _ := request["params"].(map[string]interface{})
	return params["echo"]
}
