package cn.iinti.sekiro3.business.api.core.eventbus.event.client;

import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.core.eventbus.support.AutoEvent;

public interface SekiroClientDestroyEvent extends SekiroClientEvent{
    @AutoEvent
    void onClientDestroy(SekiroClient sekiroClient);
}
