package cn.iinti.sekiro3.business.api.interfaze;
import java.util.concurrent.atomic.AtomicBoolean;
public final class RpcCancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();
    public boolean isCancelled() { return cancelled.get(); }
    public void cancel() { cancelled.set(true); }
}
