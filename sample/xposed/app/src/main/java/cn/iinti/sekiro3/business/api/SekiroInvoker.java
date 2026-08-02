package cn.iinti.sekiro3.business.api;

import cn.iinti.sekiro3.business.api.core.eventbus.event.invoker.InvokerEvent;
import cn.iinti.sekiro3.business.api.invoker.Call;
import cn.iinti.sekiro3.business.api.invoker.InvokerInstance;
import cn.iinti.sekiro3.business.api.invoker.InvokerRequest;
import cn.iinti.sekiro3.business.api.util.Constants;

import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;

/**
 * 为调用端封装，java业务非常建议使用本API替代httpAPI<br>
 * 优点如下：
 * 1.模式为ClientLB，在客户端进行Sekiro集群负载均衡，相对于http ng路由来说，少一层转发，减少服务器的带宽压力。服务器不需要存在网关层
 * 2.天然keepAlive，链路只需要单次tcp连接建立，之后在tcp通道上完成所有的调用。对服务器的套接字资源几乎不存在占用
 * 3.无解压器，节省服务器CPU资源。Sekiro->Sekiro模式下，报文在sekiro服务器上不会经过解压操作。
 * 4.API封装，和对http接口封装相比更加简单。Sekiro相关的必要参数直接封装到API中了。同时避免java方向http网络库选择困难问题
 */
public class SekiroInvoker {

    private final String apiToken;

    private final LinkedList<InvokerInstance> runningClientList = new LinkedList<>();

    public SekiroInvoker(String[] serverList) {
        this("", serverList);
    }

    public SekiroInvoker(String apiToken, String[] serverList) {
        this.apiToken = apiToken;
        if (serverList == null || serverList.length == 0) {
            throw new IllegalStateException("no server configured");
        }
        // 第一次启动，需要blocking，这样SekiroInvoker被构建成功之后，就可以进行调用了
        // 对于客户端来说，用户编程模型可以更加简单一些。所以API层面可以BIO blocking
        List<String> strings = Arrays.asList(serverList);

        // 做一次shuffle，第一个可用服务器将会blocking，剩余server异步
        // 这样多server模式不会存在太久的等待时间，
        // 此种场景，如果first start server一直是确定的，那么每次启动流量都会打到同一台服务器，我希望第一次启动的流量也是随机在不同服务器上面的
        Collections.shuffle(strings);
        for (String server : strings) {
            runningClientList.add(createInvokerInstance(server));
        }
    }

    @SuppressWarnings("unused")
    public void addEventListener(InvokerEvent event) {
        synchronized (runningClientList) {
            for (InvokerInstance invoker : runningClientList) {
                invoker.addInvokerListener(event);
            }
        }
    }

    private InvokerInstance createInvokerInstance(String config) {
        String server = config.trim();
        String ip = server;
        int port = Constants.DEFAULT_SERVER_CONF.DEFAULT_STAND_ALONG_PORT;
        int index = server.indexOf(':');
        if (index > 0) {
            ip = server.substring(0, index);
            port = Integer.parseInt(server.substring(index + 1).trim());
        }
        InvokerInstance invokerInstance = new InvokerInstance(ip, port);
        invokerInstance.start(true);
        return invokerInstance;
    }


    public Call newCall(InvokerRequest invokerRequest) {
        return new Call(this, invokerRequest);
    }

    public final void performInvoke(final Call call) {
        boolean invoked = false;
        synchronized (runningClientList) {
            int size = runningClientList.size();
            for (int i = 0; i < size; i++) {
                InvokerInstance invokerInstance = runningClientList.pollFirst();
                if (invokerInstance == null) {
                    call.callback().onFailure(call, new IOException("can not allocate sekiro server node resource"));
                    return;
                }
                runningClientList.addLast(invokerInstance);
                if (!invokerInstance.isAlive()) {
                    continue;
                }
                invokerInstance.performInvoke(call, apiToken);
                invoked = true;
                break;
            }
        }

        if (!invoked) {
            call.callback().onFailure(call, new IOException("can not allocate sekiro server node resource"));
        }
    }


    public void destroy() {
        synchronized (runningClientList) {
            for (InvokerInstance invoker : runningClientList) {
                invoker.close();
            }
            runningClientList.clear();
        }
    }

    @Override
    protected void finalize() throws Throwable {
        destroy();
        super.finalize();
    }
}
