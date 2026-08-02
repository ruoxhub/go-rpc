package cn.iinti.sekiro3.business.api.core.eventbus.event.cluster;

import cn.iinti.sekiro3.business.api.ClusterSekiroClient;
import cn.iinti.sekiro3.business.api.core.eventbus.support.AutoEvent;

public interface OnAllClientOfflineEvent extends ClusterClientEvent {
    @AutoEvent
    void onAllClientOffline(ClusterSekiroClient clusterSekiroClient);
}
