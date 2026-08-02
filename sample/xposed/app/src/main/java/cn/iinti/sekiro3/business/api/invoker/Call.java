package cn.iinti.sekiro3.business.api.invoker;

import cn.iinti.sekiro3.business.api.SekiroInvoker;
import cn.iinti.sekiro3.business.api.core.HandlerThreadPool;
import lombok.Getter;
import lombok.Setter;

import java.io.IOException;

public class Call {

    private final SekiroInvoker invoker;
    private final InvokerRequest invokerRequest;
    private volatile boolean executed;
    private Callback callback;
    @Getter
    @Setter
    private int seq;

    public Call(SekiroInvoker invoker, InvokerRequest invokerRequest) {
        this.invoker = invoker;
        this.invokerRequest = invokerRequest;
    }

    public void enqueue(Callback responseCallback) {
        enqueue0(new ThreadPoolWrapCallback(responseCallback));
    }

    private void enqueue0(Callback responseCallback) {
        this.callback = responseCallback;
        synchronized (this) {
            if (executed) {
                throw new IllegalStateException("Already Executed");
            }
            executed = true;
        }
        invoker.performInvoke(this);
    }

    public InvokerResponse execute() throws IOException {
        SyncCall syncCall = new SyncCall();
        enqueue0(syncCall);

        syncCall.waitLock();
        if (syncCall.exception == null && syncCall.invokerResponse == null) {
            throw new IOException("invoke sekiro timeout");
        }
        if (syncCall.exception != null) {
            throw syncCall.exception;
        }
        return syncCall.invokerResponse;
    }

    // 在线程池中回调，避免netty线程卡顿
    private static class ThreadPoolWrapCallback implements Callback {
        private final Callback delegate;

        public ThreadPoolWrapCallback(Callback delegate) {
            this.delegate = delegate;
        }

        @Override
        public void onFailure(final Call call, final IOException e) {
            HandlerThreadPool.post(new HandlerThreadPool.TaskRunner() {
                @Override
                public void run() {
                    delegate.onFailure(call, e);
                }
            });
        }

        @Override
        public void onResponse(final Call call, final InvokerResponse response) {
            HandlerThreadPool.post(new HandlerThreadPool.TaskRunner() {
                @Override
                public void run() {
                    delegate.onResponse(call, response);
                }
            });
        }
    }

    private static class SyncCall implements Callback {
        private final Object lock = new Object();
        private IOException exception;
        private InvokerResponse invokerResponse;

        @Override
        public void onFailure(Call call, IOException e) {
            exception = e;
            synchronized (lock) {
                lock.notify();
            }
        }

        @Override
        public void onResponse(Call call, InvokerResponse response) {
            invokerResponse = response;
            synchronized (lock) {
                lock.notify();
            }
        }

        void waitLock() {
            synchronized (lock) {
                try {
                    lock.wait();
                } catch (InterruptedException e) {
                    throw new RuntimeException(e);
                }
            }
        }

    }

    public Callback callback() {
        return callback;
    }

    public InvokerRequest invokerRequest() {
        return invokerRequest;
    }
}
