package cn.iinti.sekiro3.business.api.protocol;

public class PacketCommon {

    public static final byte MAGIC_SIZE = 8;
    public static final byte CONTENT_LENGTH_SIZE = 4;

    static final int TYPE_SIZE = 1;

    static final int SERIAL_NUMBER_SIZE = 4;

    static final int HEADER_LEN_SIZE = 1;

    static final int KEY_LEN_SIZE = 1;

    static final int VALUE_LEN_SIZE = 1;

    // magic is the hexData of "sekiro01"
    public static final long MAGIC = 0x73656b69726f3031L;

}
