package cn.iinti.sekiro3.business.api.core.eventbus.support;

import cn.iinti.sekiro3.business.api.core.eventbus.Event;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.util.Map;

public class EventHandlerImpl implements InvocationHandler {
    private final Object target;
    private final Method targetMethod;

    public EventHandlerImpl(Object target, Method targetMethod) {
        this.target = target;
        this.targetMethod = targetMethod;
        targetMethod.setAccessible(true);
    }

    @Override
    @SuppressWarnings("unchecked")
    public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
        if ("handEvent".equals(method.getName())) {// 从object继承过来的方法,不代理
            Event event = (Event) args[0];
            Map<String, Object> data = (Map) event.getData();
            Object[] args1 = (Object[]) data.get("args");
            return targetMethod.invoke(target, args1);
        }

        if ("hashCode".equals(method.getName())) {
            return target.hashCode() + targetMethod.hashCode();
        }

        if ("equals".equals(method.getName()) && args.length == 1) {
            Object other = args[0];
            if (other == null) {
                return false;
            }
            int theHashCode = target.hashCode() + targetMethod.hashCode();
            return theHashCode == other.hashCode();
        }

        return method.invoke(this, args);
    }
}
