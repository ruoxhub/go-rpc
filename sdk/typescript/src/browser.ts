import { RpcClient } from "./client.js";
import type { WebSocketFactory, WebSocketLike } from "./protocol.js";

export { RpcClient } from "./client.js";
export type { RpcClientOptions } from "./client.js";
export type * from "./protocol.js";

export const browserWebSocketFactory: WebSocketFactory = (url, auth) =>
  new WebSocket(url, auth.protocols) as unknown as WebSocketLike;
