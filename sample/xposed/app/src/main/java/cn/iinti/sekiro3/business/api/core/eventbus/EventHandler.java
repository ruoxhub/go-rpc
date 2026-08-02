package cn.iinti.sekiro3.business.api.core.eventbus;

/**
 * Created by virjar.
 *
 * @author virjar
 * @since 0.0.1
 */
public interface EventHandler {
    void handEvent(Event event);
}
