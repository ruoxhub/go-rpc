import WebSocket from "ws";
import { RpcClient } from "./client.js";
import type { WebSocketFactory, WebSocketLike } from "./protocol.js";

export { RpcClient } from "./client.js";
export type { RpcClientOptions } from "./client.js";
export type * from "./protocol.js";

export const nodeWebSocketFactory: WebSocketFactory = (url, auth) =>
  new WebSocket(url, auth.protocols ?? [], { headers: auth.headers }) as unknown as WebSocketLike;
