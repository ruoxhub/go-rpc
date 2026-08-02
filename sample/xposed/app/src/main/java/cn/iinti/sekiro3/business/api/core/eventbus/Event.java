package cn.iinti.sekiro3.business.api.core.eventbus;


import lombok.Getter;
import lombok.Setter;

import java.util.concurrent.Delayed;
import java.util.concurrent.TimeUnit;

/**
 * Created by virjar on 17/4/30.
 *
 * @author virjar
 * @since 0.0.1
 */
public class Event implements Delayed {
    @Getter
    private final String topic;
    @Getter
    @Setter
    private int what;
    @Getter
    @Setter
    private Object data;

    /**
     * 如果事件被消费,那么不在往其他handler传递
     */
    @Getter
    private boolean handled = false;
    /**
     * 如果同步选项打开,那么事件在触发线程同步执行,而不进入事件循环
     */
    @Getter
    @Setter
    private boolean sync = false;

    /**
     * The time the task is enabled to execute in nanoTime units
     */
    @Setter
    private long time;

    @Getter
    @Setter
    private boolean cleanExpire = false;

    @Getter
    @Setter
    private EventBus targetEventBus;

    public Event(String topic) {
        this.topic = topic;
    }

    public void consumed() {
        handled = true;
    }

    @Override
    public long getDelay(TimeUnit unit) {
        if (time == 0) {
            return 0;
        }
        long delay = time - System.currentTimeMillis();
        if (delay <= 0) {
            return 0;
        }
        return unit.convert(delay, TimeUnit.MILLISECONDS);
    }

    @Override
    public int compareTo(Delayed o) {
        if (o instanceof Event) {
            Event other = (Event) o;
            if (this == other) {
                return 0;
            }
            return Long.compare(this.time, other.time);
        }

        long d = (getDelay(TimeUnit.NANOSECONDS) - o.getDelay(TimeUnit.NANOSECONDS));
        return (d == 0) ? 0 : ((d < 0) ? -1 : 1);
    }

    public void dispatchToEventConsumer() {
        targetEventBus.dispatchToEventConsumer(this);
    }
}

