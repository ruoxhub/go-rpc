package cn.iinti.sekiro3.business.api.interfaze;

import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE})
@Documented
public @interface Action {
    String value();
}
