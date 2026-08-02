package cn.iinti.sekiro3.business.api.core.databind;

import cn.iinti.sekiro3.business.api.interfaze.RequestHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class AnnotationInjector {

    private static final Map<Class<? extends RequestHandler>, InjectClassHolder> rules = new ConcurrentHashMap<>();

    public static void inject(RequestHandler requestHandler, SekiroRequest sekiroRequest) {
        InjectClassHolder injectClassHolder = rules.get(requestHandler.getClass());
        if (injectClassHolder == null) {
            injectClassHolder = new InjectClassHolder(requestHandler.getClass());
            rules.put(requestHandler.getClass(), injectClassHolder);
        }
        injectClassHolder.doInject(requestHandler, sekiroRequest);

    }


}
