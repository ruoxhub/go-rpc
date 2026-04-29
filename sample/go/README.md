# Rpc的go语言环境

```go
package main

import "iinti.cn/sekiro"

type TestRpcHandler struct {
}

// handler处理器
func (TestRpcHandler) handleRequest(request map[string]interface{}, response RpcResponse) {
	response.Success("ok")
}

func TestRpc(t *testing.T) {
	// https://sekiro.iinti.cn/business/invoke?group=test-go&action=testAction&sekiro_token=123
	client := MakeClientDefault("test-go")
	var handler RequestHandler = &TestRpcHandler{}
	client.RegisterHandler("testAction", &handler).Start()

	// 请注意，由于内部是go routine，所以这里正常会直接运行结束，所以休眠一下
	time.Sleep(2 * time.Minute)
}
```