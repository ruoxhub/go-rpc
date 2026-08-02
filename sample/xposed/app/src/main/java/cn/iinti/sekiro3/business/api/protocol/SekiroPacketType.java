package cn.iinti.sekiro3.business.api.protocol;

import lombok.Getter;

public enum SekiroPacketType {
    // common type
    TYPE_HEARTBEAT((byte) 0x00),
    //  client type
    C_TYPE_REGISTER((byte) 0x10),
    C_TYPE_INVOKE_RESPONSE((byte) 0x11),
    C_TYPE_OFFLINE((byte) 0x12),
    C_TYPE_CMD_RESPONSE((byte) 0x13),
    C_TYPE_INVOKE_STREAM_CLOSE((byte) 0x14),
    // server type
    S_TYPE_INVOKE((byte) 0x20),
    S_TYPE_CMD((byte) 0x21),
    S_TYPE_OFFLINE_RESPONSE((byte) 0x22),
    // 服务器到Invoker的响应
    S_TYPE_INVOKE_RESPONSE((byte) 0x23),
    S_TYPE_INVOKE_CONNECTED((byte) 0x24),
    //

    // invoker type
    I_TYPE_CONNECT((byte) 0x30),
    I_TYPE_INVOKE((byte) 0x31)
    //
    ;
    @Getter
    private final byte code;

    SekiroPacketType(byte code) {
        this.code = code;
    }

    public static SekiroPacketType getByCode(byte code) {
        for (SekiroPacketType sekiroPacketType : values()) {
            if (sekiroPacketType.code == code) {
                return sekiroPacketType;
            }
        }
        return null;
    }

    public SekiroPacket createPacket() {
        SekiroPacket ret = new SekiroPacket();
        ret.setType(code);
        return ret;
    }

}
