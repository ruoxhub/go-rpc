package cn.iinti.sekiro3.business.api.core.eventbus.support;

import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import lombok.Data;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Collection;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class EventSenderHelper {
    private static final ConcurrentHashMap<Class<?>, SenderProxyClassHolder> sCache = new ConcurrentHashMap<>();

    /**
     * parameter types of a proxy class constructor
     */
    private static final Class<?>[] constructorParams =
            {InvocationHandler.class};

    public static void registerSender(EventBus eventBus, Class<?> interfaceClass) {
        SenderProxyClassHolder holder = sCache.get(interfaceClass);
        if (holder != null) {
            doRegisterWithCachedClass(eventBus, holder);
        } else {
            doRegisterRaw(eventBus, interfaceClass);
        }
    }

    private static void doRegisterRaw(EventBus eventBus, Class<?> interfaceClass) {
        if (!interfaceClass.isInterface()) {
            throw new IllegalStateException("can not make " + interfaceClass.getName() + " to be a event");
        }
        Method[] declaredMethods = interfaceClass.getDeclaredMethods();
        Set<Method> eventMethods = new HashSet<>();
        Set<String> duplicateMethodNames = new HashSet<>();
        for (Method method : declaredMethods) {
            if (!method.isAnnotationPresent(AutoEvent.class)) {
                continue;
            }
            if (method.getReturnType() != Void.TYPE) {
                throw new IllegalStateException("自动事件方法返回值必须为void" + method.getName());
            }
            if (duplicateMethodNames.contains(method.getName())) {
                throw new IllegalStateException("自动事件不允许多个重名方法存在" + method.getName());
            }
            duplicateMethodNames.add(method.getName());
            eventMethods.add(method);
        }
        if (eventMethods.isEmpty()) {
            // 没有任何接口监听，不处理
            return;
        }

        EventSender eventSender = new EventSender(eventBus, eventMethods);
        Object senderImpl = Proxy.newProxyInstance(EventSenderHelper.class.getClassLoader(), new Class[]{interfaceClass},
                eventSender);
        eventBus.registerSender(interfaceClass, senderImpl);

        // now make cache
        SenderProxyClassHolder holder = new SenderProxyClassHolder();
        holder.eventSenderProxyClass = senderImpl.getClass();
        holder.methods = new HashSet<>(eventMethods);
        holder.interfaceClass = interfaceClass;

        sCache.put(interfaceClass, holder);
    }

    private static void doRegisterWithCachedClass(EventBus eventBus, SenderProxyClassHolder senderProxyClassHolder) {
        EventSender eventSender = new EventSender(eventBus, new HashSet<>(senderProxyClassHolder.methods));
        Object senderImpl;
        try {
            senderImpl = senderProxyClassHolder.eventSenderProxyClass.getConstructor(constructorParams)
                    .newInstance(eventSender);
        } catch (Throwable e) {
            throw new RuntimeException(e);
        }
        eventBus.registerSender(senderProxyClassHolder.interfaceClass, senderImpl);
    }

    @Data
    private static class SenderProxyClassHolder {
        private Class<?> interfaceClass;
        private Class<?> eventSenderProxyClass;
        private Collection<Method> methods;
    }
}
