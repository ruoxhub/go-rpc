package cn.iinti.sekiro3.business.api.interfaze;

public interface SekiroRequestInitializer {
    void onSekiroRequest(SekiroRequest sekiroRequest, HandlerRegistry handlerRegistry);
}
