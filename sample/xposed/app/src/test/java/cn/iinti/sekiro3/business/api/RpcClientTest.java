package cn.iinti.sekiro3.business.api;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class RpcClientTest {
    @Test
    public void buildsEncodedRegistrationUrl() {
        RpcClient client = new RpcClient("test group", "device/1", "10.0.2.2", 5612);

        assertEquals(
                "ws://10.0.2.2:5612/business/register?group=test+group&clientId=device%2F1",
                client.buildWebSocketUrl()
        );
        client.destroy();
    }

    @Test
    public void reconnectDelayUsesCappedExponentialBackoff() {
        assertEquals(1_000L, RpcClient.reconnectDelay(1));
        assertEquals(2_000L, RpcClient.reconnectDelay(2));
        assertEquals(4_000L, RpcClient.reconnectDelay(3));
        assertEquals(30_000L, RpcClient.reconnectDelay(6));
        assertEquals(30_000L, RpcClient.reconnectDelay(100));
    }
}
