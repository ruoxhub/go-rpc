package cn.iinti.sekiro3.business.api;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class RpcClientTest {
    @Test
    public void buildsEncodedRegistrationUrl() {
        RpcClient client = new RpcClient("test group", "device/1", "10.0.2.2", 5612);

        assertEquals(
                "ws://10.0.2.2:5612/business/register?protocol_version=1&capabilities=invocation_context.v1&group=test+group&clientId=device%2F1",
                client.buildWebSocketUrl()
        );
        client.destroy();
    }

}
