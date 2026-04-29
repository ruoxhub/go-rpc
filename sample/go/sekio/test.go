package sekio

import (
	"testing"
	"time"
)

type TestRpcHandler struct {
}

func (TestRpcHandler) handleRequest(request map[string]interface{}, response RpcResponse) {
	response.Success("ok")
}

func TestRpc(t *testing.T) {
	// https://sekiro.iinti.cn/business/invoke?group=test-go&action=testAction&sekiro_token=123
	client := MakeClientDefault("test-go")
	var handler RequestHandler = &TestRpcHandler{}
	client.RegisterHandler("testAction", &handler).Start()

	time.Sleep(2 * time.Minute)
}
