package cn.iinti.sekiro3.business.api.invoker;

import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import com.alibaba.fastjson.JSON;
import lombok.Getter;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class InvokerRequest {
    @Getter
    private final Map<String, String> headers = new HashMap<>();

    private final Map<String, Object> fields = new HashMap<>();

    private InvokerRequest(Builder builder) {
        headers.putAll(builder.headers);

        fields.put(Constants.REVERSED_WORDS.GROUP, builder.group);
        fields.put(Constants.REVERSED_WORDS.ACTION, builder.action);
        fields.put(Constants.REVERSED_WORDS.INVOKE_TIME_OUT, builder.timeout);
        fields.put(Constants.REVERSED_WORDS.BIND_CLIENT, builder.bindClient);

        fields.putAll(builder.fields);
    }

    public InvokerRequest header(String key, String value) {
        this.headers.put(key, value);
        return this;
    }

    public InvokerRequest headers(Map<String, String> headers) {
        if (headers == null) {
            throw new NullPointerException("headers is null");
        }
        this.headers.putAll(headers);
        return this;
    }

    public String group() {
        return (String) fields.get(Constants.REVERSED_WORDS.GROUP);
    }

    public String action() {
        return (String) fields.get(Constants.REVERSED_WORDS.ACTION);
    }

    public int timeout() {
        return (int) fields.get(Constants.REVERSED_WORDS.INVOKE_TIME_OUT);
    }

    public Map<String, String> headers() {
        return headers;
    }

    public byte[] data(String apiToken) {
        if (TextUtil.isNotBlank(apiToken)) {
            fields.put(Constants.REVERSED_WORDS.API_TOKEN, apiToken);
        }
        return JSON.toJSONString(fields).getBytes(StandardCharsets.UTF_8);
    }

    public static class Builder {
        private String group;
        private String action;
        private final Map<String, String> headers = new HashMap<>();
        private final Map<String, Object> fields = new HashMap<>();
        private int timeout;
        private String bindClient;

        public Builder group(String group) {
            if (TextUtil.isBlank(group)) throw new IllegalArgumentException("group is empty");
            this.group = group;
            return this;
        }

        public Builder action(String action) {
            if (TextUtil.isBlank(action)) throw new IllegalArgumentException("action is empty");
            this.action = action;
            return this;
        }


        public Builder header(String key, String value) {
            if (TextUtil.isBlank(key) || TextUtil.isBlank(value))
                throw new IllegalArgumentException("key or vale is null");
            this.headers.put(key, value);
            return this;
        }

        public Builder headers(Map<String, String> headers) {
            this.headers.putAll(headers);
            return this;
        }

        public Builder field(String key, Object value) {
            if (TextUtil.isBlank(key))
                throw new IllegalArgumentException("key or vale is empty");
            this.fields.put(key, value);
            return this;
        }

        public Builder fields(Map<String, String> params) {
            if (params == null) {
                throw new NullPointerException("headerd is null");
            }
            this.fields.putAll(params);
            return this;
        }

        public Builder timeout(int timeout) {
            if (timeout < 500) {
                timeout = Constants.DEFAULT_INVOKE_TIMEOUT;
            }
            this.timeout = timeout;
            return this;
        }

        public Builder bindClient(String bindClient) {
            if (TextUtil.isBlank(bindClient)) throw new IllegalArgumentException("bindClient is empty");
            this.bindClient = bindClient;
            return this;
        }

        public InvokerRequest build() {
            if (TextUtil.isBlank(group) || TextUtil.isBlank(action)) {
                throw new IllegalStateException("group/action/apiToken can't be empty");
            }

            if (timeout < 500) {
                timeout = Constants.DEFAULT_INVOKE_TIMEOUT;
            }
            return new InvokerRequest(this);
        }
    }
}
