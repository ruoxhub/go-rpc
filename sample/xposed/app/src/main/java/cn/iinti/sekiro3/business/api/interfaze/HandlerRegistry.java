package cn.iinti.sekiro3.business.api.interfaze;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class HandlerRegistry {
    private final Map<String, RequestHandler> handlers = new ConcurrentHashMap<>();

    public HandlerRegistry registerRpcHandler(RequestHandler handler) {
        String action;
        if (handler instanceof ActionHandler) {
            action = ((ActionHandler) handler).action();
        } else {
            Action annotation = handler.getClass().getAnnotation(Action.class);
            if (annotation == null) {
                throw new IllegalArgumentException("can not resolve handler action");
            }
            action = annotation.value();
        }
        return registerRpcHandler(action, handler);
    }

    public HandlerRegistry registerRpcHandler(String action, RequestHandler handler) {
        if (action == null || action.trim().isEmpty()) {
            throw new IllegalArgumentException("action must not be empty");
        }
        if (handler == null) {
            throw new IllegalArgumentException("handler must not be null");
        }
        if (handlers.putIfAbsent(action, handler) != null) {
            throw new IllegalStateException("duplicate handler register: " + action);
        }
        return this;
    }

    public RequestHandler get(String action) {
        return handlers.get(action);
    }

    public java.util.List<String> actionList() {
        ArrayList<String> actions = new ArrayList<>(handlers.keySet());
        Collections.sort(actions);
        return actions;
    }

    public void clear() {
        handlers.clear();
    }
}
