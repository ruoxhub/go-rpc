package cn.iinti.sekiro3.business.api.core.eventbus.event.cluster;

import cn.iinti.sekiro3.business.api.ClusterSekiroClient;
import cn.iinti.sekiro3.business.api.core.eventbus.support.AutoEvent;

public interface ClusterClientDestroyEvent extends ClusterClientEvent{
    @AutoEvent
    void onDestroy(ClusterSekiroClient clusterSekiroClient);
}
