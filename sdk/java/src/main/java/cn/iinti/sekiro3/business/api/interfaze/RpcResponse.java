package cn.iinti.sekiro3.business.api.interfaze;
import cn.iinti.sekiro3.business.api.RpcClient;
import com.alibaba.fastjson.JSONObject;
import java.util.concurrent.atomic.AtomicBoolean;
public final class RpcResponse {
 private final RpcClient client; private final String sequence; private final String group,clientId,traceId; private final AtomicBoolean completed=new AtomicBoolean();
 public RpcResponse(RpcClient c,String s){this(c,s,null,null,null);} public RpcResponse(RpcClient c,String s,String g,String id,String t){client=c;sequence=s;group=g;clientId=id;traceId=t;}
 public void success(Object data){if(completed.compareAndSet(false,true))client.sendSuccess(sequence,data,group,clientId,traceId);} public void failed(String m){failed(-1,m);} public void failed(int status,String m){if(completed.compareAndSet(false,true))client.sendFailed(sequence,status,m,group,clientId,traceId);} public void sendStreamChunk(String c){if(!completed.get())client.sendStream(sequence,c,false,null);} public void endStream(){endStream(null);} public void endStream(String e){if(completed.compareAndSet(false,true))client.sendStream(sequence,null,true,e);}
}
