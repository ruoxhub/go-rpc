package cn.iinti.sekiro3.business.api.interfaze;

public interface RequestHandler {
    void handleRequest(RpcRequest rpcRequest, RpcResponse rpcResponse);
}
