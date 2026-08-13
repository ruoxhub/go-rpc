package cn.iinti.sekiro3.business.api.interfaze;

import com.alibaba.fastjson.JSONObject;

import java.math.BigInteger;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class InvocationContext {
    private static final Set<String> REQUIRED_KEYS = new HashSet<>(Arrays.asList(
            "sequence", "trace_id", "group", "action", "client_id",
            "deadline_unix_ms", "idempotent", "idempotency_key", "attempt"));

    private final String sequence;
    private final String traceId;
    private final String group;
    private final String action;
    private final String clientId;
    private final String idempotencyKey;
    private final long deadlineUnixMs;
    private final boolean idempotent;
    private final int attempt;

    public InvocationContext(String sequence, String traceId, String group, String action,
                             String clientId, long deadlineUnixMs, boolean idempotent,
                             String idempotencyKey, int attempt) {
        if (sequence == null || traceId == null || group == null || action == null
                || clientId == null || idempotencyKey == null || deadlineUnixMs < 0
                || attempt < 0) {
            throw new IllegalArgumentException("invalid invocation context");
        }
        this.sequence = sequence;
        this.traceId = traceId;
        this.group = group;
        this.action = action;
        this.clientId = clientId;
        this.deadlineUnixMs = deadlineUnixMs;
        this.idempotent = idempotent;
        this.idempotencyKey = idempotencyKey;
        this.attempt = attempt;
    }

    public static InvocationContext fromMessage(JSONObject message) {
        JSONObject context = message == null ? null : message.getJSONObject("__rpc_context__");
        if (context == null || context.size() != REQUIRED_KEYS.size()
                || !context.keySet().equals(REQUIRED_KEYS)) {
            throw new IllegalArgumentException("invalid invocation context");
        }
        for (String key : new String[]{"sequence", "trace_id", "group", "action",
                "client_id", "idempotency_key"}) {
            if (!(context.get(key) instanceof String)) {
                throw new IllegalArgumentException("invalid invocation context types");
            }
        }
        Object idempotent = context.get("idempotent");
        if (!(idempotent instanceof Boolean)) {
            throw new IllegalArgumentException("invalid invocation context types");
        }
        long deadline = exactLong(context.get("deadline_unix_ms"));
        long attempt = exactLong(context.get("attempt"));
        if (deadline < 0 || attempt < 0 || attempt > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("invalid invocation context range");
        }
        return new InvocationContext(context.getString("sequence"), context.getString("trace_id"),
                context.getString("group"), context.getString("action"),
                context.getString("client_id"), deadline, (Boolean) idempotent,
                context.getString("idempotency_key"), (int) attempt);
    }

    private static long exactLong(Object value) {
        if (value instanceof Integer) {
            return ((Integer) value).longValue();
        }
        if (value instanceof Long) {
            return (Long) value;
        }
        if (value instanceof BigInteger) {
            BigInteger integer = (BigInteger) value;
            if (integer.compareTo(BigInteger.valueOf(Long.MIN_VALUE)) < 0
                    || integer.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0) {
                throw new IllegalArgumentException("invalid invocation context range");
            }
            return integer.longValue();
        }
        throw new IllegalArgumentException("invalid invocation context number");
    }

    public String getSequence() {
        return sequence;
    }

    public String getTraceId() {
        return traceId;
    }

    public String getGroup() {
        return group;
    }

    public String getAction() {
        return action;
    }

    public String getClientId() {
        return clientId;
    }

    public long getDeadlineUnixMs() {
        return deadlineUnixMs;
    }

    public boolean isIdempotent() {
        return idempotent;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public int getAttempt() {
        return attempt;
    }
}
