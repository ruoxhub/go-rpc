package cn.iinti.sekiro3.business.api.interfaze;
import com.alibaba.fastjson.JSONObject;
public final class InvocationContext {
    private final String sequence, traceId, group, action, clientId, idempotencyKey;
    private final long deadlineUnixMs; private final boolean idempotent; private final int attempt;
    public InvocationContext(String sequence, String traceId, String group, String action, String clientId, long deadlineUnixMs, boolean idempotent, String idempotencyKey, int attempt) {
        if (sequence == null || traceId == null || group == null || action == null || clientId == null || idempotencyKey == null || deadlineUnixMs < 0 || attempt < 0) throw new IllegalArgumentException("invalid invocation context");
        this.sequence=sequence; this.traceId=traceId; this.group=group; this.action=action; this.clientId=clientId; this.deadlineUnixMs=deadlineUnixMs; this.idempotent=idempotent; this.idempotencyKey=idempotencyKey; this.attempt=attempt;
    }
    public static InvocationContext fromMessage(JSONObject message) {
        JSONObject c = message == null ? null : message.getJSONObject("__rpc_context__");
        if (c == null || c.size() != 9) throw new IllegalArgumentException("invalid invocation context");
        Object deadline=c.get("deadline_unix_ms"), attempt=c.get("attempt"), idem=c.get("idempotent");
        for (String key : new String[]{"sequence","trace_id","group","action","client_id","idempotency_key"}) if (!(c.get(key) instanceof String)) throw new IllegalArgumentException("invalid invocation context types");
        if (!(deadline instanceof Number) || deadline instanceof Boolean || !(attempt instanceof Number) || attempt instanceof Boolean || !(idem instanceof Boolean)) throw new IllegalArgumentException("invalid invocation context types");
        return new InvocationContext(c.getString("sequence"),c.getString("trace_id"),c.getString("group"),c.getString("action"),c.getString("client_id"),((Number)deadline).longValue(),(Boolean)idem,c.getString("idempotency_key"),((Number)attempt).intValue());
    }
    public String getSequence(){return sequence;} public String getTraceId(){return traceId;} public String getGroup(){return group;} public String getAction(){return action;} public String getClientId(){return clientId;} public long getDeadlineUnixMs(){return deadlineUnixMs;} public boolean isIdempotent(){return idempotent;} public String getIdempotencyKey(){return idempotencyKey;} public int getAttempt(){return attempt;}
}
