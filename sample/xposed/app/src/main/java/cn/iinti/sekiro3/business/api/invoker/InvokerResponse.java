package cn.iinti.sekiro3.business.api.invoker;

import cn.iinti.sekiro3.business.api.core.SekiroFastJson;
import cn.iinti.sekiro3.business.api.util.Constants;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

public class InvokerResponse {

    private Map<String, String> headers = new HashMap<>();
    private byte[] bytes;

    private boolean successful;

    public String string() {
        String contentType = headers.get(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE);
        if (Constants.PAYLOAD_CONTENT_TYPE.CONTENT_TYPE_SEKIRO_FAST_JSON.equals(contentType)) {
            // 内部快速反序列化，可以避免服务器进行json解码，减少CPU计算
            SekiroFastJson.FastJson fastJson = SekiroFastJson.quickJsonDecode(bytes,
                    headers.get(Constants.COMMON_HEADERS.HEADER_CLIENT_ID));
            return fastJson.getFinalJson();
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }


    public void setHeaders(Map<String, String> headers) {
        this.headers = headers;
    }

  public   void setBytes(byte[] bytes) {
        this.bytes = bytes;
    }


    public Map<String, String> getHeaders() {
        return headers;
    }

    public byte[] getBytes() {
        return bytes;
    }

    public boolean isSuccessful() {
        return successful;
    }

   public void setSuccessful() {
        this.successful = true;
    }

}
