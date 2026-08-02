package cn.iinti.sekiro3.business.api.interfaze;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class RpcRequestTest {
    @Test
    public void nestedParamsTakePriorityOverFlattenedValues() {
        JSONObject message = JSON.parseObject("{\"action\":\"echo\",\"value\":\"top\","
                + "\"params\":{\"value\":\"nested\",\"enabled\":true}}"
        );
        RpcRequest request = new RpcRequest(message);

        assertEquals("nested", request.getString("value"));
        assertTrue(request.getBooleanValue("enabled"));
        assertTrue(request.containsKey("value"));
        assertFalse(request.containsKey("missing"));
    }
}
