package cn.iinti.sekiro3.business.api.interfaze;
public interface ContextActionHandler extends ActionHandler {
    void handleRequest(InvocationContext context, RpcCancellationToken cancellationToken, RpcRequest request, RpcResponse response);
    @Override default void handleRequest(RpcRequest request, RpcResponse response) {
        handleRequest(request.getInvocationContext(), request.getCancellationToken(), request, response);
    }
}
