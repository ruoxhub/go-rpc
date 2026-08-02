package cn.iinti.sekiro3.business.api;

import cn.iinti.sekiro3.business.api.core.eventbus.EventBus;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientDestroyEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.SekiroClientEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.cluster.ClusterClientDestroyEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.cluster.ClusterClientEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.cluster.OnAllClientOfflineEvent;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequestInitializer;
import cn.iinti.sekiro3.business.api.util.Constants;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 集群客户端，内部为每个服务器节点维护一个SekiroClient，
 * 用于接受服务器的RPC调用，ClusterSekiroClient和SekiroClient的API基本保持一致
 */
public class ClusterSekiroClient implements SekiroClientDestroyEvent {
    private SekiroRequestInitializer sekiroRequestInitializer;

    private final Map<String, SekiroClient> runningSekiroClient = new ConcurrentHashMap<>();
    private final EventBus eventBus;
    private final List<SekiroClientEvent> sekiroClientEvents = new ArrayList<>();


    public ClusterSekiroClient(String sekiroGroup, String[] serverList) {
        this(sekiroGroup, UUID.randomUUID().toString(), serverList);
    }

    public ClusterSekiroClient(String sekiroGroup, String clientId, String[] serverList) {
        if (serverList == null) {
            throw new IllegalStateException("no server list configured!!");
        }
        // remove duplicate config
        TreeSet<String> strings = new TreeSet<>(Arrays.asList(serverList));
        for (String server : strings) {
            SekiroClient sekiroClient = configInstance(sekiroGroup, clientId, server);
            runningSekiroClient.put(sekiroClient.getClientKey(), sekiroClient);
        }

        eventBus = new EventBus();
        eventBus.findEventSender(ClusterClientDestroyEvent.class);
        eventBus.findEventSender(OnAllClientOfflineEvent.class);
    }


    private SekiroClient configInstance(String sekiroGroup, String clientId, String config) {
        String server = config.trim();
        String ip = server;
        int port = Constants.DEFAULT_SERVER_CONF.DEFAULT_STAND_ALONG_PORT;
        int index = server.indexOf(':');
        if (index > 0) {
            ip = server.substring(0, index);
            port = Integer.parseInt(server.substring(index + 1).trim());
        }
        SekiroClient sekiroClient = new SekiroClient(sekiroGroup, clientId, ip, port);

        sekiroClient.addEventListener(this);

        // 对client级别的生命周期监控
        for (SekiroClientEvent sekiroClientEvent : sekiroClientEvents) {
            sekiroClient.addEventListener(sekiroClientEvent);
        }
        return sekiroClient;
    }


    public ClusterSekiroClient setupSekiroRequestInitializer(SekiroRequestInitializer sekiroRequestInitializer) {
        this.sekiroRequestInitializer = sekiroRequestInitializer;
        return this;
    }

    public void destroy(long waitSeconds) {
        for (SekiroClient sekiroClient : runningSekiroClient.values()) {
            sekiroClient.destroy(waitSeconds);
        }
    }

    public ClusterSekiroClient start() {
        for (SekiroClient sekiroClient : runningSekiroClient.values()) {
            if (sekiroClient.getSekiroRequestInitializer() == null) {
                sekiroClient.setupSekiroRequestInitializer(sekiroRequestInitializer);
            }
            sekiroClient.start();
        }
        return this;
    }


    public ClusterSekiroClient addSekiroClientEventListener(SekiroClientEvent sekiroClientDisConnectedEvent) {
        sekiroClientEvents.add(sekiroClientDisConnectedEvent);
        return this;
    }

    public ClusterSekiroClient addClusterClientEventListener(ClusterClientEvent clusterClientEvent) {
        eventBus.registerEventObserver(clusterClientEvent);
        return this;
    }


    @Override
    public void onClientDestroy(final SekiroClient sekiroClient) {
        runningSekiroClient.remove(sekiroClient.getClientKey());
        if (runningSekiroClient.isEmpty()) {
            eventBus.findEventSender(ClusterClientDestroyEvent.class)
                    .onDestroy(ClusterSekiroClient.this);
        }
    }
}
