package main

import (
	"context"
	"encoding/json"
	"fmt"
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
	request := &client.InvokeRequest{Group: group, Api: "conformance.echo", Params: map[string]interface{}{"echo": "go"}, Timeout: 10 * time.Second}
	var response *client.InvokeResponse
	deadline := time.Now().Add(10 * time.Second)
	var invokeErr error
	for {
		response, invokeErr = invoker.InvokeContext(context.Background(), request)
		if invokeErr == nil || time.Now().After(deadline) || (!strings.Contains(invokeErr.Error(), "500") && !strings.Contains(invokeErr.Error(), "no client available")) {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if invokeErr != nil {
		return invokeErr
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

func requestParamsEcho(request map[string]interface{}) interface{} {
	params, _ := request["params"].(map[string]interface{})
	return params["echo"]
}
