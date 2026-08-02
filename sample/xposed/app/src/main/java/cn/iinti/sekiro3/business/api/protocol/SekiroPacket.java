package cn.iinti.sekiro3.business.api.protocol;

import lombok.Data;
import lombok.ToString;

import java.util.HashMap;
import java.util.Map;

@Data
@ToString
public class SekiroPacket {
    /**
     * 消息类型
     */
    private byte type;

    /**
     * 消息流水号
     */
    private int serialNumber = -1;

    /**
     * headers
     */
    private Map<String, String> headers = new HashMap<>();

    /**
     * 负载数据
     */
    private byte[] data;

    public SekiroPacket addHeader(String key, String value) {
        headers.put(key, value);
        return this;
    }

    public SekiroPacket migrateHeaders(SekiroPacket sekiroPacket) {
        headers.putAll(sekiroPacket.headers);
        return this;
    }

    public String getHeader(String key) {
        return headers.get(key);
    }

    /**
     * 给分段传输使用，除开payload区域，其他数据都深copy一份
     *
     * @return 新容器
     */
    public SekiroPacket duplicateForSegment() {
        SekiroPacket ret = new SekiroPacket();
        ret.type = type;
        ret.serialNumber = serialNumber;
        ret.headers = new HashMap<>(headers);
        return ret;
    }
}
