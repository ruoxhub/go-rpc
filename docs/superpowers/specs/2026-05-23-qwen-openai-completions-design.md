# Qwen OpenAI Completions 渠道转换设计

> Spec date: 2026-05-23
> Status: Draft, awaiting user approval
> Owner: server team

## 1. 背景与目标

### 1.1 现状

`pkg/server/api/chat_completions.go` 已注册 `/v1/chat/completions` 路由（`bootstrap.go:328`），当前实现是**透传**：把 OpenAI 请求体打成 `_chat_completions` action 通过 ws 发给浏览器扩展，期望客户端返回 OpenAI 形态的响应或 SSE chunk。`sample/web/content/qwen/` 下有调用 `chat2.qianwen.com` 原生 API 的浏览器脚本（`chatStreamV2` 等），但其返回的是 qwen 私有 SSE 格式（`event: message` + `multi_load/iframe` 帧 + `[(deep_think)]` 标记），并不能直接给 OpenAI 客户端用。

`Chat2API/src/main/proxy/adapters/qwen.ts` 已有完整的 OpenAI ↔ qwen 双向转换逻辑，可作为参考实现，但它跑在 Node.js 服务里，不能直接复用到本仓的 Go server。

### 1.2 目标

让 OpenAI 协议客户端（`openai` SDK、curl、各种 LLM gateway）通过 sekiro-server 调用 qwen 网页版账号，返回标准 OpenAI 形态的响应/流。链路：

```
User (OpenAI)  →  rpc-server  →  ws 扩展  →  chat2.qianwen.com  →  ws 扩展  →  rpc-server  →  User (OpenAI)
                  [转 qwen body]                                              [qwen SSE 转 OpenAI chunk]
```

**核心约束**：rpc-server 是唯一做协议转换的地方；浏览器扩展只做"代理 + 签名注入 + 字节回流"。

### 1.3 非目标

- 不替换现有 `_chat_completions` 透传链路；它作为 model 名未命中任何 provider 时的 fallback 保留
- 一期不实现多模态（图片输入），spec 写出完整方案但不进 MVP
- 不实现 qwen 多账号 ticket 池：ticket 永远从浏览器 cookie 获取，server 不持有

## 2. 关键决策记录

| # | 决策 | 选定 | 备选 |
|---|------|------|------|
| 1 | 协议转换位置 | rpc-server 端双向转换 | 浏览器端转换 / 渠道开关 |
| 2 | Provider 抽象 | 通用 `Provider` 接口，先实装 qwen | 只为 qwen 写专用代码 / 按分组配置 |
| 3 | API 路径 | 沿用 `/v1/chat/completions` | 新增 `/api/chat/completions` |
| 4 | Provider 路由 | 按 `model` 名称前缀/包含匹配 | 在 `GroupConfig` 加 provider 字段 / 请求体 provider 字段 |
| 5 | Action 形态 | 新增 `qwen_chat_stream`，body=完整 qwen 请求体 | 复用 `chatStreamV2` |
| 6 | ws 回传载荷 | 透传 qwen 原始 SSE 字节块（base64），server 拆帧 | 浏览器拆帧后回传结构化数据 |
| 7 | ticket 来源 | 浏览器扩展从 `document.cookie` 自取 | server 管理 ticket 下发 |
| 8 | 思考/联网开关 | 按 model 名关键词推断（含 `think`/`r1`/`search`） | `reasoning_effort` 字段 |
| 9 | tools 策略 | Prompt 注入 + 流式标签解析（对齐 Chat2API） | 透传不解析 / 不支持 |
| 10 | 多模态 | 完整方案：浏览器走 V2 upload/token；MVP 不做 | 一期完整支持 |
| 11 | 测试覆盖 | 单测纯函数 + mock 上游集成 + 真实账号 E2E | — |
| 12 | qwen 默认超时 | 120s，yaml `Provider.QwenTimeoutSeconds` 可配 | 沿用现有 30s |
| 13 | 非流式实现 | 内部转流式累积 | 单写一条非流式 ws 链路 |
| 14 | 旧透传链路 | 保留作为 fallback（model 未命中 provider 时） | 直接废弃 |

## 3. 架构与流量

```
┌──────────┐  OpenAI /v1/chat/completions   ┌──────────────────────────────────┐
│  Client  │ ─────────────────────────────▶ │         rpc-server               │
│ (OpenAI  │                                │                                  │
│   SDK)   │ ◀── OpenAI SSE chunks ──────── │  provider.Resolve(req.Model)     │
└──────────┘                                │           │                      │
                                            │           ├─ hit qwen ──┐        │
                                            │           │             │        │
                                            │           └─ miss ──── fallback  │
                                            │                       (legacy)   │
                                            │                                  │
                                            │  ① BuildClientAction(req)        │
                                            │     OpenAI → qwen body           │
                                            │  ② ws action=qwen_chat_stream    │
                                            │           │                      │
                                            └───────────┼──────────────────────┘
                                                        ▼
                                          ┌──────────────────────────────────┐
                                          │   browser ext (qianwen.com)      │
                                          │                                  │
                                          │  ③ POST chat2.qianwen.com         │
                                          │     credentials: include          │
                                          │     + Baxia 签名 (Bx-Et/Bx-Ua)    │
                                          │                                  │
                                          │  ④ 边读 response.body 边          │
                                          │     ws.send(base64 字节块)        │
                                          └──────────────┬───────────────────┘
                                                         │ qwen 原始字节
                                                         ▼
                                          ┌──────────────────────────────────┐
                                          │  rpc-server stream pipeline      │
                                          │  ⑤ base64 解码 + (按需)解压       │
                                          │  ⑥ SSE 拆帧 (\n\n)                │
                                          │  ⑦ qwen event → OpenAI chunk     │
                                          │  ⑧ 写回 client SSE                │
                                          └──────────────────────────────────┘
```

**关键不变量：**
- ws 上永远是 qwen 原生字节，不夹杂 OpenAI 形态——抓包易调试、协议清晰
- ticket 不离开浏览器
- 旧 `_chat_completions` 透传保留为 fallback，向后兼容
- qwen 业务逻辑全部下线浏览器，迁到 server 端

## 4. Provider 抽象与代码结构

### 4.1 接口

```go
// pkg/server/provider/provider.go
package provider

import "github.com/mrh30000/go-rpc/pkg/model"

type Provider interface {
    Name() string
    Match(model string) bool
    BuildClientAction(req *model.ChatCompletionRequest) (ClientAction, error)
    StreamDecoder() StreamDecoder
}

type ClientAction struct {
    Action  string
    Payload map[string]any
}

type StreamDecoder interface {
    Push(raw []byte) ([]model.ChatCompletionStreamResponse, error)
    Flush() ([]model.ChatCompletionStreamResponse, error)
}
```

`StreamDecoder.Push` 接受任意字节切片：SSE 拆帧、解压、JSON 解析全在 Decoder 内部，调用方只管喂字节、收 OpenAI chunk。

### 4.2 注册表

只在 `Server.Start` 阶段写入，运行期只读。`sync.RWMutex` 作为防御保留，避免未来引入热加载时翻车。

```go
// pkg/server/provider/registry.go
package provider

import "sync"

var (
    mu       sync.RWMutex
    registry []Provider
)

// Register 在 Server.Start 阶段调用，加载完 yaml 后注册。
// 不能放 init()——init 拿不到 yaml 配置。
func Register(p Provider) {
    mu.Lock()
    defer mu.Unlock()
    registry = append(registry, p)
}

func Resolve(model string) Provider {
    mu.RLock()
    defer mu.RUnlock()
    for _, p := range registry {
        if p.Match(model) {
            return p
        }
    }
    return nil
}
```

### 4.3 文件落点

```
pkg/server/provider/
  provider.go              ← 接口、ClientAction、StreamDecoder
  registry.go              ← Register / Resolve
  registry_test.go
  qwen/
    qwen.go                ← Provider 接口实现：Name() / Match() / BuildClientAction 入口 / StreamDecoder() 工厂
    request_builder.go     ← OpenAI → qwen body 纯函数（被 qwen.go 调用）
    stream_decoder.go      ← qwenDecoder 实现 + SSE 拆帧 + qwen event → OpenAI chunk
    tool_parser.go         ← [function_calls] / XML 标签 → ToolCall
    model_map.go           ← 友好名 → qwen 内部 model id
    qwen_test.go           ← Provider 接口契约测试
    request_builder_test.go
    stream_decoder_test.go
    tool_parser_test.go
    testdata/
      qwen_sse_simple.txt
      qwen_sse_thinking.txt
      qwen_sse_tools.txt
      qwen_sse_error.txt
```

`pkg/server/api/chat_completions.go` 改造点（一处）：进入 handler 后调 `provider.Resolve(req.Model)`：
- 命中 → BuildClientAction → ws → StreamDecoder → SSE
- 未命中 → 现有 `_chat_completions` 透传逻辑（保兜底）

配置（路径以实际仓库布局为准，本仓位于 `internal/config/`）：
```go
// internal/config/config.go
type ProviderConfig struct {
    QwenTimeoutSeconds int  `yaml:"qwen_timeout_seconds"` // 默认 120
    QwenLogChunks      bool `yaml:"qwen_log_chunks"`      // DEBUG 开关，默认 false
}

type Config struct {
    // ... 现有字段
    Provider ProviderConfig `yaml:"provider"`
}
```

`pkg/server/bootstrap.go` 在 `Server.Start` 阶段（加载完 yaml 之后）调 `provider.Register(qwen.New(s.yamlConfig.Provider))`。**不能放 Go 的 `init()` 函数**——`init()` 在 `main` 之前执行，拿不到 yaml。

### 4.4 浏览器扩展改动

`sample/web/content/qwen/utils.js` 增加 `bytesToBase64` helper：

```js
window.__qwenai.bytesToBase64 = function(uint8) {
    var binary = '';
    for (var i = 0; i < uint8.length; i++) {
        binary += String.fromCharCode(uint8[i]);
    }
    return btoa(binary);
};
```

`sample/web/content/qwen/api.js` 新增 `chatStreamProxy`：

```js
window.__qwenai.chatStreamProxy = async function(params) {
    var body = params.body;     // server 完整组装的 qwen body
    var target = params.target; // 'https://chat2.qianwen.com/api/v2/chat'

    var ticket = window.__qwenai.getTicketFromCookie();
    if (!ticket) {
        throw new Error('qwen ticket not found in cookie');
    }
    var headers = await window.__qwenai.buildHeadersV2(ticket, body.req_id, true);

    // query string 由浏览器构造（device_id 在浏览器侧）
    var query = window.__qwenai.buildQueryParams();
    var url = target + '?' + query;

    var response = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: new Headers(headers),
        body: JSON.stringify(body),
    });

    if (!response.ok) {
        throw new Error('qwen upstream HTTP ' + response.status);
    }

    var reader = response.body.getReader();
    while (true) {
        var step = await reader.read();
        if (step.done) {
            params.onChunk({ chunk: '', done: true });
            return;
        }
        params.onChunk({
            chunk: window.__qwenai.bytesToBase64(step.value),
            done: false,
            encoding: 'identity', // 浏览器 fetch 已自动解压
        });
    }
};
```

`sample/web/content/qwen/index.js` 注册 action：
```js
actions: {
    // ... 现有 actions 保留
    chatStreamProxy: createAction(chatStreamProxy),
}
```

旧的 `chatStreamV2` 等方法**保留不删**，避免影响其他用途。

## 5. 数据流细节

### 5.1 入站：OpenAI → qwen body（`request_builder.go`）

```
ChatCompletionRequest (OpenAI)
       │
       ▼ qwen.BuildRequest
       │
       ├── 推断模型/特性
       │     model 映射：Qwen3-Max → tongyi-qwen3-max-model-agent
       │     model 名含 "think"/"thinking"/"r1" → enableThinking = true
       │     model 名含 "search" → enableWebSearch = true
       │     thinking 启用且基础模型有 thinking 变体 → 切到 thinking 模型
       │
       ├── 折叠多轮消息为单 prompt
       │     system → systemPrompt
       │     user/assistant/tool → conversationParts 顺序拼接
       │     tools 注入：toolsToSystemPrompt(tools) 追加到 systemPrompt
       │     userContent 末尾追加 TOOL_WRAP_HINT（仅当 tools 存在）
       │     finalContent = system ? "{system}\n\nUser: {user}" : user
       │
       └── 输出 qwen body
             {
               req_id, model, scene:"chat", session_id, sub_scene:"chat",
               temporary:false,
               messages:[{ content:finalContent, mime_type:"text/plain",
                           meta_data:{ ori_query:finalContent } }],
               from:"default", parent_req_id:"0",
               deep_search: enableThinking||enableWebSearch ? "1":"0",
               enable_search: enableWebSearch,
               biz_data:'{"entryPoint":"tongyigw"}',
               scene_param:"first_turn", chat_client:"h5",
               client_tm: timestampStr, protocol_version:"v2", biz_id:"ai_qwen",
             }
```

注意点：
- `req_id` 与 `session_id`：server 端用 UUIDv4 去横线生成，每次请求新生
- ticket、Baxia tokens、device_id：server 不知道也不需要——浏览器 fetch 时自己加
- query string（`biz_id=ai_qwen&...&nonce=...&timestamp=...`）由浏览器构造，server 不参与

### 5.2 中段：ws action 下发与字节回流

下发（server → 浏览器）`reqDataJSON`：
```json
{
    "action": "qwen_chat_stream",
    "params": {
        "body":   { "...完整 qwen body..." },
        "target": "https://chat2.qianwen.com/api/v2/chat"
    }
}
```

注：`target` 由 `Endpoints.chatV2` 提供。query string（`biz_id=ai_qwen&...&nonce=...&timestamp=...`）由浏览器侧 `buildQueryParams` 生成（device_id 在浏览器端），server 不参与。

回流（浏览器 → server，多帧，按 sequence 关联）：

```json
// chunk 帧
{
    "sequence": "qwen-<group>-<ts>",
    "type":     "chunk",
    "data":     "<base64 of raw bytes>",
    "encoding": "identity",
    "done":     false
}

// 终止帧
{
    "sequence": "qwen-<group>-<ts>",
    "type":     "end",
    "done":     true
}

// 错误帧
{
    "sequence": "qwen-<group>-<ts>",
    "type":     "error",
    "error":    "qwen upstream HTTP 401",
    "done":     true
}
```

**与现有 `forwarder.InvokeResponse` 字段映射**：
- `data` (base64) → `InvokeResponse.Data` (`[]byte`，server 端 base64 解码后写入)
- `error` → `InvokeResponse.Error` (`string`)
- `done`/`type:"end"` → `InvokeResponse.Done` (`bool`)
- `encoding` → 写入 `StreamDecoder` 创建时的状态，不进 `InvokeResponse`

`encoding` 字段：浏览器原生支持解压，默认 `identity`；保留字段以应对极端场景（如浏览器禁用了自动解压）。server 端 Decoder 也能处理 `gzip|br|zstd|identity`。

> 浏览器扩展现有 ws 协议以单一 chunk 字段为载荷；本设计**不引入新字段**，由扩展端在 chunk 中嵌入上述 JSON 结构。具体编解码格式由 M4 实施时与 `wsHandler` 现状对齐。

### 5.3 出站：qwen SSE → OpenAI chunk（`stream_decoder.go`）

```go
type qwenDecoder struct {
    buffer        bytes.Buffer
    state         qwenState   // sessionID, responseID, content, thinking, answerStarted, done
    toolParser    *qwenToolParser
    encoding      string
    model         string
    created       int64
    responseID    string
}

func (d *qwenDecoder) Push(raw []byte) ([]ChatCompletionStreamResponse, error) {
    // 1. base64 解码
    // 2. 按 d.encoding 解压
    // 3. d.buffer.Write
    // 4. 循环按 "\n\n" 拆 event
    //      a. parseSSE(eventBlock) → eventType, eventData
    //      b. json.Unmarshal(eventData) → result
    //      c. 处理 communication（提取 sessionid/reqid）
    //      d. 处理 multi_load 内 deep_think/multimodal_chat_think → reasoning_content delta
    //      e. 处理 mime_type in {text/plain, multi_load/iframe} → content delta（经 toolParser）
    //      f. msg.status in {complete, finished} → finish_reason
    //      g. result.error_code != 0 → error chunk
    // 5. 返回累计 OpenAI chunk
}

func (d *qwenDecoder) Flush() ([]ChatCompletionStreamResponse, error) {
    // 兜底：toolParser 残余 buffer 当普通文本 emit
    // 若 state.done==false：补一个 finish_reason="stop" chunk
}
```

关键状态机规则（从 `qwen.ts` 移植）：
1. **思考片段在答案出现之前才能 emit**：一旦 `answerStarted=true`，停止发 `reasoning_content`
2. **deep_think 优先于 multimodal_chat_think**：避免重复内容
3. **过滤标记**：移除 `[(deep_think)]`、`[(multimodal_chat_think_\d+)]`
4. **只在 `multi_load/iframe` 完成时发 finish_reason**：避免提前终止
5. **tool_calls 完成时 finish_reason="tool_calls"，否则 "stop"**

### 5.4 ws 信道：复用现有 stream 机制

`forwarder.TimeoutManager.RegisterStream` + `ChunkChan` 已支持按 sequence 多帧返回（`chat_completions.go:191-247`）。新流程不引入新 ws 协议层，仅 `chunk.Data` 语义从 "OpenAI chunk JSON" 改为 "qwen 原始字节 base64"。

handler 改造伪码（命中 qwen 时进入此分支，BuildClientAction 在 RegisterStream 之前执行——任何 builder 错误都在写 SSE header 之前返回 HTTP 400）：

```go
prov := provider.Resolve(req.Model)
if prov == nil {
    return h.handleChatCompletionStreamLegacy(...)  // 现有透传逻辑
}

action, err := prov.BuildClientAction(req)
if err != nil {
    writeChatError(c, http.StatusBadRequest, err.Error())
    return
}
decoder := prov.StreamDecoder()

stream := h.timeoutManager.RegisterStream(seq, ..., timeout)
defer h.timeoutManager.RemoveStream(seq)

reqDataJSON, _ := json.Marshal(map[string]any{
    "action": action.Action,
    "params": action.Payload,
})
if err := h.wsHandler.SendInvokeRequest(targetClient, seq, ..., reqDataJSON); err != nil {
    writeChatError(c, http.StatusOK, "Failed to send request: "+err.Error())
    return
}

writeSSEHeader(c)
for {
    select {
    case <-ctx.Done():
        writeSSEData(c, errorChunk("Request timeout"))
        writeSSEDone(c); return
    case chunk, ok := <-stream.ChunkChan:
        if !ok {
            // stream closed
            flushed, _ := decoder.Flush()
            for _, oc := range flushed { writeSSEData(c, oc) }
            writeSSEDone(c); return
        }
        if chunk.Error != "" {
            writeSSEData(c, errorChunk(chunk.Error))
            writeSSEDone(c); return
        }
        outputs, err := decoder.Push(chunk.Data)
        if err != nil {
            writeSSEData(c, errorChunk(err.Error()))
            writeSSEDone(c); return
        }
        for _, oc := range outputs { writeSSEData(c, oc) }
        if chunk.Done {
            flushed, _ := decoder.Flush()
            for _, oc := range flushed { writeSSEData(c, oc) }
            writeSSEDone(c); return
        }
    }
}
```

### 5.5 非流式（`stream=false`）

server 内部依然用 stream 模式调浏览器，累积所有 chunk 后一次性返回 ChatCompletionResponse。少一套代码路径。

```go
var fullContent, fullThinking strings.Builder
var toolCalls []ToolCall
var finish FinishReason = FinishReasonStop

for chunk := range stream.ChunkChan {
    outputs, _ := decoder.Push(chunk.Data)
    for _, oc := range outputs {
        d := oc.Choices[0].Delta
        if d.ReasoningContent != "" { fullThinking.WriteString(d.ReasoningContent) }
        if d.Content != "" { fullContent.WriteString(d.Content) }
        if len(d.ToolCalls) > 0 { toolCalls = mergeToolCalls(toolCalls, d.ToolCalls) }
        if oc.Choices[0].FinishReason != "" { finish = oc.Choices[0].FinishReason }
    }
    if chunk.Done {
        flushed, _ := decoder.Flush()
        // 同上累积
        break
    }
}

return ChatCompletionResponse{
    Choices: []ChatCompletionChoice{{
        Message: ChatCompletionMessage{
            Role:             "assistant",
            Content:          fullContent.String(),
            ReasoningContent: fullThinking.String(),
            ToolCalls:        toolCalls,
        },
        FinishReason: finish,
    }},
    Usage: Usage{PromptTokens: 1, CompletionTokens: 1, TotalTokens: 2}, // MVP 写死，见 5.7
}
```

### 5.6 多模态（图片输入，第二期）

```
client request: messages[].content = [
    {type:"image_url", image_url:{url:"https://..."}},
    {type:"text", text:"..."}
]
       │
       ▼ server pre-process
       ├── 扫描 messages，收集 image_url 列表
       ├── 对每张图：
       │     ws action="qwen_upload_image"
       │     payload: {url:"...", filename:"...", content_type:"..."}
       │     浏览器：fetch URL → blob → POST chat2-api.qianwen.com/api/v2/upload/token
       │              → PUT OSS → 返回 oss URL
       │     server 接收 oss URL，替换 messages[].content 中的 image_url.url
       └── 进入正常 qwen_chat_stream 流程
```

**MVP 不实现**。spec 写出方案，作为第二期 M7 任务。

### 5.7 Usage / Token 计数

qwen 网页版 SSE 不返回 token 计数。MVP 与 Chat2API 一致，**写死返回** `prompt_tokens=1, completion_tokens=1, total_tokens=2`，避免 OpenAI 客户端因 usage 缺失抛错。流式 `stream_options.include_usage=true` 时同样在末尾 chunk 写入这组占位值。

未来如果有需求做精确计量，可在 server 端用 tiktoken-go 等 tokenizer 自行计算，spec 不展开。

## 6. 错误处理、超时、安全、可观测性

### 6.1 错误边界

| 边界 | 错误来源 | 处理方 | 用户看到 |
|------|---------|-------|----------|
| ① 入站校验 | 请求体非法、model 必填、messages 必填 | `parseChatCompletionRequest` | HTTP 400 + `{error:{message,type:"sekiro_error"}}` |
| ② Provider 路由 | model 命中 qwen 但 group 没可用客户端 | `selectTargetClient` | HTTP 200 + `{error:{message:"no client available"}}` |
| ③ ws 发送失败 | ws 已断 / 注册超时 | `wsHandler.SendInvokeRequest` | SSE 一条 error chunk + `[DONE]` |
| ④ 浏览器侧失败 | qwen 5xx / ticket 失效 / Baxia 失败 | 浏览器 ws 回 `{type:"error"}` | SSE 一条 error chunk + `[DONE]` |
| ⑤ Decoder 异常 | qwen JSON 突变、SSE 半截 | `StreamDecoder.Push/Flush` 内 recover | SSE 兜底 chunk `finish_reason:"stop"` + 日志 |

**关键约束**：流已经写过任何 chunk 之后再发生错误**不能改 HTTP status**——只能写一条 `delta:{content:"\n[Error: ...]"}` + `finish_reason:"error"` 的 chunk 然后 `[DONE]`。

### 6.2 超时

```
maxInvokeTimeout (yaml `Provider.QwenTimeoutSeconds` 默认 120s)
       │
       ▼
context.WithTimeout(c.Request.Context(), timeout)
       │
       ▼
TimeoutManager.RegisterStream(seq, ..., timeout)
   (现有：上游 > timeout 无 chunk → 关 ChunkChan)
```

非 qwen 路径继续用现有 `maxInvokeTimeout`（30s 或 yaml 全局默认）。

### 6.3 安全

| 关注点 | 措施 |
|-------|------|
| ticket 不入服务端日志 | server 永远不持有 ticket。日志只打印 sequence、group、model、req_id、session_id |
| ws 通道授权 | 沿用 `OptionalAuth` + `authorizeRegisteredGroupAccess`，qwen 路径不放宽 |
| 浏览器扩展信任 | ws 注册时已授权；回传字节视为可信，但 Decoder 内部 recover 假设字节可能畸形 |
| 请求体大小 | 沿用 `maxChatCompletionBodyBytes = 1MB`；多模态预留二期放宽 |
| tool prompt 注入 | 拼接 system prompt 前 escape 用户输入里的 `[function_calls]`、`<tool_use>` 字面量；toolParser 兜底回滚 |
| 并发安全 | `StreamDecoder` 每请求一个，状态机不共享；registry `init()` 期写入运行期只读 |

### 6.4 指标与日志

新增 metrics（基于现有 `metrics.MetricCollector`）：
```
invoke.total{group, api=_chat_completions, provider=qwen}        counter
invoke.success{group, provider=qwen}                              counter
invoke.failure{group, provider=qwen, reason=timeout|upstream|decode}  counter
invoke.latency{group, provider=qwen}                              histogram
provider.stream.bytes{provider=qwen, direction=ws_in}             counter
provider.tool_calls_emitted{provider=qwen}                        counter
```

日志（zap，受 `Provider.QwenLogChunks` 控制 DEBUG 输出，避免日志爆炸）：
- INFO：provider 路由命中、ws 发送、流结束
- DEBUG：每个 ws chunk 字节数、SSE event 类型、tool parser 状态切换
- WARN：tool parser 兜底回滚、decoder recover
- ERROR：边界 ⑤ 错误、ws 发送失败

### 6.5 失败兜底矩阵

| 场景 | 行为 |
|------|------|
| 浏览器扩展未连接 | HTTP 200 + `error: no client available`（沿用） |
| ticket 失效（qwen 401） | 浏览器读到 401 → 错误帧 → SSE error chunk |
| Baxia 签名缺失 | 浏览器 `getBaxiaTokens` 抛错 → 错误帧 |
| qwen SSE 中途断开 | decoder 收 `done:true` 但 `state.done==false` → Flush 兜底 `finish_reason:"stop"`，已发内容保留 |
| qwen 返回非 SSE（HTML 错误页） | decoder 第一次 JSON parse 失败 → 累积满 8KB 仍无合法 SSE → 报 decode error |
| tool parser 撞上未闭合标签 | Flush 时残余 buffer 当普通文本 emit |

## 7. 测试策略

### 7.1 测试金字塔

```
        E2E（手动）              真实 qwen 账号 + 浏览器，3-5 个核心场景，不入 CI
   ┌────────────────────┐
   │ 集成（mock 上游）    │      go test，httptest 模拟 qwen 上游 + fake ws，10-15 场景
   │ 入 CI               │
   ├──────────────────────┤
   │ 单测（纯函数）        │      go test，无网络，覆盖率 80%+
   │ 入 CI                │
   └──────────────────────┘
```

### 7.2 单测

| 用例族 | 关键断言 |
|--------|---------|
| `request_builder_test.go` | OpenAI→qwen body：system 抽离、多轮折叠、tools 注入 prompt、model 名映射、`deep_search` 推断、req_id/session_id 非空 |
| `stream_decoder_test.go` | testdata 喂入分段（按字节切碎）→ 输出有序 OpenAI chunk；分段不变性；reasoning_content 在 content 之前；finish_reason 终态正确 |
| `tool_parser_test.go` | `[function_calls]` / `<tool_use>` 标签识别、参数 JSON 提取、跨 chunk 边界、未闭合标签兜底 |
| `model_map_test.go` | 已知名映射、未知名直透、大小写规范化 |
| `registry_test.go` | Provider 路由命中/未命中、并发安全 |

**关键技巧**：`stream_decoder_test.go` 的输入按 1/3/7/...n 等不同切片大小喂入，确保任何 TCP 分段不影响输出。这是 SSE 解析最容易翻车的点。

### 7.3 集成测试

`pkg/server/api/chat_completions_qwen_test.go`：用 `httptest.Server` 启假 qwen 上游，在 server 进程内启完整 API handler + WebSocket 监听，然后**用一个 fake 客户端连上去模拟浏览器扩展**——这个 fake 客户端读到 `qwen_chat_stream` action 后向 httptest 上游发请求，把 SSE 字节按本 spec §5.2 的 chunk 帧格式打包通过 ws 回写给 server。这样跑的是真实的 `wsHandler` + `forwarder.TimeoutManager` + `provider` 全链路，唯一被替换的是"浏览器"和"qwen 服务"两端。

| 场景 | 期望 |
|------|------|
| 简单文本对话流式 | 用户收完整 OpenAI SSE，含 role/content/finish_reason |
| 简单文本对话非流式 | 一次性 ChatCompletionResponse，content 完整 |
| 思考型模型 | reasoning_content 先于 content 出现 |
| 工具调用 | finish_reason="tool_calls"、tool_calls 结构正确 |
| 模型未命中 provider | 走透传 fallback |
| 上游超时 | SSE 输出 error chunk + [DONE] |
| 上游 401 | SSE 输出 error chunk |
| 上游错误 JSON | SSE 输出 error chunk |
| 上游中途断开 | Flush 兜底 finish_reason="stop"，已发内容保留 |
| 大字节切片随机分片 | 输出与不分片一致 |

### 7.4 E2E（手动 checklist，不入 CI）

```
[ ] 在 qianwen.com 登录 SSO，确认 cookie 中有 tongyi_sso_ticket
[ ] 启动 sekiro-server + 浏览器扩展并注册 group=qwen
[ ] curl localhost:5612/v1/chat/completions stream=true，model=Qwen3-Max
[ ] 验证 SSE 输出符合 OpenAI 协议
[ ] 切到 model=Qwen3-Max-Thinking，验证 reasoning_content 出现
[ ] 用 OpenAI Python SDK（openai==1.x）配 base_url 调通
[ ] 用 OpenAI SDK 测试 tools 参数与 tool_calls 返回
[ ] qwen 退出登录后再调，确认错误被翻译为 OpenAI error
```

## 8. 里程碑

每个里程碑可独立上线，作为后续 writing-plans 阶段的输入。

### M1 — Provider 抽象骨架（无渠道实现）
- 新建 `pkg/server/provider` 包，接口/Registry/Resolve
- `chat_completions.go` 接入 Resolve 但仅做空判断（fallback 到现状）
- 单测：`registry_test.go`
- yaml 加 `Provider.QwenTimeoutSeconds` 字段（默认 120）但暂未生效
- **验收**：现有透传链路完全不受影响，回归集成测试通过

### M2 — qwen RequestBuilder + ModelMap
- `qwen/request_builder.go` + `qwen/model_map.go`
- 单测覆盖所有 OpenAI→qwen body 字段
- 不需要浏览器扩展改动（这一步纯 Go server）
- **验收**：100% 单测覆盖，能 marshal 出与 Chat2API 等价的 qwen body（用 `qwen.ts` 输出做 golden 文件对比）

### M3 — qwen StreamDecoder + ToolParser
- `qwen/stream_decoder.go` + `qwen/tool_parser.go`
- 录制 5-10 段真实 qwen SSE 作为 testdata（包含简单/思考/工具/错误四类）
- 单测：分片不变性、思考/答案/工具/错误状态机
- **验收**：testdata 输入 → 输出 OpenAI chunk 与人工标注期望完全一致

### M4 — 浏览器扩展新 action `qwen_chat_stream`
- `sample/web/content/qwen/api.js` 加 `chatStreamProxy` + `bytesToBase64` 工具
- `sample/web/content/qwen/index.js` 注册 action
- 不动旧的 `chatStreamV2` 等
- **验收**：手测发请求，浏览器能调通 chat2.qianwen.com 并把字节流通过 ws 回传

### M5 — chat_completions handler 接入新流程
- `chat_completions.go` 改造：命中 qwen → BuildClientAction + StreamDecoder
- 非流式内部转流式累积
- 集成测试 mock 上游 + fake ws
- yaml `Provider.QwenTimeoutSeconds` 生效
- 新增指标
- `pkg/server/bootstrap.go` 在 `Server.Start` 阶段（加载 yaml 之后）调 `provider.Register(qwen.New(s.yamlConfig.Provider))`
- **验收**：所有集成测试通过，E2E checklist 烟测通过

### M6 — 文档与上线（可与 M5 合并）
- 更新 `CLAUDE.md` 项目概述新增 Provider 段落
- README/AGENTS.md 添加 qwen 调用示例（Python SDK + curl）
- **验收**：文档 review 通过

### M7（第二期，不入 MVP）— 多模态
- 浏览器扩展 `qwen_upload_image` action
- server `RequestBuilder` 预处理 image_url
- 集成测试

## 9. 风险登记

| 风险 | 严重度 | 缓解 |
|------|-------|------|
| qwen SSE 协议变更 | 高 | testdata 集中管理，发现变更只改 StreamDecoder；监控 decode_error 指标告警 |
| Baxia 签名算法升级 | 中 | 信任浏览器原生 baxia 模块；ws 错误带回 server 时识别 `error_code` 翻译给用户 |
| 思考型模型回复极慢 | 中 | 默认 120s 超时；ctx 取消传递到 ws 端正确清理 stream 注册 |
| ws 字节回流过快导致内存堆积 | 低 | TimeoutManager.ChunkChan 有缓冲容量；StreamDecoder 立即消费，不持久化 |
| tools prompt 与真实标记冲突 | 中 | escape 用户输入字面量；toolParser 兜底回滚 |
| 旧透传链路与新 provider 路径并存维护成本 | 低 | 仅作为 fallback，不主动开发；监控两条路径调用占比，待新路径稳定后可考虑下线旧路径 |

## 10. 参考资料

- `Chat2API/src/main/proxy/adapters/qwen.ts`：参考实现（Node.js）
- `sample/web/content/qwen/api.js`：现有 qwen V2 浏览器调用脚本
- `pkg/server/api/chat_completions.go:1-395`：现有透传链路实现
- `pkg/server/forwarder/timeout.go`：`RegisterStream` / `ChunkChan` 机制
- OpenAI Chat Completions 规范：reasoning_content（DeepSeek/qwen 扩展）、tool_calls、stream_options
