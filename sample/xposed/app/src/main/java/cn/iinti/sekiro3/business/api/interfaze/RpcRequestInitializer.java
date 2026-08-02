package cn.iinti.sekiro3.business.api.interfaze;

public interface RpcRequestInitializer {
    void onRpcRequest(RpcRequest request, HandlerRegistry handlerRegistry);
}
