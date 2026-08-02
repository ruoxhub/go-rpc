package cn.iinti.sekiro3.business.api.core.databind;

import cn.iinti.sekiro3.business.api.interfaze.AutoBind;
import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import com.alibaba.fastjson.parser.ParserConfig;
import com.alibaba.fastjson.util.TypeUtils;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

class InjectClassHolder {

    private final Class<? extends RequestHandler> handlerClass;
    private final List<FileBindHandler> fileBindHandlerList = new ArrayList<>();

    private static final ConcurrentMap<Class<?>, Field[]> fieldCache = new ConcurrentHashMap<>();

    InjectClassHolder(Class<? extends RequestHandler> handlerClass) {
        this.handlerClass = handlerClass;
        parseFileBindHandler();
    }

    void doInject(RequestHandler requestHandler, SekiroRequest sekiroRequest) {
        for (FileBindHandler fileBindHandler : fileBindHandlerList) {
            Object targetValue = fileBindHandler.transfer(sekiroRequest);
            if (targetValue != null) {
                try {
                    fileBindHandler.getTargetFiled().set(requestHandler, targetValue);
                } catch (IllegalAccessException e) {
                    throw new IllegalStateException(e);
                }
            }
        }
    }

    private void parseFileBindHandler() {
        for (Field field : classFileds(handlerClass)) {
            if (Modifier.isStatic(field.getModifiers())
                    || field.isSynthetic()) {
                continue;
            }
            AutoBind autoBind = field.getAnnotation(AutoBind.class);
            if (autoBind == null) {
                continue;
            }
            Object defaultValue = null;
            if (TextUtil.isNotBlank(autoBind.defaultValue())) {
                defaultValue = TypeUtils.cast(autoBind.defaultValue(), field.getGenericType(), ParserConfig.getGlobalInstance());
            }
            fileBindHandlerList.add(new FileBindHandler(defaultValue, field, autoBind));
        }
    }

    private static Field[] classFileds(Class<?> clazz) {
        if (clazz == Object.class) {
            return new Field[0];
        }
        Field[] fields = fieldCache.get(clazz);
        if (fields != null) {
            return fields;
        }
        synchronized (InjectClassHolder.class) {
            fields = fieldCache.get(clazz);
            if (fields != null) {
                return fields;
            }
            ArrayList<Field> ret = new ArrayList<>();
            ret.addAll(Arrays.asList(clazz.getDeclaredFields()));
            ret.addAll(Arrays.asList(classFileds(clazz.getSuperclass())));
            Iterator<Field> iterator = ret.iterator();
            while (iterator.hasNext()) {
                Field next = iterator.next();
                if (Modifier.isStatic(next.getModifiers())) {
                    iterator.remove();
                    continue;
                }
                if (next.isSynthetic()) {
                    iterator.remove();
                    continue;
                }
                if (!next.isAccessible()) {
                    next.setAccessible(true);
                }
            }
            fields = ret.toArray(new Field[0]);

            fieldCache.put(clazz, fields);
        }
        return fields;
    }
}
