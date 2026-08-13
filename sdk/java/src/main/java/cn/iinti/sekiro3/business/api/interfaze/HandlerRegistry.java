package cn.iinti.sekiro3.business.api.interfaze;
import java.util.*; import java.util.concurrent.ConcurrentHashMap;
public class HandlerRegistry {
 private final Map<String,RequestHandler> handlers=new ConcurrentHashMap<>();
 public HandlerRegistry registerRpcHandler(RequestHandler h){String a; if(h instanceof ActionHandler)a=((ActionHandler)h).action(); else {Action x=h.getClass().getAnnotation(Action.class); if(x==null)throw new IllegalArgumentException("can not resolve handler action"); a=x.value();} return registerRpcHandler(a,h);}
 public HandlerRegistry registerRpcHandler(String a,RequestHandler h){if(a==null||a.trim().isEmpty()||h==null)throw new IllegalArgumentException("invalid handler"); if(handlers.putIfAbsent(a,h)!=null)throw new IllegalStateException("duplicate handler register: "+a); return this;}
 public RequestHandler get(String a){return handlers.get(a);} public List<String> actionList(){ArrayList<String> a=new ArrayList<>(handlers.keySet()); Collections.sort(a); return a;} public void clear(){handlers.clear();}
}
