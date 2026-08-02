package cn.iinti.sekiro3.business.api.core;

import cn.iinti.sekiro3.business.api.interfaze.CommonRes;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import com.alibaba.fastjson.JSONObject;
import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import lombok.AllArgsConstructor;
import lombok.Data;

import java.nio.charset.StandardCharsets;

/**
 * 内部专用fastjson，避免服务器进行json反序列化
 */
public class SekiroFastJson {

    @Data
    @AllArgsConstructor
    public static class FastJson {
        private int status;
        private String errorMessage;
        private String dataJson;
        private String finalJson;
    }

    public static FastJson quickJsonDecode(byte[] data, String clientId) {
        ByteBuf byteBuf = Unpooled.wrappedBuffer(data);
        int status = byteBuf.readInt();
        String errorMessage = readString(byteBuf);
        String dataJson = readString(byteBuf);

        String finalJson = "{\"clientId\":" + JSONObject.toJSONString(clientId) +
                ",\"message\":" + JSONObject.toJSONString(errorMessage) +
                ",\"status\":" + status +
                ",\"data\":" + dataJson +
                "}";
        return new FastJson(status, errorMessage, dataJson, finalJson);

    }


    public static byte[] encode(CommonRes<?> commonRes) {
        ByteBuf byteBuf = Unpooled.buffer();
        byteBuf.writeInt(commonRes.getStatus());
        appendString(commonRes.getMessage(), byteBuf);

        if (commonRes.getData() == null) {
            appendString(null, byteBuf);
        } else {
            appendString(JSONObject.toJSONString(commonRes.getData()), byteBuf);
        }
        byte[] ret = new byte[byteBuf.readableBytes()];
        byteBuf.readBytes(ret);
        byteBuf.release();
        return ret;
    }

    private static String readString(ByteBuf byteBuf) {
        int length = byteBuf.readInt();
        if (length == 0) {
            return null;
        }
        byte[] content = new byte[length];
        byteBuf.readBytes(content);
        return new String(content, StandardCharsets.UTF_8);
    }

    private static void appendString(String input, ByteBuf byteBuf) {
        if (TextUtil.isEmpty(input)) {
            byteBuf.writeInt(0);
            return;
        }
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        byteBuf.writeInt(bytes.length);
        byteBuf.writeBytes(bytes);
    }

}
