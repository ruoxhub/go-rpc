package cn.iinti.sekiro3.business.api.interfaze;
import java.lang.annotation.*;
@Retention(RetentionPolicy.RUNTIME) @Target(ElementType.FIELD) @Documented
public @interface AutoBind { String value() default ""; boolean require() default false; String defaultValue() default ""; }
