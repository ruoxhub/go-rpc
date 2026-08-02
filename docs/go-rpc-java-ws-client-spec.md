# go-rpc Java/Android WebSocket 客户端实现规格

> 本文档可直接交给其他大模型作为实现输入。
> 目标：为 go-rpc 服务端实现一个 Android/Xposed 可用的 Java WebSocket RPC 客户端，
> 协议与行为对齐 `sample/web/lib/client.js`（BaseClient），API 风格尽量兼容原 Sekiro3 Java SDK。

---

## 0. 任务目标

### 0.1 要做什么

在仓库 `go-rpc` 中，基于现有：

1. Web 客户端参考实现：`sample/web/lib/client.js`
2. Go 服务端 WebSocket 协议：`pkg/websocket/handler.go`
3. Xposed 示例入口：`sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java`
4. 已解包的官方 Java SDK 源码位置：`sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/`

实现一套 **兼容 go-rpc 服务端** 的 Java WebSocket 客户端，使 Android/Xposed 端可以：

- 连接 go-rpc 的 `/business/register`
- 注册 action
- 接收 invoke 请求
- 返回 unary / stream 响应
- 自动心跳
- 自动重连
- 支持 destroy 幂等销毁

### 0.2 明确不要做什么

- **不要**继续使用官方 `sekiro-business-api` 的 Netty TCP 二进制协议去连 go-rpc
- **不要**依赖 Netty / 官方 `SekiroClientConnection`
- **不要**把浏览器专用的 `BackgroundWebSocket` / `postMessage bridge` 搬到 Android
- **不要**大改 go-rpc 服务端协议
- **不要**重构无关模块

### 0.3 成功标准

1. Android/Xposed 客户端可连上本地 go-rpc 服务端（默认 `ws://127.0.0.1:5612`）
2. 调用：
   ```
   GET/POST /business/invoke?group=test&action=testAction
   ```
   可收到客户端返回 `ok`
3. 客户端断线后可自动重连
4. 客户端会主动发 heartbeat
5. 客户端连接成功后会 bind 上报 actions
6. 不会与服务端形成 “缺少 action / unknown message type” 死循环

---

## 1. 背景与核心结论

### 1.1 协议不兼容（最关键）

| 端 | 传输 | 协议 |
|---|---|---|
| 官方 Java SDK `SekiroClient` | Netty TCP | 二进制包：`Magic + Length + Type + SerialNumber + Headers + Data` |
| go-rpc 服务端 | WebSocket | JSON 文本消息 |
| Web BaseClient (`client.js`) | WebSocket | JSON 文本消息 |

**结论：**

> 官方 Java SDK 源码可参考 API 风格，但 **不能直接拿来连 go-rpc**。
> 必须参照 `client.js` 重新实现一套 **WebSocket + JSON** 的 Java 客户端。

### 1.2 当前 Xposed 示例现状

`sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java` 当前引用了不存在/不一致的类：

```java
import cn.iinti.sekiro3.business.api.RpcClient;
import cn.iinti.sekiro3.business.api.interfaze.ActionHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
```

但官方 SDK 实际类名是：

- `SekiroClient`
- `SekiroRequest`
- `SekiroResponse`
- `ActionHandler`
- `HandlerRegistry`
- `SekiroRequestInitializer`

并且它基于 Netty TCP，不兼容 go-rpc。

### 1.3 正确方向

实现一个新的 Java 客户端，推荐类名：

- `cn.iinti.sekiro3.business.api.RpcClient`  
  或  
- `cn.iinti.sekiro3.business.api.ws.RpcWsClient`

推荐兼容 API：

```java
new RpcClient("test", UUID.randomUUID().toString())
  .setupRpcRequestInitializer((request, registry) -> {
      registry.registerRpcHandler(new ActionHandler() {
          @Override public String action() { return "testAction"; }
          @Override public void handleRequest(RpcRequest req, RpcResponse resp) {
              resp.success("ok");
          }
      });
  })
  .start();
```

底层实现必须是 WebSocket JSON，而不是 Netty TCP。

---

## 2. 参考文件清单

### 2.1 必须阅读

| 文件 | 作用 |
|---|---|
| `sample/web/lib/client.js` | Web 端完整客户端参考实现（最重要） |
| `pkg/websocket/handler.go` | go-rpc 服务端 WebSocket 协议定义与处理 |
| `sample/xposed/app/src/main/java/cn/iinti/sekiro/demoapp/XposedMain.java` | Xposed 接入示例目标 API |
| `sample/xposed/app/build.gradle` | Android 依赖配置 |

### 2.2 可选阅读（仅参考 API 风格，不复用传输层）

| 文件 | 作用 |
|---|---|
| `sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/SekiroClient.java` | 原官方客户端生命周期 |
| `.../interfaze/ActionHandler.java` | action 接口 |
| `.../interfaze/SekiroRequest.java` | 请求参数读取风格 |
| `.../interfaze/SekiroResponse.java` | success/failed 响应风格 |
| `.../interfaze/HandlerRegistry.java` | handler 注册表风格 |

---

## 3. go-rpc WebSocket 协议规格（必须严格遵守）

### 3.1 注册连接 URL

```
ws://{host}:{port}/business/register?group={group}&clientId={clientId}
```

示例：

```
ws://127.0.0.1:5612/business/register?group=test&clientId=abc123
```

- `group` 必填
- `clientId` 必填
- 服务端默认心跳超时：60 秒内未收到任何消息会踢掉连接
- 客户端建议每 25 秒主动发一次 heartbeat

### 3.2 服务端消息结构（Go）

```go
type RpcMessage struct {
    Type          MessageType     `json:"type"`
    Sequence      string          `json:"sequence,omitempty"`
    RpcSeq        string          `json:"__sekiro_seq__,omitempty"`
    Group         string          `json:"group,omitempty"`
    ClientID      string          `json:"clientId,omitempty"`
    Actions       []string        `json:"actions,omitempty"`
    Data          json.RawMessage `json:"data,omitempty"`
    Error         string          `json:"error,omitempty"`
    Status        int             `json:"status,omitempty"`
    Done          bool            `json:"done,omitempty"`
    Timestamp     int64           `json:"timestamp,omitempty"`
    TraceID       string          `json:"trace_id,omitempty"`
}
```

消息类型：

| type | 方向 | 含义 |
|---|---|---|
| `heartbeat` | 双向 | 心跳 |
| `bind` | C→S | 上报 actions |
| `invoke` | S→C | 服务端下发调用请求 |
| `invoke_response` / 无 type 但带 seq | C→S | unary 响应 |
| `invoke_stream` | C→S | 流式响应帧 |
| `error` | S→C | 错误通知 |

### 3.3 客户端 → 服务端

#### A. heartbeat

```json
{
  "type": "heartbeat",
  "group": "test",
  "clientId": "abc123",
  "timestamp": 1722500000000
}
```

#### B. bind（上报 actions）

```json
{
  "type": "bind",
  "group": "test",
  "clientId": "abc123",
  "actions": ["testAction", "getUser"],
  "timestamp": 1722500000000
}
```

#### C. unary 成功响应（兼容 client.js）

```json
{
  "data": "ok",
  "code": 0,
  "status": 0,
  "__sekiro_seq__": "test-testAction-1722500000000"
}
```

也可以：

```json
{
  "type": "invoke_response",
  "data": {"hello":"world"},
  "status": 0,
  "__sekiro_seq__": "..."
}
```

#### D. unary 失败响应

```json
{
  "message": "未定义 action 处理函数：xxx",
  "status": -1,
  "__sekiro_seq__": "..."
}
```

#### E. stream chunk

```json
{
  "type": "invoke_stream",
  "__sekiro_seq__": "...",
  "data": "chunk text",
  "done": false
}
```

#### F. stream end

```json
{
  "type": "invoke_stream",
  "__sekiro_seq__": "...",
  "done": true
}
```

stream error end：

```json
{
  "type": "invoke_stream",
  "__sekiro_seq__": "...",
  "done": true,
  "error": "something failed",
  "status": -1
}
```

### 3.4 服务端 → 客户端

#### A. invoke 请求

```json
{
  "type": "invoke",
  "group": "test",
  "clientId": "abc123",
  "action": "testAction",
  "params": {
    "arg1": "x",
    "arg2": "y"
  },
  "__sekiro_seq__": "test-testAction-1722500000000",
  "timestamp": 1722500000000,
  "trace_id": "optional-trace-id"
}
```

注意：

- `action` 必有
- `__sekiro_seq__` 必有
- 参数可能在 `params` 中，也可能被 flatten 到顶层字段
- 客户端读取参数时要兼容这两种形态

#### B. heartbeat 响应

```json
{
  "type": "heartbeat",
  "timestamp": 1722500000000
}
```

#### C. error

```json
{
  "type": "error",
  "error": "unknown message type",
  "sequence": "...",
  "timestamp": 1722500000000
}
```

### 3.5 防死循环规则（非常重要）

客户端收到以下消息时 **必须静默忽略，不能当 action 请求处理，也不能回错误包**：

- `type === "heartbeat"`
- `type === "error"`
- `type === "invoke_response"`
- 无 `action` 且无 `__sekiro_seq__` 的消息

否则会与服务端形成无限回环：

```
client 回 "缺少 action"
  -> server 回 "unknown message type"
  -> client 再回 "缺少 action"
  -> ...
```

这是 `client.js` 已经踩过并修复的问题，Java 实现必须复刻。

---

## 4. client.js 行为规格（Java 必须对齐）

### 4.1 生命周期

```
create -> start -> connect -> onopen
  -> startHeartbeat
  -> reportActions(bind)
  -> receive invoke
  -> handle action
  -> send response
onclose / onerror
  -> scheduleReconnect (unless manual disconnect)
destroy
  -> stop reconnect
  -> stop heartbeat
  -> close socket
  -> clear handlers
```

### 4.2 必须实现的能力

| 能力 | client.js 对应 | 要求 |
|---|---|---|
| 构建 WS URL | `buildWebSocketURL()` | `/business/register?group=&clientId=` |
| 连接 | `_connect()` | OkHttp / Java-WebSocket |
| 心跳 | `_startHeartbeat()` | 25s 一次 |
| 上报 actions | `reportActions()` | 连接成功后 bind |
| 注册 action | `registerAction()` | Map 存储 |
| 请求分发 | `_handleRpcRequest()` | 按 action 路由 |
| 成功响应 | `_sendSuccess()` | `data/code/status/__sekiro_seq__` |
| 失败响应 | `_sendFailed()` | `message/status=-1/__sekiro_seq__` |
| 流式响应 | `_sendStreamChunk/_sendStreamEnd` | `invoke_stream` |
| 指数退避重连 | `_scheduleReconnect()` | 1s,2s,4s... 封顶 30s，无次数上限 |
| 手动断开 | `_disconnect()` | 禁止自动重连 |
| 幂等销毁 | `destroy()` | 可重复调用 |

### 4.3 重连策略

```
baseReconnectDelay = 1000ms
maxReconnectDelay = 30000ms
exponent = min(reconnectAttempts - 1, 6)
delay = min(base * 2^exponent, max)
```

规则：

- 手动 disconnect / destroy 后不再重连
- 已有 pending reconnect timer 时不重复调度
- 连接成功后 `reconnectAttempts = 0`
- 不设最大重连次数，避免“躺平”

### 4.4 Action 延迟

支持全局 `actionDelay`（毫秒）：

- unary action 执行前 sleep/delay
- stream action 执行前 sleep/delay

默认 0。

---

## 5. 推荐 Java 实现设计

### 5.1 建议包结构

```text
sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/
  RpcClient.java                 # 主客户端（WebSocket JSON）
  interfaze/
    ActionHandler.java           # 可复用或新建
    RequestHandler.java
    RpcRequest.java              # 新：JSON 请求包装
    RpcResponse.java             # 新：JSON 响应包装
    HandlerRegistry.java         # 可改造为持久 registry
    RpcRequestInitializer.java   # 新：替代 SekiroRequestInitializer
```

如果担心和旧 Netty SDK 冲突，可用：

```text
cn.iinti.sekiro3.business.api.ws.*
```

但 `XposedMain` 当前期望的是：

```java
cn.iinti.sekiro3.business.api.RpcClient
cn.iinti.sekiro3.business.api.interfaze.RpcRequest
cn.iinti.sekiro3.business.api.interfaze.RpcResponse
```

优先按这个命名实现，保证示例可直接编译。

### 5.2 核心类职责

#### `RpcClient`

职责：

- 保存 `group` / `clientId` / `serverHost` / `port`
- 管理 WebSocket 连接
- 管理 handlers
- 心跳
- 重连
- bind 上报
- 消息收发

建议构造器：

```java
public RpcClient(String group, String clientId)
public RpcClient(String group, String clientId, String host, int port)
```

默认：

- host = `127.0.0.1`
- port = `5612`
- wsURL = `ws://host:port/business/register?group=...&clientId=...`

公开 API：

```java
RpcClient setupRpcRequestInitializer(RpcRequestInitializer initializer)
void start()
void destroy()
void destroy(long waitSeconds) // 可选
boolean isConnected()
```

#### `HandlerRegistry`

持久保存 action -> handler：

```java
registerRpcHandler(RequestHandler handler)
registerRpcHandler(String action, RequestHandler handler)
List<String> actionList()
RequestHandler get(String action)
```

注意：

官方旧 `HandlerRegistry` 是“每个请求临时创建”的。  
go-rpc/Web 模式应是“客户端生命周期内持久注册”，更接近 `client.js` 的 `handlers` Map。

#### `RpcRequest`

包装服务端下发的 invoke JSON：

必须支持：

```java
String getAction()
String getSeq()
String getString(String key)
int getIntValue(String key)
boolean getBooleanValue(String key)
JSONObject getParams()
JSONObject raw()
boolean containsKey(String key)
```

参数读取优先级建议：

1. `params.key`
2. 顶层 `key`
3. 默认值 / null

#### `RpcResponse`

```java
void success(Object data)
void failed(String message)
void failed(int status, String message)
void sendStreamChunk(String chunk)
void endStream()
void endStream(String error)
```

内部发送：

- success -> `_sendSuccess`
- failed -> `_sendFailed`
- stream -> `invoke_stream`

必须保证 **同一 seq 只成功响应一次**（unary），可用 `AtomicBoolean`。

### 5.3 线程模型

Android/Xposed 环境注意：

- WebSocket 回调线程不要做重业务
- action handler 建议丢到独立线程池
- 发送消息要线程安全（同步 send）

建议：

```text
1 个连接读线程 / OkHttp callback 线程
1 个 scheduled 线程：heartbeat + reconnect
1 个业务线程池：执行 action handler
```

### 5.4 WebSocket 库选择

Android 推荐：

1. **OkHttp WebSocket**（优先）
2. Java-WebSocket
3. 不建议再引入 Netty

`sample/xposed/app/build.gradle` 当前依赖：

```gradle
implementation('cn.iinti.sekiro3.business:sekiro-business-api:1.0')
compileOnly 'de.robv.android.xposed:api:82'
```

实现时建议：

- 去掉对旧 Netty SDK 的运行依赖（若源码内嵌，则不要再 implementation maven 包）
- 增加：

```gradle
implementation 'com.squareup.okhttp3:okhttp:4.12.0'
implementation 'com.alibaba:fastjson:1.2.83'
// 或 org.json / gson
```

如果想零第三方 JSON，可用 `org.json.JSONObject`，但 Android/Xposed 下 Fastjson 更贴近原 SDK。

---

## 6. 伪代码规格（实现按这个写）

### 6.1 start

```text
start():
  if started: return
  started = true
  isManualDisconnect = false
  ensureHandlersRegisteredFromInitializer()
  connect(buildWsUrl())
```

### 6.2 connect

```text
connect(url):
  cleanupOldSocket()
  socket = new WebSocket(url)
  onOpen:
    reconnectAttempts = 0
    startHeartbeat()
    reportActions()
  onMessage(text):
    handleRpcRequest(text)
  onClosing/onClosed:
    stopHeartbeat()
    socket = null
    if !isManualDisconnect:
      scheduleReconnect()
  onFailure:
    stopHeartbeat()
    socket = null
    if !isManualDisconnect:
      scheduleReconnect()
```

### 6.3 handleRpcRequest

```text
handleRpcRequest(json):
  msg = parse(json)
  type = msg.type || ""

  if type in ["heartbeat", "error", "invoke_response"]:
    return

  seq = msg.__sekiro_seq__ || msg.sequence || ""
  action = msg.action

  if action is empty:
    if seq is empty:
      log warn and return
    sendFailed(seq, "缺少 request 参数 {action}")
    return

  handler = handlers.get(action)
  if handler == null:
    sendFailed(seq, "未定义 action 处理函数：" + action)
    return

  request = new RpcRequest(msg)
  response = new RpcResponse(this, seq)

  executeInWorker:
    try:
      maybeDelay(actionDelay)
      handler.handleRequest(request, response)
    catch e:
      response.failed(String(e))
```

### 6.4 sendSuccess / sendFailed

```text
sendSuccess(seq, data):
  payload = {
    data: data,
    code: 0,
    status: 0,
    __sekiro_seq__: seq
  }
  send(json(payload))

sendFailed(seq, message):
  payload = {
    message: message,
    status: -1,
    __sekiro_seq__: seq
  }
  send(json(payload))
```

### 6.5 reportActions

```text
reportActions():
  if !connected: return
  actions = handlers.keys()
  if empty: return
  send({
    type: "bind",
    group,
    clientId,
    actions,
    timestamp: now
  })
```

### 6.6 heartbeat

```text
every 25s:
  if connected:
    send({
      type: "heartbeat",
      group,
      clientId,
      timestamp: now
    })
```

### 6.7 destroy

```text
destroy():
  if destroyed: return
  destroyed = true
  isManualDisconnect = true
  stopHeartbeat()
  clearReconnectTimer()
  closeSocket()
  clearHandlers optional
```

---

## 7. Xposed 示例应改成这样

```java
package cn.iinti.sekiro.demoapp;

import java.util.UUID;

import cn.iinti.sekiro3.business.api.RpcClient;
import cn.iinti.sekiro3.business.api.interfaze.ActionHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public class XposedMain implements IXposedHookLoadPackage {
    public static XC_LoadPackage.LoadPackageParam loadPackageParam;

    @Override
    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam loadPackageParam) throws Throwable {
        XposedMain.loadPackageParam = loadPackageParam;

        // 只在主进程启动
        if (!loadPackageParam.packageName.equals(loadPackageParam.processName)) {
            return;
        }

        // 只注入目标 App
        if (!"com.xxx.xxx".equals(loadPackageParam.packageName)) {
            return;
        }

        new RpcClient("test", UUID.randomUUID().toString(), "127.0.0.1", 5612)
            .setupRpcRequestInitializer((request, handlerRegistry) ->
                handlerRegistry.registerRpcHandler(new ActionHandler() {
                    @Override
                    public String action() {
                        return "testAction";
                    }

                    @Override
                    public void handleRequest(RpcRequest sekiroRequest, RpcResponse sekiroResponse) {
                        sekiroResponse.success("ok");
                    }
                })
            )
            .start();
    }
}
```

验证调用：

```text
http://127.0.0.1:5612/business/invoke?group=test&action=testAction
```

期望返回类似：

```json
{
  "data": "ok",
  "code": 0,
  "status": 0
}
```

---

## 8. 与旧官方 SDK 的关系

### 8.1 可以保留的

- `ActionHandler.action()`
- `handleRequest(request, response)`
- `response.success(...)` / `failed(...)`
- group + clientId 构造方式
- initializer 注册 handler 的使用体验

### 8.2 必须替换的

| 旧实现 | 新实现 |
|---|---|
| Netty TCP | WebSocket |
| `SekiroPacket` 二进制 | JSON 文本 |
| `C_TYPE_REGISTER` | URL query + 连接即注册 |
| 被动心跳为主 | 主动 25s heartbeat |
| 无 bind actions | 连接后 bind 上报 |
| serialNumber int | `__sekiro_seq__` string |

### 8.3 对已解包源码的处理建议

路径：

```text
sample/xposed/app/src/main/java/cn/iinti/sekiro3/business/api/
```

建议策略（二选一）：

#### 方案 A（推荐，最小冲突）

- 新建 `RpcClient` / `RpcRequest` / `RpcResponse` 等 WebSocket 版本
- 旧 Netty 相关类先保留但 **不参与编译路径**，或移到 `legacy/` 备用
- Xposed demo 只依赖新 WebSocket 客户端

#### 方案 B

- 直接改造现有 `SekiroClient` 为 WebSocket 实现
- 删除/停用 Netty connection/protocol/compress 相关代码

对 go-rpc 项目来说，**方案 A 更安全**。

---

## 9. 实现任务拆分（给执行模型）

按顺序完成：

### Task 1：定义接口层

创建/补齐：

- `RpcRequest`
- `RpcResponse`
- `RpcRequestInitializer`
- `HandlerRegistry`（持久版）
- `ActionHandler` / `RequestHandler`

验收：

- XposedMain 的 import 可解析

### Task 2：实现 RpcClient 连接与收发

- buildWsUrl
- connect/close
- send text
- parse json message
- ignore control messages

验收：

- 能连上 go-rpc `/business/register`

### Task 3：实现 heartbeat + reconnect + destroy

验收：

- 25s 心跳
- 断线自动重连
- destroy 后不再重连

### Task 4：实现 action 注册与 unary 响应

验收：

- `/business/invoke?group=test&action=testAction` 返回 ok

### Task 5：实现 bind 上报

验收：

- 连接成功后服务端 group actions 可看到 `testAction`

### Task 6：实现 stream（可选但建议做）

验收：

- 可持续推 `invoke_stream`，最后 `done=true`

### Task 7：更新 build.gradle / README

- 替换旧 maven SDK 依赖
- 增加 OkHttp/JSON 依赖
- 更新 `sample/xposed/README.md` 说明改为对接 go-rpc

---

## 10. 非目标与边界

- 不做浏览器 bridge / BackgroundWebSocket
- 不做集群 `ClusterSekiroClient`
- 不做完整 Invoker 调用端（可后续）
- 不要求兼容原 Java 二进制 sekiro server
- 不修改 go-rpc 核心服务协议

---

## 11. 验收清单

- [ ] `RpcClient` 使用 WebSocket，而不是 Netty TCP
- [ ] 连接 URL 为 `/business/register?group=&clientId=`
- [ ] 每 25s 发送 heartbeat
- [ ] onopen 后 bind 上报 actions
- [ ] 能处理服务端 `type=invoke`
- [ ] 成功响应带 `__sekiro_seq__` + `status=0`
- [ ] 失败响应带 `__sekiro_seq__` + `status=-1`
- [ ] 忽略 heartbeat/error/无 action 无 seq 消息，不回环
- [ ] 断线指数退避重连，封顶 30s，无次数上限
- [ ] destroy 幂等且停止重连
- [ ] Xposed 示例可调用 `testAction` 返回 `ok`
- [ ] 不依赖官方 Netty 传输层即可运行

---

## 12. 最小可运行示例（实现完成后应支持）

```java
RpcClient client = new RpcClient("test", "device-001", "10.0.2.2", 5612);
client.setupRpcRequestInitializer((req, registry) -> {
    registry.registerRpcHandler(new ActionHandler() {
        @Override public String action() { return "testAction"; }
        @Override public void handleRequest(RpcRequest request, RpcResponse response) {
            String name = request.getString("name");
            response.success("hello " + (name == null ? "world" : name));
        }
    });
});
client.start();
```

调用：

```text
http://127.0.0.1:5612/business/invoke?group=test&action=testAction&name=sekiro
```

期望：

```json
{
  "data": "hello sekiro",
  "code": 0,
  "status": 0
}
```

---

## 13. 给执行模型的最终指令

请在 `sample/xposed` 中实现上述 **go-rpc 兼容的 Java WebSocket RpcClient**，以 `sample/web/lib/client.js` 为行为权威参考，以 `pkg/websocket/handler.go` 为协议权威参考。

优先保证：

1. 协议正确
2. 生命周期正确
3. Xposed demo 可跑通 unary invoke

不要复用官方 Netty TCP SDK 传输实现。
