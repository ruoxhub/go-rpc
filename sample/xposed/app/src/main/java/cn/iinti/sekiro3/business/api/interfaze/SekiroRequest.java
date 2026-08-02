package cn.iinti.sekiro3.business.api.interfaze;

import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.log.LogPrintInterceptor;
import cn.iinti.sekiro3.business.api.log.LogPrinter;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacket;
import cn.iinti.sekiro3.business.api.util.Constants;
import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import lombok.Getter;

import java.nio.charset.StandardCharsets;
import java.util.Map;

public class SekiroRequest {

    @Getter
    private JSONObject jsonModel;

    @Getter
    private String paramContent;

    @Getter
    private final SekiroPacket requestSekiroPacket;

    private final Map<String, String> headers;

    public String getRequestHeader(String key) {
        return headers.get(key);
    }

    @Getter
    private final SekiroClient sekiroClient;

    @Getter
    private final SekiroLogger sekiroLogger;


    private String traceId;
    private String action;


    public SekiroRequest(SekiroClient sekiroClient, SekiroPacket requestSekiroPacket) {
        this.requestSekiroPacket = requestSekiroPacket;
        this.sekiroClient = sekiroClient;
        headers = requestSekiroPacket.getHeaders();
        sekiroLogger = sekiroClient.getSekiroLogger().createChildLogger(new LogPrintInterceptor() {
            private int findInsertIndex(String msg, int begin) {
                int start = msg.indexOf('[', begin);
                if (start < 0) {
                    return -1;
                }
                int end = msg.indexOf(']', start + 1);
                if (end < 0) {
                    return -1;
                }
                if (end > 64) {
                    // only scan prefix,skip message content
                    return end;
                }
                int nextSegmentIndex = findInsertIndex(msg, end + 1);
                return nextSegmentIndex < 0 ? end : nextSegmentIndex;
            }

            @Override
            public void doPrint(LogPrinter logPrinter, int level, String message, Throwable throwable) {
                int insertIndex = findInsertIndex(message, 0);
                String prefix = "";
                if (insertIndex > 0) {
                    prefix = message.substring(0, insertIndex + 1);
                    message = message.substring(insertIndex + 1);
                }
                String newMsg = prefix + (action == null ? "" : "[action:" + action + "]") + (traceId == null ? "" : "[traceId:" + traceId + "]") + message;
                logPrinter.print(level, newMsg, throwable);
            }
        });
        // 请注意jsonMode结构解析需要放到执行的时候进行，构造函数时机在netty线程中
        // json结构解析需要放到工作线程中执行，避免netty线程阻塞
    }

    public void doInit() {
        if (jsonModel != null) {
            return;
        }

        paramContent = new String(requestSekiroPacket.getData(), StandardCharsets.UTF_8);
        jsonModel = JSON.parseObject(paramContent);
        traceId = jsonModel.getString(Constants.REVERSED_WORDS.INVOKE_TRACE_ID);
        action = jsonModel.getString(Constants.REVERSED_WORDS.ACTION);
    }

    public boolean containsKey(String key) {
        return jsonModel.containsKey(key);
    }

    public boolean containsValue(Object value) {
        return jsonModel.containsValue(value);
    }

    public Object get(String key) {
        return jsonModel.get(key);
    }

    public JSONObject getJSONObject(String key) {
        return jsonModel.getJSONObject(key);
    }

    public JSONArray getJSONArray(String key) {
        return jsonModel.getJSONArray(key);
    }

    public <T> T getObject(String key, Class<T> clazz) {
        return jsonModel.getObject(key, clazz);
    }


    public boolean getBooleanValue(String key) {
        return jsonModel.getBooleanValue(key);
    }


    public int getIntValue(String key) {
        return jsonModel.getIntValue(key);
    }


    public long getLongValue(String key) {
        return jsonModel.getLongValue(key);
    }


    public float getFloatValue(String key) {
        return jsonModel.getFloatValue(key);
    }


    public double getDoubleValue(String key) {
        return jsonModel.getDoubleValue(key);
    }


    public String getString(String key) {
        return jsonModel.getString(key);
    }


}
