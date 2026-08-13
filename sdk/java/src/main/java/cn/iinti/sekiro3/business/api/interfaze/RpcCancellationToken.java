package cn.iinti.sekiro3.business.api.interfaze;

import java.util.concurrent.atomic.AtomicBoolean;

/** Cancellation state exposed to application handlers. */
public class RpcCancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();

    public boolean isCancelled() {
        return cancelled.get();
    }

    protected final void cancelInternal() {
        cancelled.set(true);
    }
}
