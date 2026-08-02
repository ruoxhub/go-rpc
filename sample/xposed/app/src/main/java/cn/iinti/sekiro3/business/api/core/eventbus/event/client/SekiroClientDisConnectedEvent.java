package cn.iinti.sekiro3.business.api.core.eventbus.event.client;

import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.core.eventbus.support.AutoEvent;


public interface SekiroClientDisConnectedEvent extends SekiroClientEvent {
    @AutoEvent
    void onClientDisConnected(SekiroClient sekiroClient);
}
