package cn.iinti.sekiro3.business.api;

import android.app.ActivityThread;
import cn.iinti.sekiro3.business.api.core.SekiroClientConnection;
import cn.iinti.sekiro3.business.api.core.compress.CompressorManager;
import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientConnectEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientDestroyEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientDisConnectedEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientEvent;
import cn.iinti.sekiro3.business.api.interfaze.Compressor;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequestInitializer;
import cn.iinti.sekiro3.business.api.log.LogPrintInterceptor;
import cn.iinti.sekiro3.business.api.log.LogPrinter;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.log.SekiroLoggerFactory;
import cn.iinti.sekiro3.business.api.util.Constants;
import io.netty.channel.EventLoop;
import lombok.Getter;
import lombok.Setter;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 单点模式下Client，SekiroClient核心实现，对标开源版本SekiroClient。<br>
 * 但是一般情况下不建议使用他，因为他不具备集群连接功能
 */
public class SekiroClient {
    @Getter
    private final String clientId;
    @Getter
    private final String sekiroGroup;
    @Getter
    private final String clientKey;
    @Getter
    private SekiroRequestInitializer sekiroRequestInitializer;
    @Getter
    private final CompressorManager compressorManager = new CompressorManager();
    @Getter
    private final SekiroLogger sekiroLogger;

    private final String serverHost;
    private final int port;
    private final EventBus eventBus;
    private int reconnectRetryInterval = 1;
    private static final int DEFAULT_RECONNECT_RETRY_INTERVAL = 1;
    private static final int MAX_RECONNECT_RETRY_INTERVAL = 15;
    private SekiroClientConnection sekiroClientConnection;
    private final AtomicBoolean isDestroyed = new AtomicBoolean(false);

    @Setter
    private boolean showIntMsg = true;

    public SekiroClient(String sekiroGroup, String clientId) {
        this(sekiroGroup, clientId, Constants.DEFAULT_SERVER_CONF.DEFAULT_STAND_ALONG_SERVER, Constants.DEFAULT_SERVER_CONF.DEFAULT_STAND_ALONG_PORT);
    }

    public SekiroClient(final String sekiroGroup, final String clientId, final String serverHost, int serverPort) {
        this.sekiroGroup = sekiroGroup;
        this.clientId = clientId;
        this.serverHost = serverHost;
        this.port = serverPort;
        this.sekiroLogger = SekiroLoggerFactory.createLogger().setupInterceptor(new LogPrintInterceptor() {
            @Override
            public void doPrint(LogPrinter logPrinter, int level, String message, Throwable throwable) {
                String stringBuilder = "[" + sekiroGroup + ":" + clientId + "]" +
                        "[" + serverHost + ":" + port + "]" +
                        message;
                logPrinter.print(level, stringBuilder, throwable);
            }
        });
        this.clientKey = serverHost + ":" + port;

        // doInitEventBus
        eventBus = new EventBus();
        eventBus.findEventSender(SekiroClientConnectEvent.class);
        eventBus.findEventSender(SekiroClientDisConnectedEvent.class);
        eventBus.findEventSender(SekiroClientDestroyEvent.class);

        warningIfNotRunningOnAndroidMainProcess();
    }


    private void warningIfNotRunningOnAndroidMainProcess() {
        try {
            Class.forName("android.content.Context");
        } catch (Throwable ignore) {
            // not android env
            return;
        }
        // 这是一个很多人都容易触发的坑，但是在现代化手机中我们其实无法访问到Android的这些api，所以大概率这个告警是无法报出的
        // 但是他会覆盖大多数已知框架环境
        //   如果client运行在xposed或者lsposed环境中，当前classloader将会是可信赖的，那么访问私有api将会被允许
        //   如果client运行在ratel（本人的重打包方案）中，我们通过通过ratel的桥接获取配置
        //   如果运行在va环境中，私有api将会直接被干掉
        //   如果运行在qc或者珍惜大佬的重打包环境中，这里将无法识别
        try {
            // xposed,lsposed,edxposed,virtualApp
            if (!ActivityThread.currentProcessName().equals(ActivityThread.currentPackageName())) {
                sekiroLogger.warn("the sekiro client start on none main process in android, please check if you are register duplicate client id from multiple process");
            }
            return;
        } catch (Throwable ignore) {
        }
        // check other env
    }


    public synchronized void start() {
        if (sekiroClientConnection != null) {
            return;
        }
        sekiroClientConnection = new SekiroClientConnection(this, serverHost, port);
        if (showIntMsg) {
            sekiroLogger.info("welcome use sekiro framework, for more support please visit our website: https://iinti.cn/");
        }
    }


    public SekiroClient setupSekiroRequestInitializer(SekiroRequestInitializer sekiroRequestInitializer) {
        if (this.sekiroRequestInitializer != null) {
            // 遇到有用户多次调用这个接口，导致handler被覆盖
            throw new IllegalStateException("duplicate initializer setup ,please check your configuration");
        }
        this.sekiroRequestInitializer = sekiroRequestInitializer;
        return this;
    }


    public void destroy(final long waitSeconds) {
        if (!isDestroyed.compareAndSet(false, true)) {
            return;
        }
        SekiroClientConnection sekiroClientConnection1 = this.sekiroClientConnection;
        if (sekiroClientConnection1 == null) {
            return;
        }
        this.sekiroClientConnection = null;
        sekiroClientConnection1.destroy(waitSeconds);
    }


    public void addEventListener(SekiroClientEvent sekiroClientDisConnectedEvent) {
        eventBus.registerEventObserver(sekiroClientDisConnectedEvent);
    }


    @SuppressWarnings("unused")
    public void addCompressor(Compressor compressor) {
        compressorManager.registerCompressor(compressor);
    }


    public void triggerClientDestroy() {
        eventBus.findEventSender(SekiroClientDestroyEvent.class)
                .onClientDestroy(SekiroClient.this);
    }

    public void onClientOpDestroy(EventLoop eventLoop, SekiroClientConnection sekiroClientConnection) {
        if (this.sekiroClientConnection != null && this.sekiroClientConnection != sekiroClientConnection) {
            // duplicate client connection??
            return;
        }
        eventBus.findEventSender(SekiroClientDisConnectedEvent.class)
                .onClientDisConnected(SekiroClient.this);

        if (isDestroyed.get()) {
            return;
        }
        this.sekiroClientConnection = null;
        eventLoop.schedule(this::start, reconnectRetryInterval, TimeUnit.SECONDS);
        reconnectRetryInterval += DEFAULT_RECONNECT_RETRY_INTERVAL;
        if (reconnectRetryInterval > MAX_RECONNECT_RETRY_INTERVAL) {
            reconnectRetryInterval = MAX_RECONNECT_RETRY_INTERVAL;
        }
    }

    public void onClientOpOnline() {
        eventBus.findEventSender(SekiroClientConnectEvent.class)
                .onClientConnected(SekiroClient.this);
        sekiroLogger.info("connect to sekiro server success");
        reconnectRetryInterval = DEFAULT_RECONNECT_RETRY_INTERVAL;
    }

    public boolean isDestroyed() {
        return isDestroyed.get();
    }
}
