package cn.iinti.sekiro3.business.api.interfaze;

import java.util.concurrent.atomic.AtomicBoolean;

import cn.iinti.sekiro3.business.api.RpcClient;

public class RpcResponse {
    private final RpcClient client;
    private final String sequence;
    private final AtomicBoolean completed = new AtomicBoolean();

    public RpcResponse(RpcClient client, String sequence) {
        this.client = client;
        this.sequence = sequence;
    }

    public void success(Object data) {
        if (completed.compareAndSet(false, true)) {
            client.sendSuccess(sequence, data);
        }
    }

    public void failed(String message) {
        failed(-1, message);
    }

    public void failed(int status, String message) {
        if (completed.compareAndSet(false, true)) {
            client.sendFailed(sequence, status, message);
        }
    }

    public void sendStreamChunk(String chunk) {
        if (!completed.get()) {
            client.sendStream(sequence, chunk, false, null);
        }
    }

    public void endStream() {
        endStream(null);
    }

    public void endStream(String error) {
        if (completed.compareAndSet(false, true)) {
            client.sendStream(sequence, null, true, error);
        }
    }
}
