package cn.iinti.sekiro3.business.api.core.eventbus.support;

import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import cn.iinti.sekiro3.business.api.core.eventbus.EventHandler;
import cn.iinti.sekiro3.business.api.util.TextUtil;

import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Collection;

public class EventHandlerHelper {
    public static void registerObserver(EventBus eventBus, Object observer) {
        Collection<Class<?>> allSupperClass = eventBus.fetchEventInterface(observer);
        if (allSupperClass.isEmpty()) {
            // 需要先声明事件，才能注册监听函数
            return;
        }
        for (Class<?> interfaceClazz : allSupperClass) {
            for (Method interfaceMethod : interfaceClazz.getDeclaredMethods()) {
                if (interfaceMethod.isAnnotationPresent(AutoEvent.class)) {
                    handleOnEventRegister(eventBus, observer, interfaceMethod);
                }
            }
        }
    }

    private static void handleOnEventRegister(EventBus eventBus, Object observer, Method interfaceMethod) {
        Method targetMethod;
        try {
            targetMethod = observer.getClass().getDeclaredMethod(
                    interfaceMethod.getName(), interfaceMethod.getParameterTypes()
            );
        } catch (NoSuchMethodException e) {
            throw new IllegalStateException(e);
        }
        AutoEvent annotation = interfaceMethod.getAnnotation(AutoEvent.class);
        String eventTopic = annotation.topic();

        if (TextUtil.isEmpty(eventTopic)) {
            eventTopic = interfaceMethod.getDeclaringClass().getName() + "#" + interfaceMethod.getName();
        }

        EventHandlerImpl eventHandlerImpl = new EventHandlerImpl(observer, targetMethod);

        EventHandler eventHandler = (EventHandler) Proxy.newProxyInstance(EventHandlerHelper.class.getClassLoader(),
                new Class[]{EventHandler.class}, eventHandlerImpl);
        eventBus.registerHandler(eventTopic, eventHandler);
    }
}
