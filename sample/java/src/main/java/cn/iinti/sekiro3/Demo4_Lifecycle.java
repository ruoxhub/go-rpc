package cn.iinti.sekiro3;

import cn.iinti.sekiro3.business.api.ClusterRpcClient;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.RpcClientConnectEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.RpcClientDestroyEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.client.RpcClientDisConnectedEvent;
import cn.iinti.sekiro3.business.api.core.eventbus.event.cluster.ClusterClientDestroyEvent;
import cn.iinti.sekiro3.business.api.interfaze.ActionHandler;
import cn.iinti.sekiro3.business.api.interfaze.RpcRequest;
import cn.iinti.sekiro3.business.api.interfaze.RpcResponse;

public class Demo4_Lifecycle {
    public static void main(String[] args) throws InterruptedException {
        // http://sekiro.iinti.cn/business/invoke?group=test&action=test&sekiro_token=123
        ClusterRpcClient sekiroClient = new ClusterRpcClient("test", new String[]{"sekiro.iinti.com:5612"})
                .setupRpcRequestInitializer((sekiroRequest, handlerRegistry) -> handlerRegistry.registerRpcHandler(new ActionHandler() {

                    @Override
                    public String action() {
                        return "test";
                    }

                    @Override
                    public void handleRequest(RpcRequest sekiroRequest, RpcResponse sekiroResponse) {
                        sekiroResponse.success("ok");
                    }
                }))
                // 集群版和单机版均有这一组关于sekiro生命周期的挂钩点，给业务使用
                .addRpcClientEventListener((RpcClientConnectEvent) sekiroClient1 -> System.out.println(sekiroClient1.getClientKey() + ": 连接"))
                .addRpcClientEventListener((RpcClientDisConnectedEvent) sekiroClient12 -> System.out.println(sekiroClient12.getClientKey() + ": 断开"))
                .addRpcClientEventListener((RpcClientDestroyEvent) sekiroClient13 -> System.out.println(sekiroClient13.getClientKey() + ": 销毁"))
                .addClusterClientEventListener((ClusterClientDestroyEvent) clusterRpcClient -> System.out.println("集群client销毁"))
                .start();

        Thread.sleep(20000);

        sekiroClient.destroy(10);
    }
}
