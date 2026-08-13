package cn.iinti.sekiro3.business.api;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import cn.iinti.sekiro3.business.api.interfaze.InvocationContext;
import cn.iinti.sekiro3.business.api.interfaze.RpcCancellationToken;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.Assume;
import okio.ByteString;
import org.junit.Test;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class RpcClientTest {
    @Test
    public void formalClientHasConfirmedReadySurface() {
        RpcClient client = new RpcClient("g", "c");
        assertFalse(client.isConnected());
        client.destroy();
    }

    @Test
    public void realServerConformanceTarget() throws Exception {
        String baseUrl = System.getProperty("rpc.test.baseUrl", "");
        Assume.assumeTrue(!baseUrl.isEmpty());
        JSONObject fixture = JSON.parseObject(new String(Files.readAllBytes(Paths.get("..", "..", "conformance", "fixtures", "invoke-context-v1.json")), StandardCharsets.UTF_8));
        Set<String> fields = new HashSet<>();
        for (Object field : fixture.getJSONArray("rpc_context_required_fields")) {
            fields.add(String.valueOf(field));
        }
        assertEquals(new HashSet<>(Arrays.asList("sequence", "trace_id", "group", "action", "client_id", "deadline_unix_ms", "idempotent", "idempotency_key", "attempt")), fields);
        URI base = URI.create(baseUrl);
        String group = "conformance-java";
        String clientId = "java-client";
        RpcClient client = new RpcClient(group, clientId, "ws", base.getHost(), base.getPort(), null);
        AtomicReference<InvocationContext> received = new AtomicReference<>();
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "conformance.echo", (rpcRequest, response) -> {
                    received.set(rpcRequest.getInvocationContext());
                    JSONObject data = new JSONObject();
                    data.put("echo", rpcRequest.getString("echo"));
                    data.put("group", rpcRequest.getInvocationContext().getGroup());
                    data.put("clientId", rpcRequest.getInvocationContext().getClientId());
                    data.put("trace_id", rpcRequest.getInvocationContext().getTraceId());
                    response.success(data);
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(5, TimeUnit.SECONDS));
            java.util.concurrent.FutureTask<JSONObject> request = new java.util.concurrent.FutureTask<>(
                    () -> postInvoke(baseUrl, group));
            new Thread(request, "java-conformance-http").start();
            JSONObject response = request.get(10, TimeUnit.SECONDS);
            InvocationContext context = received.get();
            assertEquals(0, response.getIntValue("code"));
            assertEquals(group, response.getString("group"));
            assertEquals(clientId, response.getString("clientId"));
            assertTrue(response.getString("trace_id") != null && !response.getString("trace_id").isEmpty());
            JSONObject data = response.getJSONObject("data");
            if (data == null) {
                data = response;
            }
            assertEquals("java", data.getString("echo"));
            assertEquals(group, data.getString("group"));
            assertEquals(clientId, data.getString("clientId"));
            assertTrue(data.getString("trace_id") != null && !data.getString("trace_id").isEmpty());
            assertNotNull(context);
            assertEquals(group, context.getGroup());
            assertEquals(clientId, context.getClientId());
            assertEquals("conformance.echo", context.getAction());
            assertTrue(context.getSequence() != null && !context.getSequence().isEmpty());
            assertTrue(context.getTraceId() != null && !context.getTraceId().isEmpty());
            assertEquals(response.getString("trace_id"), context.getTraceId());
            assertTrue(context.getDeadlineUnixMs() > 0);
            assertFalse(context.isIdempotent());
            assertEquals("", context.getIdempotencyKey());
            assertEquals(1, context.getAttempt());
        } finally {
            client.destroy(2);
        }
    }

    private static JSONObject postInvoke(String baseUrl, String group) throws Exception {
        URL url = URI.create(baseUrl + "/business/invoke").toURL();
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        try {
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(10000);
        connection.setRequestProperty("Content-Type", "application/json");
        byte[] body = ("{\"group\":\"" + group + "\",\"action\":\"conformance.echo\","
                + "\"params\":{\"echo\":\"java\"}}").getBytes(StandardCharsets.UTF_8);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(body);
        }
        StringBuilder text = new StringBuilder();
        if (connection.getResponseCode() < 200 || connection.getResponseCode() >= 300) {
            throw new IllegalStateException("HTTP status " + connection.getResponseCode());
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                connection.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                text.append(line);
            }
        }
        return JSON.parseObject(text.toString());
        } finally {
            connection.disconnect();
        }
    }

    @Test
    public void registeredConfirmationPrecedesSortedBindAndContextResponse() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                if (message.contains("\"type\":\"bind\"")) {
                    webSocket.send("{\"type\":\"invoke\",\"action\":\"echo\","
                            + "\"__sekiro_seq__\":\"seq-1\",\"group\":\"g\","
                            + "\"clientId\":\"c\",\"trace_id\":\"trace-1\","
                            + "\"value\":7,\"__rpc_context__\":{"
                            + "\"sequence\":\"seq-1\",\"trace_id\":\"trace-1\","
                            + "\"group\":\"g\",\"action\":\"echo\","
                            + "\"client_id\":\"c\",\"deadline_unix_ms\":4102444800000,"
                            + "\"idempotent\":false,\"idempotency_key\":\"\","
                            + "\"attempt\":1}}");
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), "secret");
        client.setupRpcRequestInitializer((request, handlers) -> {
            handlers.registerRpcHandler("zeta", (rpcRequest, response) -> response.success(1));
            handlers.registerRpcHandler("echo", (rpcRequest, response) -> {
                assertEquals("seq-1", rpcRequest.getInvocationContext().getSequence());
                assertFalse(rpcRequest.getCancellationToken().isCancelled());
                response.success(rpcRequest.getIntValue("value"));
            });
        });
        try {
            client.start();
            RecordedRequest upgrade = server.takeRequest(2, TimeUnit.SECONDS);
            assertNotNull(upgrade);
            assertEquals("Bearer secret", upgrade.getHeader("Authorization"));
            assertEquals("1", upgrade.getRequestUrl().queryParameter("protocol_version"));
            assertEquals("invocation_context.v1",
                    upgrade.getRequestUrl().queryParameter("capabilities"));
            assertEquals("g", upgrade.getRequestUrl().queryParameter("group"));
            assertEquals("c", upgrade.getRequestUrl().queryParameter("clientId"));
            assertNull(upgrade.getRequestUrl().queryParameter("token"));
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(client.isConnected());
            JSONObject bindMessage = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals("bind", bindMessage.getString("type"));
            assertEquals("g", bindMessage.getString("group"));
            assertEquals("c", bindMessage.getString("clientId"));
            assertEquals("[\"echo\",\"zeta\"]", bindMessage.getJSONArray("actions").toJSONString());
            String reply = received.poll(2, TimeUnit.SECONDS);
            JSONObject responseMessage = JSON.parseObject(reply);
            assertEquals("seq-1", responseMessage.getString("__sekiro_seq__"));
            assertEquals("g", responseMessage.getString("group"));
            assertEquals("c", responseMessage.getString("clientId"));
            assertEquals("trace-1", responseMessage.getString("trace_id"));
            assertEquals(7, responseMessage.getIntValue("data"));
            assertEquals(0, responseMessage.getIntValue("status"));
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void openingWithoutConfirmationNeverBecomesReady() throws Exception {
        MockWebServer server = new MockWebServer();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertFalse(client.awaitReady(100, TimeUnit.MILLISECONDS));
            assertFalse(client.isConnected());
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void closeBeforeConfirmationUnblocksLongAwaitAndAllowsNoBind() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.close(1000, "not confirmed");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        long started = System.nanoTime();
        try {
            client.start();
            assertFalse(client.awaitReady(5, TimeUnit.SECONDS));
            assertTrue(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started) < 1_000);
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void immediateRegisteredCallbackStillPublishesReady() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
            client.destroy();
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void stringProtocolVersionIsRejectedWithoutBind() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":\"1\","
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertFalse(client.awaitReady(2, TimeUnit.SECONDS));
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void duplicateRegisteredBindsOnceAndRemoteCloseCanRestart() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        WebSocketListener listener = new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                            + "\"capabilities\":[\"invocation_context.v1\"]}");
                    webSocket.close(1000, "restart");
                }
            }
        };
        server.enqueue(new MockResponse().withWebSocketUpgrade(listener));
        server.enqueue(new MockResponse().withWebSocketUpgrade(listener));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
            assertFalse(client.awaitReady(200, TimeUnit.MILLISECONDS));
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void staleRegistrationFromPreviousSocketCannotReadyCurrentLifecycle() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        CountDownLatch firstClosed = new CountDownLatch(1);
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                firstClosed.countDown();
                webSocket.close(1000, "first");
            }
        }));
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                // The new lifecycle must wait for its own confirmation.
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertTrue(firstClosed.await(2, TimeUnit.SECONDS));
            assertFalse(client.awaitReady(200, TimeUnit.MILLISECONDS));
            client.start();
            assertFalse(client.awaitReady(200, TimeUnit.MILLISECONDS));
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void missingTopLevelMetadataUsesValidatedContextForFailureResponse() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessage("seq-context", null, null, null,
                            "trace-context"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> fail("invalid metadata must not dispatch")));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
            JSONObject failure = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals("seq-context", failure.getString("__sekiro_seq__"));
            assertEquals("g", failure.getString("group"));
            assertEquals("c", failure.getString("clientId"));
            assertEquals("trace-context", failure.getString("trace_id"));
            assertTrue(failure.getIntValue("status") < 0);
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void mismatchedContextDoesNotInvokeHandlerAndReturnsOneError() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        AtomicInteger calls = new AtomicInteger();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                JSONObject outbound = JSON.parseObject(message);
                if ("bind".equals(outbound.getString("type"))) {
                    webSocket.send(invokeMessage("seq-mismatch", "g", "c", "trace-top",
                            "trace-context"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> calls.incrementAndGet()));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
            JSONObject failure = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals(0, calls.get());
            assertEquals("seq-mismatch", failure.getString("__sekiro_seq__"));
            assertEquals("g", failure.getString("group"));
            assertEquals("c", failure.getString("clientId"));
            assertEquals("trace-top", failure.getString("trace_id"));
            assertTrue(failure.getIntValue("status") < 0);
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void actionDelayAndThrowableProduceObservableSingleResponses() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        AtomicLong sentAt = new AtomicLong();
        AtomicLong startedAt = new AtomicLong();
        CountDownLatch handlerStarted = new CountDownLatch(1);
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    sentAt.set(System.nanoTime());
                    webSocket.send(invokeMessage("seq-delay", "g", "c", "trace-delay",
                            "trace-delay"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null).setActionDelay(120);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    startedAt.set(System.nanoTime());
                    handlerStarted.countDown();
                    throw new IllegalStateException("boom");
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
            assertTrue(TimeUnit.NANOSECONDS.toMillis(startedAt.get() - sentAt.get()) >= 80);
            JSONObject bind = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals("bind", bind.getString("type"));
            JSONObject failure = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals("seq-delay", failure.getString("__sekiro_seq__"));
            assertEquals("g", failure.getString("group"));
            assertEquals("c", failure.getString("clientId"));
            assertEquals("trace-delay", failure.getString("trace_id"));
            assertTrue(failure.getIntValue("status") < 0);
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void streamResponsesRetainMetadataAndOnlyFinalizesOnce() throws Exception {
        MockWebServer server = new MockWebServer();
        BlockingQueue<String> received = new LinkedBlockingQueue<>();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                received.add(message);
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessage("seq-stream", "g", "c", "trace-stream",
                            "trace-stream"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    response.sendStreamChunk("part");
                    response.endStream();
                    response.endStream();
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertEquals("bind", JSON.parseObject(received.poll(2, TimeUnit.SECONDS))
                    .getString("type"));
            JSONObject chunk = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            JSONObject end = JSON.parseObject(received.poll(2, TimeUnit.SECONDS));
            assertEquals("invoke_stream", chunk.getString("type"));
            assertFalse(chunk.getBooleanValue("done"));
            assertEquals("g", chunk.getString("group"));
            assertEquals("c", chunk.getString("clientId"));
            assertEquals("trace-stream", chunk.getString("trace_id"));
            assertTrue(end.getBooleanValue("done"));
            assertEquals("g", end.getString("group"));
            assertEquals("c", end.getString("clientId"));
            assertEquals("trace-stream", end.getString("trace_id"));
            assertNull(received.poll(200, TimeUnit.MILLISECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void handlerDestroyWithPositiveWaitDoesNotSelfWait() throws Exception {
        MockWebServer server = new MockWebServer();
        CountDownLatch finished = new CountDownLatch(1);
        AtomicLong elapsed = new AtomicLong();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessage("seq-destroy", "g", "c", "trace-destroy",
                            "trace-destroy"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    long started = System.nanoTime();
                    client.destroy(5);
                    elapsed.set(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
                    finished.countDown();
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(finished.await(2, TimeUnit.SECONDS));
            assertTrue(elapsed.get() < 1_000);
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void publicCompatibilityOverloadsCompileAndDelayIsConfigured() {
        RpcClient client = new RpcClient("g", "c").setActionDelay(25);
        client.sendSuccess("seq", "data");
        client.sendFailed("seq", -1, "failed");
        client.sendStream("seq", "chunk", false, null);
        client.destroy();
    }

    @Test
    public void invocationContextRejectsNonExactNumbersAndUnknownKeys() {
        JSONObject message = validContextMessage();
        message.getJSONObject("__rpc_context__").put("deadline_unix_ms", new BigDecimal("1.5"));
        assertInvalidContext(message);

        message = validContextMessage();
        message.getJSONObject("__rpc_context__").put("attempt", new BigInteger("2147483648"));
        assertInvalidContext(message);

        message = validContextMessage();
        message.getJSONObject("__rpc_context__").remove("attempt");
        message.getJSONObject("__rpc_context__").put("extra", 1);
        assertInvalidContext(message);
    }

    @Test
    public void cancellationTokenIsReadOnlyToHandlers() throws Exception {
        assertNull(RpcCancellationToken.class.getMethod("getClass") == null ? null
                : findPublicMethod("cancel"));
    }

    @Test
    public void binaryFramesAreRejectedWithoutDispatch() throws Exception {
        MockWebServer server = new MockWebServer();
        CountDownLatch closed = new CountDownLatch(1);
        AtomicInteger closeCode = new AtomicInteger();
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send(ByteString.encodeUtf8("{}"));
            }

            @Override
            public void onClosing(WebSocket webSocket, int code, String reason) {
                closeCode.set(code);
                closed.countDown();
                webSocket.close(code, reason);
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        try {
            client.start();
            assertTrue(closed.await(2, TimeUnit.SECONDS));
            assertEquals(1003, closeCode.get());
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void oversizedBinaryAndTextFramesCloseBeforeParsing() throws Exception {
        for (boolean text : new boolean[]{false, true}) {
            MockWebServer server = new MockWebServer();
            CountDownLatch closed = new CountDownLatch(1);
            AtomicInteger closeCode = new AtomicInteger();
            server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
                @Override
                public void onOpen(WebSocket webSocket, Response response) {
                    if (text) {
                        StringBuilder payload = new StringBuilder(10 * 1024 * 1024 + 1);
                        for (int i = 0; i <= 10 * 1024 * 1024; i++) {
                            payload.append('x');
                        }
                        webSocket.send(payload.toString());
                    } else {
                        webSocket.send(ByteString.of(new byte[10 * 1024 * 1024 + 1]));
                    }
                }

                @Override
                public void onClosing(WebSocket webSocket, int code, String reason) {
                    closeCode.set(code);
                    closed.countDown();
                    webSocket.close(code, reason);
                }
            }));
            server.start();
            RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                    server.getPort(), null);
            try {
                client.start();
                assertTrue(closed.await(5, TimeUnit.SECONDS));
                assertEquals(1009, closeCode.get());
            } finally {
                client.destroy();
                safeShutdown(server);
            }
        }
    }

    @Test
    public void deadlineCancelsContextTokenWithoutPublicCancelMethod() throws Exception {
        MockWebServer server = new MockWebServer();
        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch cancelled = new CountDownLatch(1);
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessageWithDeadline("seq-deadline", 1));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    handlerStarted.countDown();
                    while (!rpcRequest.getCancellationToken().isCancelled()) {
                        Thread.yield();
                    }
                    cancelled.countDown();
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
            assertTrue(cancelled.await(2, TimeUnit.SECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void disconnectCancelsActiveContextToken() throws Exception {
        MockWebServer server = new MockWebServer();
        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch cancelled = new CountDownLatch(1);
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessage("seq-disconnect", "g", "c",
                            "trace-disconnect", "trace-disconnect"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    handlerStarted.countDown();
                    while (!rpcRequest.getCancellationToken().isCancelled()) {
                        Thread.yield();
                    }
                    cancelled.countDown();
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
            client.disconnect();
            assertTrue(cancelled.await(2, TimeUnit.SECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    @Test
    public void destroyCancelsActiveContextToken() throws Exception {
        MockWebServer server = new MockWebServer();
        CountDownLatch handlerStarted = new CountDownLatch(1);
        CountDownLatch cancelled = new CountDownLatch(1);
        server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener() {
            @Override
            public void onOpen(WebSocket webSocket, Response response) {
                webSocket.send("{\"type\":\"registered\",\"protocol_version\":1,"
                        + "\"capabilities\":[\"invocation_context.v1\"]}");
            }

            @Override
            public void onMessage(WebSocket webSocket, String message) {
                if ("bind".equals(JSON.parseObject(message).getString("type"))) {
                    webSocket.send(invokeMessage("seq-destroy-cancel", "g", "c",
                            "trace-destroy-cancel", "trace-destroy-cancel"));
                }
            }
        }));
        server.start();
        RpcClient client = new RpcClient("g", "c", "ws", server.getHostName(),
                server.getPort(), null);
        client.setupRpcRequestInitializer((request, handlers) -> handlers.registerRpcHandler(
                "echo", (rpcRequest, response) -> {
                    handlerStarted.countDown();
                    while (!rpcRequest.getCancellationToken().isCancelled()) {
                        Thread.yield();
                    }
                    cancelled.countDown();
                }));
        try {
            client.start();
            assertTrue(client.awaitReady(2, TimeUnit.SECONDS));
            assertTrue(handlerStarted.await(2, TimeUnit.SECONDS));
            client.destroy();
            assertTrue(cancelled.await(2, TimeUnit.SECONDS));
        } finally {
            client.destroy();
            safeShutdown(server);
        }
    }

    private static void safeShutdown(MockWebServer server) {
        try {
            server.shutdown();
        } catch (java.io.IOException ignored) {
            // Client cancellation can race MockWebServer's websocket executor shutdown.
        }
    }

    private static JSONObject validContextMessage() {
        JSONObject context = new JSONObject();
        context.put("sequence", "seq");
        context.put("trace_id", "trace");
        context.put("group", "g");
        context.put("action", "echo");
        context.put("client_id", "c");
        context.put("deadline_unix_ms", 1L);
        context.put("idempotent", false);
        context.put("idempotency_key", "");
        context.put("attempt", 1);
        JSONObject message = new JSONObject();
        message.put("__rpc_context__", context);
        return message;
    }

    private static String invokeMessage(String sequence, String group, String clientId,
                                        String topTrace, String contextTrace) {
        return invokeMessageWithDeadline(sequence, group, clientId, topTrace, contextTrace,
                4102444800000L);
    }

    private static String invokeMessageWithDeadline(String sequence, long deadline) {
        return invokeMessageWithDeadline(sequence, "g", "c", "trace-deadline",
                "trace-deadline", deadline);
    }

    private static String invokeMessageWithDeadline(String sequence, String group,
                                                    String clientId, String topTrace,
                                                    String contextTrace, long deadline) {
        JSONObject context = new JSONObject();
        context.put("sequence", sequence);
        context.put("trace_id", contextTrace);
        context.put("group", "g");
        context.put("action", "echo");
        context.put("client_id", "c");
        context.put("deadline_unix_ms", deadline);
        context.put("idempotent", false);
        context.put("idempotency_key", "");
        context.put("attempt", 1);
        JSONObject message = new JSONObject();
        message.put("type", "invoke");
        message.put("action", "echo");
        message.put("__sekiro_seq__", sequence);
        if (group != null) {
            message.put("group", group);
        }
        if (clientId != null) {
            message.put("clientId", clientId);
        }
        if (topTrace != null) {
            message.put("trace_id", topTrace);
        }
        message.put("value", 7);
        message.put("__rpc_context__", context);
        return message.toJSONString();
    }

    private static void assertInvalidContext(JSONObject message) {
        try {
            InvocationContext.fromMessage(message);
            fail("expected invalid context");
        } catch (IllegalArgumentException expected) {
            // expected
        }
    }

    private static java.lang.reflect.Method findPublicMethod(String name) {
        for (java.lang.reflect.Method method : RpcCancellationToken.class.getMethods()) {
            if (method.getName().equals(name)) {
                return method;
            }
        }
        return null;
    }
}
