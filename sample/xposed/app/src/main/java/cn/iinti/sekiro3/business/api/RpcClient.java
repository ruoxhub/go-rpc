package cn.iinti.sekiro3.business.api;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;

import java.net.URLEncoder;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import cn.iinti.sekiro3.business.api.interfaze.HandlerRegistry;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequestInitializer;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

public class RpcClient {
    private static final long HEARTBEAT_INTERVAL_MS = 25_000L;
    private static final long MAX_RECONNECT_DELAY_MS = 30_000L;

    private final String group;
    private final String clientId;
    private final String host;
    private final int port;
    private final HandlerRegistry handlers = new HandlerRegistry();
    private final OkHttpClient httpClient = new OkHttpClient.Builder().build();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private final Object lifecycleLock = new Object();

    private volatile WebSocket socket;
    private volatile boolean connected;
    private volatile boolean started;
    private volatile boolean destroyed;
    private volatile boolean manualDisconnect;
    private volatile long actionDelay;
    private int reconnectAttempts;
    private ScheduledFuture<?> heartbeatTask;
    private ScheduledFuture<?> reconnectTask;
    private RpcRequestInitializer initializer;

    public RpcClient(String group, String clientId) {
        this(group, clientId, "127.0.0.1", 5612);
    }

    public RpcClient(String group, String clientId, String host, int port) {
        if (group == null || group.trim().isEmpty() || clientId == null || clientId.trim().isEmpty()) {
            throw new IllegalArgumentException("group and clientId must not be empty");
        }
        this.group = group;
        this.clientId = clientId;
        this.host = host;
        this.port = port;
    }

    public RpcClient setupRpcRequestInitializer(RpcRequestInitializer initializer) {
        this.initializer = initializer;
        return this;
    }

    public RpcClient setActionDelay(long actionDelay) {
        if (actionDelay < 0) {
            throw new IllegalArgumentException("actionDelay must not be negative");
        }
        this.actionDelay = actionDelay;
        return this;
    }

    public void start() {
        synchronized (lifecycleLock) {
            if (started || destroyed) {
                return;
            }
            started = true;
            manualDisconnect = false;
            if (initializer != null) {
                initializer.onRpcRequest(null, handlers);
            }
        }
        connect();
    }

    public boolean isConnected() {
        return connected;
    }

    public void disconnect() {
        synchronized (lifecycleLock) {
            manualDisconnect = true;
            connected = false;
            cancel(heartbeatTask);
            cancel(reconnectTask);
            heartbeatTask = null;
            reconnectTask = null;
            WebSocket oldSocket = socket;
            socket = null;
            if (oldSocket != null) {
                oldSocket.close(1000, "client disconnected");
            }
        }
    }

    public void destroy() {
        synchronized (lifecycleLock) {
            if (destroyed) {
                return;
            }
            destroyed = true;
        }
        disconnect();
        handlers.clear();
        workers.shutdownNow();
        scheduler.shutdownNow();
        httpClient.dispatcher().executorService().shutdown();
        httpClient.connectionPool().evictAll();
    }

    public void destroy(long waitSeconds) {
        destroy();
        try {
            workers.awaitTermination(waitSeconds, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public void sendSuccess(String sequence, Object data) {
        JSONObject payload = baseResponse(sequence);
        payload.put("data", data);
        payload.put("code", 0);
        payload.put("status", 0);
        send(payload);
    }

    public void sendFailed(String sequence, int status, String message) {
        JSONObject payload = baseResponse(sequence);
        payload.put("message", message);
        payload.put("status", status < 0 ? status : -1);
        send(payload);
    }

    public void sendStream(String sequence, String chunk, boolean done, String error) {
        JSONObject payload = baseResponse(sequence);
        payload.put("type", "invoke_stream");
        if (chunk != null) {
            payload.put("data", chunk);
        }
        payload.put("done", done);
        if (error != null) {
            payload.put("error", error);
            payload.put("status", -1);
        }
        send(payload);
    }

    private void connect() {
        if (manualDisconnect || destroyed) {
            return;
        }
        Request request = new Request.Builder().url(buildWebSocketUrl()).build();
        socket = httpClient.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                synchronized (lifecycleLock) {
                    if (destroyed || webSocket != socket) {
                        webSocket.close(1000, "stale connection");
                        return;
                    }
                    connected = true;
                    reconnectAttempts = 0;
                    reconnectTask = null;
                    startHeartbeat();
                }
                reportActions();
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                handleMessage(text);
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                webSocket.close(code, reason);
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                handleDisconnected(webSocket);
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable throwable, Response response) {
                handleDisconnected(webSocket);
            }
        });
    }

    String buildWebSocketUrl() {
        try {
            return "ws://" + host + ":" + port + "/business/register?group="
                    + URLEncoder.encode(group, "UTF-8") + "&clientId="
                    + URLEncoder.encode(clientId, "UTF-8");
        } catch (java.io.UnsupportedEncodingException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private void handleMessage(String text) {
        final JSONObject message;
        try {
            message = JSON.parseObject(text);
        } catch (RuntimeException ignored) {
            return;
        }
        String type = message.getString("type");
        if ("heartbeat".equals(type) || "error".equals(type) || "invoke_response".equals(type)) {
            return;
        }
        String sequence = message.getString("__sekiro_seq__");
        if (sequence == null) {
            sequence = message.getString("sequence");
        }
        String action = message.getString("action");
        if (action == null || action.trim().isEmpty()) {
            if (sequence != null && !sequence.isEmpty()) {
                sendFailed(sequence, -1, "缺少 request 参数 {action}");
            }
            return;
        }
        if (sequence == null || sequence.isEmpty()) {
            return;
        }
        RequestHandler handler = handlers.get(action);
        if (handler == null) {
            sendFailed(sequence, -1, "未定义 action 处理函数：" + action);
            return;
        }
        final RpcRequest request = new RpcRequest(message);
        final RpcResponse response = new RpcResponse(this, sequence);
        workers.execute(() -> {
            try {
                if (actionDelay > 0) {
                    Thread.sleep(actionDelay);
                }
                handler.handleRequest(request, response);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                response.failed("action interrupted");
            } catch (Throwable throwable) {
                response.failed(throwable.getMessage() == null ? throwable.toString() : throwable.getMessage());
            }
        });
    }

    private void reportActions() {
        List<String> actions = handlers.actionList();
        if (actions.isEmpty()) {
            return;
        }
        JSONObject payload = identityMessage("bind");
        payload.put("actions", actions);
        send(payload);
    }

    private void startHeartbeat() {
        cancel(heartbeatTask);
        heartbeatTask = scheduler.scheduleAtFixedRate(() -> send(identityMessage("heartbeat")),
                HEARTBEAT_INTERVAL_MS, HEARTBEAT_INTERVAL_MS, TimeUnit.MILLISECONDS);
    }

    private void handleDisconnected(WebSocket webSocket) {
        synchronized (lifecycleLock) {
            if (webSocket != socket) {
                return;
            }
            connected = false;
            socket = null;
            cancel(heartbeatTask);
            heartbeatTask = null;
            scheduleReconnect();
        }
    }

    private void scheduleReconnect() {
        if (manualDisconnect || destroyed || (reconnectTask != null && !reconnectTask.isDone())) {
            return;
        }
        reconnectAttempts++;
        long delay = reconnectDelay(reconnectAttempts);
        reconnectTask = scheduler.schedule(() -> {
            synchronized (lifecycleLock) {
                reconnectTask = null;
            }
            connect();
        }, delay, TimeUnit.MILLISECONDS);
    }

    static long reconnectDelay(int attempt) {
        int exponent = Math.min(Math.max(attempt - 1, 0), 6);
        return Math.min(1_000L << exponent, MAX_RECONNECT_DELAY_MS);
    }

    private JSONObject identityMessage(String type) {
        JSONObject payload = new JSONObject();
        payload.put("type", type);
        payload.put("group", group);
        payload.put("clientId", clientId);
        payload.put("timestamp", System.currentTimeMillis());
        return payload;
    }

    private JSONObject baseResponse(String sequence) {
        JSONObject payload = new JSONObject();
        payload.put("__sekiro_seq__", sequence);
        return payload;
    }

    private void send(JSONObject payload) {
        WebSocket current = socket;
        if (connected && current != null) {
            current.send(payload.toJSONString());
        }
    }

    private static void cancel(ScheduledFuture<?> task) {
        if (task != null) {
            task.cancel(false);
        }
    }
}
