package cn.iinti.sekiro3.business.api;
import org.junit.Test;
import okhttp3.mockwebserver.*;
import okhttp3.*;
import com.alibaba.fastjson.JSON;
import java.util.concurrent.*;
import cn.iinti.sekiro3.business.api.interfaze.*;
import static org.junit.Assert.*;
 public class RpcClientTest {
 @Test public void formalClientHasConfirmedReadySurface(){ RpcClient c=new RpcClient("g","c"); assertFalse(c.isConnected()); c.destroy(); }
 @Test public void registeredConfirmationPrecedesSortedBindAndContextResponse() throws Exception {
  MockWebServer server=new MockWebServer(); final BlockingQueue<String> received=new LinkedBlockingQueue<>();
  server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener(){public void onOpen(WebSocket w,Response r){w.send("{\"type\":\"registered\",\"protocol_version\":1,\"capabilities\":[\"invocation_context.v1\"]}");} public void onMessage(WebSocket w,String s){received.add(s); if(s.contains("\"type\":\"bind\"")) w.send("{\"type\":\"invoke\",\"action\":\"echo\",\"__sekiro_seq__\":\"seq-1\",\"group\":\"g\",\"clientId\":\"c\",\"trace_id\":\"trace-1\",\"value\":7,\"__rpc_context__\":{\"sequence\":\"seq-1\",\"trace_id\":\"trace-1\",\"group\":\"g\",\"action\":\"echo\",\"client_id\":\"c\",\"deadline_unix_ms\":4102444800000,\"idempotent\":false,\"idempotency_key\":\"\",\"attempt\":1}}");}}));
  server.start(); RpcClient c=new RpcClient("g","c","ws",server.getHostName(),server.getPort(),"secret"); final CountDownLatch response=new CountDownLatch(1); c.setupRpcRequestInitializer((r,h)->{h.registerRpcHandler("zeta",(q,x)->x.success(1));h.registerRpcHandler("echo",(q,x)->{assertEquals("seq-1",q.getInvocationContext().getSequence());assertFalse(q.getCancellationToken().isCancelled());x.success(q.getIntValue("value"));});}); c.start(); assertTrue(c.awaitReady(2,TimeUnit.SECONDS)); assertTrue(c.isConnected()); String bind=received.poll(2,TimeUnit.SECONDS); assertTrue(bind.contains("echo")); assertTrue(bind.indexOf("echo")<bind.indexOf("zeta")); String reply=received.poll(2,TimeUnit.SECONDS); assertNotNull(reply); c.destroy(); server.shutdown();
 }
 @Test public void openingWithoutConfirmationNeverBecomesReady() throws Exception { MockWebServer server=new MockWebServer(); server.enqueue(new MockResponse().withWebSocketUpgrade(new WebSocketListener(){})); server.start(); RpcClient c=new RpcClient("g","c","ws",server.getHostName(),server.getPort(),null); c.start(); assertFalse(c.awaitReady(100,TimeUnit.MILLISECONDS)); assertFalse(c.isConnected()); c.destroy(); server.shutdown(); }
}
