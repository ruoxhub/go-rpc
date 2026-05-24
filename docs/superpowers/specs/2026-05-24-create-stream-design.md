# createStream — 流式 Action 端到端设计

**日期**: 2026-05-24
**分支**: `feat/qwen-provider`
**触发场景**: Qwen `/api/v2/chat/completions` 返回 `text/event-stream`，无法用现有的 `createAction` 一次性 JSON 包回传。

## 1. 背景

### 1.1 现状

`sample/web/lib/client.js` 提供的 `createAction(method)` 把业务 method 的 Promise 结果一次性走 `_sendSuccess` 包成 `{data, code, status, __sekiro_seq__}` 单帧 WebSocket 消息。当 method 是 `chatCompletions` 这种 SSE 流式接口时：

- `lib/http.js` 的 `fetchPost` 默认 `responseType:'text'`，会等 `response.text()` 全部读完
- 客户端拿到的是整条 SSE 文本，再包成 JSON 一次性回传
- `action_response.json` 中那串 escape 过的 `data: ...\\n\\n` 就是这种"伪流式"的产物

### 1.2 协议层已就绪

服务端协议层已经支持流式：

- `pkg/server/forwarder/timeout.go` — `StreamRecord` / `RegisterStream` / `PushStreamChunk` / `CompleteStream`
- `pkg/server/websocket/handler.go:296 handleInvokeStream` — 消费 `{type:"invoke_stream", __sekiro_seq__, data, error, status, done}` 多帧消息

但 HTTP 出口端 `pkg/server/api/handlers.go:handleForwardRequest` 现在只用 unary 路径（`timeoutManager.Wait()` 拿到完整响应再 `c.JSON(...)` 返回），**StreamRecord 在 HTTP 层从未被注册**。

### 1.3 目标

打通三层：
1. **客户端**：新增 `createStream`，用 `Response.body.getReader()` 逐 chunk 推 `invoke_stream` 帧到服务端
2. **服务端**：`/business/invoke` 加 `stream=true` 字段，进入 `RegisterStream` 路径，按 SSE 输出 chunked HTTP
3. **业务层**：`chatCompletions` 改成返回 `Response`，`index.js` 用 `createStream` 注册

## 2. 设计

### 2.1 客户端 — `lib/client.js`

#### 新增 `createStream`

```js
function createStream(method, options = {}) {
  return { method, stream: true, ...options };
}
```

放在 `createAction` 旁边，挂到 `window.createStream`。

#### `registerAction` 识别流式

`registerAction(actionName, actionConfig)` 现有逻辑里 `typeof actionConfig === 'object'` 分支额外判断 `actionConfig.stream === true`，走新的 `_buildStreamHandler`：

```js
_buildStreamHandler(actionName, method) {
  return async (request, _resolve, _reject) => {
    const seq = request.__sekiro_seq__ || '';
    const params = request.params || {};
    try {
      const resp = await method(params);
      // 必须是 Response（method 用 fetchPost(..., {isParseResponse:false})）
      if (!resp || !resp.body || typeof resp.body.getReader !== 'function') {
        this._sendStreamEnd(seq, 'createStream method 必须返回 Response 对象');
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          if (chunk) this._sendStreamChunk(seq, chunk);
        }
        const tail = decoder.decode();
        if (tail) this._sendStreamChunk(seq, tail);
        this._sendStreamEnd(seq);
      } finally {
        try { reader.releaseLock(); } catch (e) {}
      }
    } catch (e) {
      this._sendStreamEnd(seq, e instanceof Error ? e.message : String(e));
    }
  };
}
```

`registerAction` 改造：

```js
} else if (typeof actionConfig === 'object') {
  const { method, transform, stream } = actionConfig;
  if (typeof method !== 'function') {
    this.log(`Action ${actionName} 缺少有效的 method`, 'warn');
    return;
  }
  if (stream) {
    handler = this._buildStreamHandler(actionName, method).bind(this);
  } else {
    // 现有 unary 路径不变
    handler = (request, resolve, reject) => { /* ... */ };
  }
}
```

注意：流式 handler 自己负责整个生命周期（success/error 都通过 `_sendStreamChunk/_sendStreamEnd` 直接发帧），不再走外层 `_handleRpcRequest` 里的 `resolve/reject` → `_sendSuccess/_sendFailed`。所以传给 `_handleRpcRequest` 的 `resolve/reject` 在流式分支里是 no-op。

#### 新增帧发送方法

```js
_sendStreamChunk(seq, dataStr) {
  this._send(JSON.stringify({
    type: 'invoke_stream',
    __sekiro_seq__: seq,
    data: dataStr,    // 字符串透传，服务端 json.RawMessage 接收为 "..."
    done: false
  }));
}

_sendStreamEnd(seq, errorMsg) {
  const msg = {
    type: 'invoke_stream',
    __sekiro_seq__: seq,
    done: true
  };
  if (errorMsg) {
    msg.error = errorMsg;
    msg.status = -1;
  }
  this._send(JSON.stringify(msg));
}
```

#### actionDelay 处理

`actionDelay > 0` 时流式分支也需要前置 sleep（与 unary 一致），在 `_buildStreamHandler` 入口加：

```js
const delay = this.actionDelay;
if (delay > 0) {
  await new Promise(r => setTimeout(r, delay));
}
```

### 2.2 业务层 — `content/qwen/api.js` & `index.js`

#### `api.js`：`chatCompletions` 直返 Response

```js
window.__qwenai.chatCompletions = async function(params) {
  var { messages, model, chatId } = params || {};
  model = model || 'Qwen3.5-Plus';
  var headers = await buildHeadersV2();

  var body = { /* 不变 */ };
  var url = Endpoints.chatsChat + '?chat_id=' + chatId;

  return await fetchPost(url, body, headers, {
    ...Options,
    isParseResponse: false   // 关键：拿到原始 Response
  });
};
```

#### `index.js`：用 `createStream` 注册

```js
var { createAction, createStream } = window;  // 解构
// 或保持现状：window.createStream
actions: {
  chatCompletions: createStream(chatCompletions),
  getModel: createAction(getModel),
  createChat: createAction(createChat),
}
```

### 2.3 服务端 — `pkg/server/api/handlers.go`

#### `InvokeRequest` 加 `Stream` 字段

```go
type InvokeRequest struct {
    Group          string      `json:"group"`
    ClientID       string      `json:"clientId,omitempty"`
    ConstantInvoke string      `json:"constantInvoke,omitempty"`
    RpcToken       string      `json:"sekiro_token,omitempty"`
    Timeout        int         `json:"timeout,omitempty"`
    Action         string      `json:"action"`
    Params         interface{} `json:"params,omitempty"`
    Stream         bool        `json:"stream,omitempty"`
}
```

GET 路径也支持：query 中 `stream=1`/`stream=true` 进入流式分支。

#### `RequestBuilder` 接口加 `IsStream`

```go
type RequestBuilder interface {
    // ... existing
    IsStream() bool
}

// InvokeBuilder
type InvokeBuilder struct {
    // ... existing
    Stream bool
}
func (b *InvokeBuilder) IsStream() bool { return b.Stream }

// 其它 builder 默认返回 false
func (b *ExecJSBuilder) IsStream() bool   { return false }
func (b *GetCookieBuilder) IsStream() bool { return false }
func (b *GetHTMLBuilder) IsStream() bool   { return false }
```

#### `handleForwardRequest` 分流

在选完 client、生成 sequence 之后：

```go
sequence := builder.GetSequence(group)
timeout := builder.GetTimeout()

if builder.IsStream() {
    streamRec := h.timeoutManager.RegisterStream(sequence, group, targetClient.ClientID, timeout)
    if err := h.wsHandler.SendInvokeRequest(targetClient, sequence, group, targetClient.ClientID, reqDataJSON); err != nil {
        h.timeoutManager.RemoveStream(sequence)
        targetClient.MarkFailure()
        BusinessError(c, "Failed to send request: "+err.Error())
        return
    }
    h.streamSSEResponse(c, streamRec, group, targetClient, builder, startTime, reqAction)
    return
}

// 原有 unary 路径不变（h.timeoutManager.Add(sequence, ...)）
```

#### `streamSSEResponse` 实现

```go
func (h *APIHandler) streamSSEResponse(
    c *gin.Context,
    rec *forwarder.StreamRecord,
    group string,
    targetClient *client.RpcClient,
    builder RequestBuilder,
    startTime time.Time,
    reqAction string,
) {
    c.Writer.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
    c.Writer.Header().Set("Cache-Control", "no-cache")
    c.Writer.Header().Set("X-Accel-Buffering", "no")
    c.Writer.Header().Set("Connection", "keep-alive")
    c.Writer.WriteHeader(http.StatusOK)

    flusher, ok := c.Writer.(http.Flusher)
    if !ok {
        h.timeoutManager.RemoveStream(rec.ID)
        return
    }
    flusher.Flush()  // 立即把 200 头送出去

    timeoutTimer := time.NewTimer(rec.Timeout)
    defer timeoutTimer.Stop()

    var streamErr string
    defer func() {
        // 指标记录
        if builder.ShouldRecordMetrics() && h.metricsCollector != nil {
            status := "success"
            if streamErr != "" {
                status = "failure"
            }
            metricAPI := builder.GetMetricAPI(reqAction)
            h.metricsCollector.Incr("invoke.total", map[string]string{
                "group": group, "api": metricAPI, "status": status,
            }, 1)
            h.metricsCollector.RecordLatency("invoke.latency", map[string]string{
                "group": group, "api": metricAPI,
            }, float64(time.Since(startTime).Milliseconds()))
        }
        if streamErr != "" {
            targetClient.MarkFailure()
        } else {
            targetClient.MarkSuccess()
        }
    }()

    for {
        select {
        case <-c.Request.Context().Done():
            h.timeoutManager.RemoveStream(rec.ID)
            streamErr = "client disconnected"
            return
        case <-timeoutTimer.C:
            h.timeoutManager.RemoveStream(rec.ID)
            streamErr = "timeout"
            writeSSEErrorEvent(c.Writer, "timeout")
            flusher.Flush()
            return
        case chunk, ok := <-rec.ChunkChan:
            if !ok {
                if errMsg := rec.TerminalError(); errMsg != "" {
                    streamErr = errMsg
                    writeSSEErrorEvent(c.Writer, errMsg)
                    flusher.Flush()
                }
                return
            }
            if chunk.Error != "" {
                streamErr = chunk.Error
                writeSSEErrorEvent(c.Writer, chunk.Error)
                flusher.Flush()
                continue
            }
            // chunk.Data 是 json.RawMessage，客户端发的是 JSON 字符串（带引号）
            var payload string
            if err := json.Unmarshal(chunk.Data, &payload); err == nil {
                c.Writer.Write([]byte(payload))
            } else {
                c.Writer.Write(chunk.Data)
            }
            flusher.Flush()
        }
    }
}

func writeSSEErrorEvent(w io.Writer, msg string) {
    fmt.Fprintf(w, "event: error\ndata: %s\n\n", strings.ReplaceAll(msg, "\n", " "))
}
```

**关键设计点**：
- 透传客户端 reader chunk，不做 SSE 边界解析（保留原始 `data: ...\n\n`，下游消费者直接当 SSE 用）
- `c.Writer.WriteHeader(200)` 之后失败只能通过 `event: error` 通知，不能再回 502/500
- 客户端断连（`c.Request.Context().Done()`）主动 `RemoveStream`，触发 ChunkChan close 让客户端的下一次 `Push` 失败而中止读流

### 2.4 调用方使用

```bash
curl -N -X POST http://localhost:5612/business/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "group": "qwenai",
    "action": "chatCompletions",
    "stream": true,
    "params": {
      "messages": "Hello",
      "model": "qwen3-max",
      "chatId": "96fd5257-..."
    }
  }'
```

响应 `Content-Type: text/event-stream`，每个 chunk 实时到达。

## 3. 不在范围内

- `sample/ts/protocol/Client.ts` 是 Node 客户端，本次不动
- ExecJS / Cookie / HTML 不需要流式
- SSE 心跳 `event: ping` 不实现
- 流式调用方 SDK（curl 之外的封装）不实现

## 4. 风险与边界

| 风险 | 处理 |
|---|---|
| 客户端 `_sendStreamChunk` 在 WS 未连接时丢帧 | `_send` 已有 readyState 检查，只 log 不抛错；下游 `done:true` 帧也会丢，靠服务端超时兜底清理 StreamRecord |
| 客户端 method 抛错（网络/鉴权） | `_buildStreamHandler` catch 后发 `done:true + error`，服务端通过 `chunk.Error` → `event: error` 透出 |
| 客户端进程崩溃，never `done:true` | 服务端 `RegisterStream(timeout)` 持有的 StreamRecord 由 `cleanupLoop` 按 timeout 关闭 |
| `chunk.Data` 不是合法 JSON 字符串 | 退化路径直接写原字节，调用方仍然能收到内容 |
| `actionDelay > 0` | 流式分支入口前置 sleep，与 unary 一致 |

## 5. 影响面

| 文件 | 改动 |
|---|---|
| `sample/web/lib/client.js` | +`createStream` / `_buildStreamHandler` / `_sendStreamChunk` / `_sendStreamEnd`，`registerAction` 识别 `stream:true` |
| `sample/web/content/qwen/api.js` | `chatCompletions` 改用 `isParseResponse:false` 直返 Response |
| `sample/web/content/qwen/index.js` | `chatCompletions: createStream(chatCompletions)` |
| `pkg/server/api/handlers.go` | `InvokeRequest.Stream`、`RequestBuilder.IsStream`、各 builder、`handleForwardRequest` 分流、新增 `streamSSEResponse` |

unary 路径完全不动；ExecJS/Cookie/HTML 业务行为不受影响。
