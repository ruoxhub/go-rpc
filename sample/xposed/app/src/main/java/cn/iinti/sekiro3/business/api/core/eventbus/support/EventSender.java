package cn.iinti.sekiro3.business.api.core.eventbus.support;

import cn.iinti.sekiro3.business.api.core.eventbus.Event;
import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import lombok.NonNull;
import lombok.RequiredArgsConstructor;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

@RequiredArgsConstructor
public class EventSender implements InvocationHandler {

    @NonNull
    private final EventBus eventBus;

    @NonNull
    private final Collection<Method> methods;

    @Override
    public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
        if (!methods.contains(method)) {
            return method.invoke(this, args);
        }
        AutoEvent annotation = method.getAnnotation(AutoEvent.class);
        if (annotation == null) {
            throw new IllegalStateException("can not make " + method.getName() + "  to be a event");
        }
        String topic = annotation.topic();
        if (TextUtil.isEmpty(topic)) {
            topic = method.getDeclaringClass().getName() + "#" + method.getName();
        }

        boolean sync = annotation.sync();

        Event event = new Event(topic);

        Map<String, Object> data = new HashMap<>();
        data.put("AutoEvent", true);
        data.put("proxy", proxy);
        data.put("method", method);
        data.put("args", args);
        event.setData(data);
        event.setSync(sync);
        eventBus.offerEvent(event);
        return null;
    }
}
