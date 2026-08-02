package cn.iinti.sekiro3.business.api.invoker;

import cn.iinti.sekiro3.business.api.core.InvokerConnection;
import cn.iinti.sekiro3.business.api.core.compress.CompressorManager;
import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import cn.iinti.sekiro3.business.api.core.eventbus.event.invoker.InvokerConnectEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.invoker.InvokerDestroyEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.invoker.InvokerDisconnectEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.invoker.InvokerEvent;
import cn.iinti.sekiro3.business.api.interfaze.Compressor;
import cn.iinti.sekiro3.business.api.log.LogPrintInterceptor;
import cn.iinti.sekiro3.business.api.log.LogPrinter;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.log.SekiroLoggerFactory;
import io.netty.channel.ChannelFuture;
import io.netty.channel.ChannelFutureListener;
import io.netty.channel.EventLoop;
import lombok.Getter;

import java.io.Closeable;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InvokerInstance implements Closeable {
    @Getter
    private final SekiroLogger sekiroLogger;
    @Getter
    private final CompressorManager compressorManager = new CompressorManager();
    @Getter
    private final String clientKey;

    private final String serverHost;
    private final int port;
    private final EventBus eventBus;
    private InvokerConnection invokerConnection;
    private final AtomicBoolean isDestroyed = new AtomicBoolean(false);
    private int reconnectRetryInterval = 2;
    private static final int DEFAULT_RECONNECT_RETRY_INTERVAL = 1;
    private static final int MAX_RECONNECT_RETRY_INTERVAL = 15;


    public InvokerInstance(final String serverHost, int serverPort) {
        this.serverHost = serverHost;
        this.port = serverPort;
        this.clientKey = serverHost + ":" + port;

        sekiroLogger = SekiroLoggerFactory.createLogger().setupInterceptor(new LogPrintInterceptor() {
            @Override
            public void doPrint(LogPrinter logPrinter, int level, String message, Throwable throwable) {
                String stringBuilder = "[" + serverHost + ":" + port + "]" + message;
                logPrinter.print(level, stringBuilder, throwable);
            }
        });

        eventBus = new EventBus();
        eventBus.findEventSender(InvokerConnectEvent.class);
        eventBus.findEventSender(InvokerDisconnectEvent.class);

    }

    public synchronized void start(boolean waitConnect) {
        if (invokerConnection != null) {
            return;
        }
        invokerConnection = new InvokerConnection(this, serverHost, port, waitConnect);
    }


    @Override
    public void close() {
        destroy();
    }

    @Override
    protected void finalize() throws Throwable {
        destroy();
        super.finalize();
    }


    public void destroy() {
        if (!isDestroyed.compareAndSet(false, true)) {
            return;
        }
        InvokerConnection invokerConnection1 = this.invokerConnection;
        if (invokerConnection1 == null) {
            return;
        }
        this.invokerConnection = null;
        invokerConnection1.destroy(new ChannelFutureListener() {
            @Override
            public void operationComplete(ChannelFuture future) {
                eventBus.findEventSender(InvokerDestroyEvent.class)
                        .onInvokerDestroy(InvokerInstance.this);
            }
        });

    }


    public boolean isAlive() {
        return invokerConnection != null && invokerConnection.isAlive();
    }


    public void addInvokerListener(InvokerEvent event) {
        eventBus.registerEventObserver(event);
    }


    @SuppressWarnings("unused")
    public void addCompressor(Compressor compressor) {
        compressorManager.registerCompressor(compressor);
    }


    public void onClientOpDestroy(EventLoop eventLoop) {
        eventBus.findEventSender(InvokerDisconnectEvent.class)
                .onInvokerDisConnected(InvokerInstance.this);

        if (isDestroyed.get()) {
            return;
        }
        invokerConnection = null;
        eventLoop.schedule(new Runnable() {
            @Override
            public void run() {
                start(false);
            }
        }, reconnectRetryInterval, TimeUnit.SECONDS);
        reconnectRetryInterval += DEFAULT_RECONNECT_RETRY_INTERVAL;
        if (reconnectRetryInterval > MAX_RECONNECT_RETRY_INTERVAL) {
            reconnectRetryInterval = MAX_RECONNECT_RETRY_INTERVAL;
        }
    }

    public void onClientOpOnline() {
        eventBus.findEventSender(InvokerConnectEvent.class)
                .onInvokerConnected(InvokerInstance.this);
        sekiroLogger.info("connect to sekiro server success");
        reconnectRetryInterval = DEFAULT_RECONNECT_RETRY_INTERVAL;
    }

    public boolean isDestroyed() {
        return isDestroyed.get();
    }

    public void performInvoke(Call call, String apiToken) {
        invokerConnection.performInvoke(call, apiToken);
    }
}
