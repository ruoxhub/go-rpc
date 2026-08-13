# Formal TypeScript/Web SDK

Stage 1 的 TypeScript core 使用 WebSocket JSON，收到服务端 `registered` 后才 bind 和 ready，
不会降级或自动重连。浏览器使用 `browserWebSocketFactory`，Node 使用 `nodeWebSocketFactory`：

```ts
import { RpcClient, nodeWebSocketFactory } from "@mrh30000/go-rpc-sdk/node";

const client = new RpcClient({
  url: "ws://127.0.0.1:5612/business/register",
  group: "demo",
  clientId: "node-demo",
  websocketFactory: nodeWebSocketFactory,
});
client.registerAction("echo", async request => request.params);
await client.start();
```

从仓库构建后可用 `npm pack` 产生的本地 `.tgz` 安装：
`npm install ./artifacts/sdk/mrh30000-go-rpc-sdk-0.1.0-experimental.1.tgz`。
本阶段不发布到公共 npm。浏览器和 Node 共用 core；`_execjs` 不属于正式 SDK。
