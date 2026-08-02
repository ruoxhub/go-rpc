package cn.iinti.sekiro3.business.api.core.eventbus.support;


import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Created by virjar on 17/4/30.
 *
 * @author virjar
 * @since 0.0.1
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AutoEvent {
    /**
     * 事件主题
     *
     * @return 主题
     */
    String topic() default "";

    /**
     * 是否为同步事件
     *
     * @return 是否为同步事件
     */
    boolean sync() default true;

    /**
     * 是否为消重事件
     *
     * @return 是否为消重事件
     */
    boolean clearExpire() default false;
}
