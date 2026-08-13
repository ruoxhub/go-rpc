package cn.iinti.sekiro3.business.api;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import cn.iinti.sekiro3.business.api.interfaze.HandlerRegistry;
import cn.iinti.sekiro3.business.api.interfaze.InvocationContext;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcCancellationToken;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequestInitializer;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class RpcClient {
    private static final long HEARTBEAT_INTERVAL_MS = 25_000L;
    private static final long MAX_MESSAGE_BYTES = 10L * 1024 * 1024;
    private static final ThreadLocal<Boolean> IN_HANDLER = new ThreadLocal<>();

    private final String group;
    private final String clientId;
    private final String scheme;
    private final String host;
    private final int port;
    private final String token;
    private final HandlerRegistry handlers = new HandlerRegistry();
    private final OkHttpClient httpClient = new OkHttpClient.Builder().build();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();
    private final ExecutorService workers = Executors.newCachedThreadPool();
    private final Set<MutableToken> activeTokens = ConcurrentHashMap.newKeySet();
    private final Object lock = new Object();
    private volatile WebSocket socket;
    private volatile ConnectionState currentState;
    private volatile boolean connected;
    private volatile boolean started;
    private volatile boolean destroyed;
    private volatile long actionDelay;
    private volatile CountDownLatch readyLatch = new CountDownLatch(0);
    private volatile boolean readyResult;
    private volatile ScheduledFuture<?> heartbeat;
    private RpcRequestInitializer initializer;

    public RpcClient(String group, String clientId) {
        this(group, clientId, "ws", "127.0.0.1", 5612, null);
    }

    public RpcClient(String group, String clientId, String host, int port) {
        this(group, clientId, "ws", host, port, null);
    }

    public RpcClient(String group, String clientId, String scheme, String host, int port,
                     String token) {
        if (blank(group) || blank(clientId) || blank(host)) {
            throw new IllegalArgumentException("group, clientId and host required");
        }
        if (!"ws".equals(scheme) && !"wss".equals(scheme)) {
            throw new IllegalArgumentException("scheme must be ws or wss");
        }
        this.group = group;
        this.clientId = clientId;
        this.scheme = scheme;
        this.host = host;
        this.port = port;
        this.token = token;
    }

    private static boolean blank(String value) {
        return value == null || value.trim().isEmpty();
    }

    public RpcClient setupRpcRequestInitializer(RpcRequestInitializer value) {
        initializer = value;
        return this;
    }

    public RpcClient setActionDelay(long value) {
        if (value < 0) {
            throw new IllegalArgumentException("actionDelay must not be negative");
        }
        actionDelay = value;
        return this;
    }

    public void start() {
        ConnectionState state;
        synchronized (lock) {
            if (started || destroyed) {
                return;
            }
            started = true;
            connected = false;
            readyResult = false;
            readyLatch = new CountDownLatch(1);
            state = new ConnectionState();
            currentState = state;
            if (initializer != null) {
                initializer.onRpcRequest(null, handlers);
            }
        }
        Request.Builder builder = new Request.Builder().url(buildWebSocketUrl());
        if (!blank(token)) {
            builder.header("Authorization", "Bearer " + token);
        }
        WebSocket candidate = httpClient.newWebSocket(builder.build(), newListener(state));
        synchronized (lock) {
            if (destroyed || !started || currentState != state || state.failed) {
                candidate.cancel();
                return;
            }
            state.socket = candidate;
            socket = candidate;
        }
    }

    public boolean awaitReady(long timeout, TimeUnit unit) {
        try {
            return readyLatch.await(timeout, unit) && readyResult && connected && !destroyed;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    public boolean isConnected() {
        return connected;
    }

    public void disconnect() {
        signalReady(false);
        closeSocket();
    }

    public void destroy() {
        synchronized (lock) {
            if (destroyed) {
                return;
            }
            destroyed = true;
        }
        signalReady(false);
        closeSocket();
        handlers.clear();
        workers.shutdownNow();
        scheduler.shutdownNow();
        httpClient.dispatcher().executorService().shutdown();
        httpClient.connectionPool().evictAll();
    }

    public void destroy(long waitSeconds) {
        destroy();
        if (Boolean.TRUE.equals(IN_HANDLER.get())) {
            return;
        }
        try {
            workers.awaitTermination(waitSeconds, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    String buildWebSocketUrl() {
        try {
            return scheme + "://" + host + ":" + port + "/business/register?"
                    + "protocol_version=1&capabilities="
                    + URLEncoder.encode("invocation_context.v1", "UTF-8")
                    + "&group=" + URLEncoder.encode(group, "UTF-8")
                    + "&clientId=" + URLEncoder.encode(clientId, "UTF-8");
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private WebSocketListener newListener(ConnectionState state) {
        return new WebSocketListener() {
        @Override
        public void onOpen(WebSocket webSocket, Response response) {
            synchronized (lock) {
                if (destroyed || !started || currentState != state) {
                    webSocket.cancel();
                    return;
                }
                state.socket = webSocket;
                socket = webSocket;
            }
            if (!isCurrent(state, webSocket)) {
                webSocket.cancel();
            }
        }

        @Override
        public void onMessage(WebSocket webSocket, String text) {
            if (isCurrent(state, webSocket)) {
                handleMessage(state, webSocket, text);
            }
        }

        @Override
        public void onMessage(WebSocket webSocket, ByteString bytes) {
            if (!isCurrent(state, webSocket)) {
                return;
            }
            if (bytes.size() > MAX_MESSAGE_BYTES) {
                webSocket.close(1009, "message too large");
            } else {
                webSocket.close(1003, "binary unsupported");
            }
        }

        @Override
        public void onClosing(WebSocket webSocket, int code, String reason) {
            webSocket.close(code, reason);
        }

        @Override
        public void onClosed(WebSocket webSocket, int code, String reason) {
            gone(state, webSocket);
        }

        @Override
        public void onFailure(WebSocket webSocket, Throwable throwable, Response response) {
            gone(state, webSocket);
        }
        };
    }

    private boolean isCurrent(ConnectionState state, WebSocket webSocket) {
        return !destroyed && started && currentState == state
                && (state.socket == null || state.socket == webSocket)
                && (socket == null || socket == webSocket);
    }

    private void handleMessage(ConnectionState state, WebSocket webSocket, String text) {
        if (text.getBytes(StandardCharsets.UTF_8).length > MAX_MESSAGE_BYTES) {
            webSocket.close(1009, "message too large");
            return;
        }
        JSONObject message;
        try {
            message = JSON.parseObject(text);
        } catch (RuntimeException exception) {
            return;
        }
        if (message == null) {
            return;
        }
        String type = message.getString("type");
        if ("registered".equals(type)) {
            handleRegistration(state, webSocket, message);
            return;
        }
        if (!connected || "heartbeat".equals(type) || "error".equals(type)
                || "invoke_response".equals(type)) {
            return;
        }
        dispatchInvocation(message);
    }

    private void handleRegistration(ConnectionState state, WebSocket webSocket,
                                    JSONObject message) {
        JSONArray capabilities = message.getJSONArray("capabilities");
        Object protocolVersion = message.get("protocol_version");
        boolean valid = isExactOne(protocolVersion)
                && capabilities != null && capabilities.contains("invocation_context.v1");
        synchronized (lock) {
            if (!isCurrent(state, webSocket) || connected) {
                return;
            }
            if (!valid) {
                signalReady(false);
            } else {
                JSONObject bind = identity("bind");
                bind.put("actions", handlers.actionList());
                if (!send(bind)) {
                    signalReady(false);
                } else {
                    try {
                        heartbeat = scheduler.scheduleAtFixedRate(
                                () -> send(identity("heartbeat")), HEARTBEAT_INTERVAL_MS,
                                HEARTBEAT_INTERVAL_MS, TimeUnit.MILLISECONDS);
                    } catch (RuntimeException exception) {
                        signalReady(false);
                        heartbeat = null;
                    }
                    if (heartbeat != null) {
                        connected = true;
                        readyResult = true;
                        signalReady(true);
                        return;
                    }
                }
            }
        }
        closeSocket();
    }

    private static boolean isExactOne(Object value) {
        return value instanceof Integer && ((Integer) value) == 1
                || value instanceof Long && ((Long) value) == 1L;
    }

    private void dispatchInvocation(JSONObject message) {
        String sequence = message.getString("__sekiro_seq__");
        String alternateSequence = message.getString("sequence");
        if (sequence == null) {
            sequence = alternateSequence;
        }
        String action = message.getString("action");
        if (sequence == null || action == null) {
            return;
        }
        RequestHandler handler = handlers.get(action);
        if (handler == null) {
            sendFailed(sequence, -1, "no handler", message.getString("group"),
                    message.getString("clientId"), message.getString("trace_id"));
            return;
        }
        InvocationContext context;
        try {
            context = InvocationContext.fromMessage(message);
            validateMatch(message, context);
        } catch (IllegalArgumentException exception) {
            sendFailed(sequence, -1, "invalid invocation context",
                    message.getString("group"), message.getString("clientId"),
                    message.getString("trace_id"));
            return;
        }

        MutableToken tokenState = new MutableToken();
        activeTokens.add(tokenState);
        RpcRequest request = new RpcRequest(message, context, tokenState);
        RpcResponse response = new RpcResponse(this, sequence, context.getGroup(),
                context.getClientId(), context.getTraceId());
        ScheduledFuture<?> deadline = scheduleDeadline(context, tokenState);
        workers.execute(() -> {
            IN_HANDLER.set(Boolean.TRUE);
            try {
                if (actionDelay > 0) {
                    Thread.sleep(actionDelay);
                }
                handler.handleRequest(request, response);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                response.failed("action interrupted");
            } catch (Throwable throwable) {
                String messageText = throwable.getMessage();
                response.failed(messageText == null ? throwable.toString() : messageText);
            } finally {
                IN_HANDLER.remove();
                activeTokens.remove(tokenState);
                if (deadline != null) {
                    deadline.cancel(false);
                }
            }
        });
    }

    private ScheduledFuture<?> scheduleDeadline(InvocationContext context, MutableToken tokenState) {
        if (context.getDeadlineUnixMs() <= 0) {
            return null;
        }
        long delay = Math.max(0L, context.getDeadlineUnixMs() - System.currentTimeMillis());
        return scheduler.schedule(tokenState::cancelToken, delay, TimeUnit.MILLISECONDS);
    }

    private static void validateMatch(JSONObject message, InvocationContext context) {
        String protocolSequence = message.getString("__sekiro_seq__");
        String sequence = message.getString("sequence");
        if ((protocolSequence == null && sequence == null)
                || (protocolSequence != null && !protocolSequence.equals(context.getSequence()))
                || (sequence != null && !sequence.equals(context.getSequence()))) {
            throw new IllegalArgumentException("sequence mismatch");
        }
        compareIfPresent(message, "trace_id", context.getTraceId());
        compareIfPresent(message, "group", context.getGroup());
        compareIfPresent(message, "action", context.getAction());
        compareIfPresent(message, "clientId", context.getClientId());
        compareIfPresent(message, "client_id", context.getClientId());
    }

    private static void compareIfPresent(JSONObject message, String key, String expected) {
        if (message.containsKey(key) && !expected.equals(message.getString(key))) {
            throw new IllegalArgumentException(key + " mismatch");
        }
    }

    private JSONObject identity(String type) {
        JSONObject message = new JSONObject();
        message.put("type", type);
        message.put("group", group);
        message.put("clientId", clientId);
        message.put("timestamp", System.currentTimeMillis());
        return message;
    }

    private boolean send(JSONObject message) {
        WebSocket current = socket;
        if (current == null || (!connected && !"bind".equals(message.getString("type")))) {
            return false;
        }
        return current.send(message.toJSONString());
    }

    public void sendSuccess(String sequence, Object data) {
        sendSuccess(sequence, data, null, null, null);
    }

    public void sendSuccess(String sequence, Object data, String group, String clientId,
                            String traceId) {
        JSONObject message = base(sequence, group, clientId, traceId);
        message.put("data", data);
        message.put("code", 0);
        message.put("status", 0);
        send(message);
    }

    public void sendFailed(String sequence, int status, String message) {
        sendFailed(sequence, status, message, null, null, null);
    }

    public void sendFailed(String sequence, int status, String error, String group,
                           String clientId, String traceId) {
        JSONObject message = base(sequence, group, clientId, traceId);
        message.put("message", error);
        message.put("status", status < 0 ? status : -1);
        send(message);
    }

    public void sendStream(String sequence, String chunk, boolean done, String error) {
        sendStream(sequence, chunk, done, error, null, null, null);
    }

    public void sendStream(String sequence, String chunk, boolean done, String error,
                           String group, String clientId, String traceId) {
        JSONObject message = base(sequence, group, clientId, traceId);
        message.put("type", "invoke_stream");
        if (chunk != null) {
            message.put("data", chunk);
        }
        message.put("done", done);
        if (error != null) {
            message.put("error", error);
            message.put("status", -1);
        }
        send(message);
    }

    private JSONObject base(String sequence, String group, String clientId, String traceId) {
        JSONObject message = new JSONObject();
        message.put("__sekiro_seq__", sequence);
        if (group != null) {
            message.put("group", group);
        }
        if (clientId != null) {
            message.put("clientId", clientId);
        }
        if (traceId != null) {
            message.put("trace_id", traceId);
        }
        return message;
    }

    private void cancelActive() {
        for (MutableToken tokenState : activeTokens) {
            tokenState.cancelToken();
        }
    }

    private void signalReady(boolean result) {
        CountDownLatch latch = readyLatch;
        readyResult = result;
        latch.countDown();
    }

    private void gone(ConnectionState state, WebSocket webSocket) {
        synchronized (lock) {
            if (!isCurrent(state, webSocket)) {
                return;
            }
            state.failed = true;
            connected = false;
            started = false;
            socket = null;
            currentState = null;
            stopHeartbeat();
            signalReady(false);
        }
        cancelActive();
    }

    private void closeSocket() {
        WebSocket current;
        synchronized (lock) {
            connected = false;
            started = false;
            current = socket;
            socket = null;
            currentState = null;
            stopHeartbeat();
        }
        cancelActive();
        if (current != null) {
            current.close(1000, "client closed");
            current.cancel();
        }
    }

    private void stopHeartbeat() {
        if (heartbeat != null) {
            heartbeat.cancel(false);
            heartbeat = null;
        }
    }

    private static final class MutableToken extends RpcCancellationToken {
        private void cancelToken() {
            cancelInternal();
        }
    }

    private static final class ConnectionState {
        private volatile WebSocket socket;
        private volatile boolean failed;
    }
}
