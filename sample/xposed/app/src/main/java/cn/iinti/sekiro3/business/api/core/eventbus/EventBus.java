package cn.iinti.sekiro3.business.api.core.eventbus;

import cn.iinti.sekiro3.business.api.core.eventbus.support.EventHandlerHelper;
import cn.iinti.sekiro3.business.api.core.eventbus.support.EventSenderHelper;
import cn.iinti.sekiro3.business.api.log.SekiroGlobalLogger;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.DelayQueue;

/**
 * 只狼事件总线，各种模块回调函数太多，所以统一抽象派发事件，降低模块生命周期函数挂载复杂度
 */
public class EventBus {
    private final ConcurrentMap<String, Set<EventHandler>> allHandlers = new ConcurrentHashMap<>();
    private final Map<Class<?>, Object> autoEventSender = new ConcurrentHashMap<>();
    private static final DelayQueue<Event> eventQueue = new DelayQueue<>();

    public static class EventBusLooperThread extends Thread {
        public EventBusLooperThread() {
            super("sekiro-event-bus");
            setDaemon(true);
            start();
        }

        @Override
        public void run() {
            eventLoop();
        }
    }

    private static final EventBusLooperThread eventBusLooperThread = new EventBusLooperThread();

    public void offerEvent(final Event event) {
        if (!allHandlers.containsKey(event.getTopic())
                || allHandlers.get(event.getTopic()).isEmpty()
        ) {
            //TODO log
            return;
        }

        if (event.isSync()) {
            postImmediately(event);
            return;
        }

        if (event.isCleanExpire()) {
            Iterator<Event> iterator = eventQueue.iterator();
            while (iterator.hasNext()) {
                Event next = iterator.next();
                if (next.getTopic().equals(event.getTopic())) {
                    iterator.remove();
                }
            }
//            eventQueue.removeIf(new Predicate<Event>() {
//                @Override
//                public boolean test(Event next) {
//                    return next.getTopic().equals(event.getTopic());
//                }
//            });
        }
        event.setTargetEventBus(this);
        eventQueue.offer(event);
    }

    /**
     * 同步事件直接投递,不能吞掉异常
     *
     * @param event 将要被投递的事件
     */
    private void postImmediately(Event event) {
        for (EventHandler eventHandler : allHandlers.get(event.getTopic())) {
            eventHandler.handEvent(event);
            if (event.isHandled()) {
                break;
            }
        }
    }

    private static void eventLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                eventQueue.take().dispatchToEventConsumer();
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                SekiroGlobalLogger.error("event bus error", e);
            }
        }
    }

    public void dispatchToEventConsumer(Event event) {
        String topic = event.getTopic();
        for (EventHandler eventHandler : allHandlers.get(topic)) {
            try {
                eventHandler.handEvent(event);
                if (event.isHandled()) {
                    break;
                }
            } catch (Exception e) {
                SekiroGlobalLogger.error("event bus error", e);
            }
        }
    }

    public synchronized void registerHandler(String topic, EventHandler eventHandler) {
        // Set<EventHandler> eventHandlers = allHandlers.computeIfAbsent(topic, k -> new HashSet<>());
        Set<EventHandler> eventHandlers = allHandlers.get(topic);
        if (eventHandlers == null) {
            eventHandlers = new HashSet<>();
            allHandlers.put(topic, eventHandlers);
        }

        eventHandlers.add(eventHandler);
    }

    public Collection<Class<?>> fetchEventInterface(Object observer) {
        Set<Class<?>> ret = new HashSet<>();
        Class<?> observerClass = observer.getClass();
        for (Class<?> clazz : autoEventSender.keySet()) {
            if (clazz.isAssignableFrom(observerClass)) {
                ret.add(clazz);
            }
        }
        return ret;
    }

    public void registerEventObserver(Object observer) {
        EventHandlerHelper.registerObserver(this, observer);
    }

    public void registerSender(Class<?> interfaze, Object proxySender) {
        Object v = autoEventSender.get(interfaze);
        if (v == null) {
            autoEventSender.put(interfaze, proxySender);
        }

//        autoEventSender.putIfAbsent(interfaze, proxySender);
    }

    @SuppressWarnings("unchecked")
    public <T> T findEventSender(Class<T> interfaze) {
        if (!interfaze.isInterface()) {
            throw new IllegalStateException("sender must be interface");
        }
        Object o = autoEventSender.get(interfaze);
        if (o != null) {
            return (T) o;
        }
        EventSenderHelper.registerSender(this, interfaze);
        return findEventSender(interfaze);
    }


}
