package cn.iinti.sekiro3.business.api.interfaze;

import com.alibaba.fastjson.JSONObject;

public final class RpcRequest {
    private final JSONObject raw;
    private final JSONObject params;
    private final InvocationContext context;
    private final RpcCancellationToken token;

    public RpcRequest(JSONObject raw) {
        this(raw, null, null);
    }

    public RpcRequest(JSONObject raw, InvocationContext context, RpcCancellationToken token) {
        this.raw = raw;
        JSONObject rawParams = raw.getJSONObject("params");
        this.params = rawParams == null ? new JSONObject() : rawParams;
        this.context = context;
        this.token = token;
    }

    public String getAction() {
        return raw.getString("action");
    }

    public String getSeq() {
        String sequence = raw.getString("__sekiro_seq__");
        return sequence == null ? raw.getString("sequence") : sequence;
    }

    public String getString(String key) {
        Object value = value(key);
        return value == null ? null : String.valueOf(value);
    }

    public int getIntValue(String key) {
        Object value = value(key);
        return value instanceof Number ? ((Number) value).intValue()
                : value == null ? 0 : Integer.parseInt(String.valueOf(value));
    }

    public long getLongValue(String key) {
        Object value = value(key);
        return value instanceof Number ? ((Number) value).longValue()
                : value == null ? 0L : Long.parseLong(String.valueOf(value));
    }

    public boolean getBooleanValue(String key) {
        Object value = value(key);
        return value instanceof Boolean ? (Boolean) value
                : Boolean.parseBoolean(String.valueOf(value));
    }

    public Object get(String key) {
        return value(key);
    }

    public boolean containsKey(String key) {
        return params.containsKey(key) || raw.containsKey(key);
    }

    public JSONObject getParams() {
        return params;
    }

    public JSONObject raw() {
        return raw;
    }

    public InvocationContext getInvocationContext() {
        return context;
    }

    public RpcCancellationToken getCancellationToken() {
        return token;
    }

    private Object value(String key) {
        return params.containsKey(key) ? params.get(key) : raw.get(key);
    }
}
