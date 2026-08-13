package cn.iinti.sekiro3.business.api.interfaze;

import cn.iinti.sekiro3.business.api.RpcClient;

import java.util.concurrent.atomic.AtomicBoolean;

public final class RpcResponse {
    private final RpcClient client;
    private final String sequence;
    private final String group;
    private final String clientId;
    private final String traceId;
    private final AtomicBoolean completed = new AtomicBoolean();

    public RpcResponse(RpcClient client, String sequence) {
        this(client, sequence, null, null, null);
    }

    public RpcResponse(RpcClient client, String sequence, String group, String clientId,
                       String traceId) {
        this.client = client;
        this.sequence = sequence;
        this.group = group;
        this.clientId = clientId;
        this.traceId = traceId;
    }

    public void success(Object data) {
        if (completed.compareAndSet(false, true)) {
            client.sendSuccess(sequence, data, group, clientId, traceId);
        }
    }

    public void failed(String message) {
        failed(-1, message);
    }

    public void failed(int status, String message) {
        if (completed.compareAndSet(false, true)) {
            client.sendFailed(sequence, status, message, group, clientId, traceId);
        }
    }

    public void sendStreamChunk(String chunk) {
        if (!completed.get()) {
            client.sendStream(sequence, chunk, false, null, group, clientId, traceId);
        }
    }

    public void endStream() {
        endStream(null);
    }

    public void endStream(String error) {
        if (completed.compareAndSet(false, true)) {
            client.sendStream(sequence, null, true, error, group, clientId, traceId);
        }
    }
}
