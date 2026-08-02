package cn.iinti.sekiro3.business.api.interfaze;

import com.alibaba.fastjson.JSONObject;

public class RpcRequest {
    private final JSONObject raw;
    private final JSONObject params;

    public RpcRequest(JSONObject raw) {
        this.raw = raw;
        JSONObject nested = raw.getJSONObject("params");
        this.params = nested == null ? new JSONObject() : nested;
    }

    public String getAction() {
        return raw.getString("action");
    }

    public String getSeq() {
        String seq = raw.getString("__sekiro_seq__");
        return seq == null ? raw.getString("sequence") : seq;
    }

    public String getString(String key) {
        Object value = value(key);
        return value == null ? null : String.valueOf(value);
    }

    public int getIntValue(String key) {
        Object value = value(key);
        return value == null ? 0 : JSONObject.toJavaObject(value, Integer.class);
    }

    public long getLongValue(String key) {
        Object value = value(key);
        return value == null ? 0L : JSONObject.toJavaObject(value, Long.class);
    }

    public boolean getBooleanValue(String key) {
        Object value = value(key);
        return value != null && JSONObject.toJavaObject(value, Boolean.class);
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

    private Object value(String key) {
        return params.containsKey(key) ? params.get(key) : raw.get(key);
    }
}
