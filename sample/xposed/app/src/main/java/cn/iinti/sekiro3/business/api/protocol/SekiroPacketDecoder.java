package cn.iinti.sekiro3.business.api.protocol;

import io.netty.buffer.ByteBuf;
import io.netty.buffer.Unpooled;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.ByteToMessageDecoder;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class SekiroPacketDecoder extends ByteToMessageDecoder {
    private static final byte HEADER_SIZE = PacketCommon.MAGIC_SIZE + PacketCommon.CONTENT_LENGTH_SIZE;

    /**
     * only for test,to test other language encode data(captured from wireshark)
     */
    public static SekiroPacket testDecode(byte[] payload) {
        ArrayList<Object> objects = new ArrayList<>();
        new SekiroPacketDecoder().decode(null, Unpooled.wrappedBuffer(payload), objects);
        return objects.isEmpty() ? null : (SekiroPacket) objects.get(0);
    }

    @Override
    protected void decode(ChannelHandlerContext ctx, ByteBuf byteBuf, List<Object> out) {
        while (true) {
            if (byteBuf.readableBytes() < HEADER_SIZE) {
                return;
            }
            byteBuf.markReaderIndex();
            long magic = byteBuf.readLong();
            if (magic != PacketCommon.MAGIC) {
                throw new IllegalStateException("pkg not start with legal magic: " + magic + " expected:" + PacketCommon.MAGIC);
            }
            int contentLength = byteBuf.readInt();
            if (byteBuf.readableBytes() < contentLength) {
                byteBuf.resetReaderIndex();
                return;
            }
            SekiroPacket sekiroPacket = decodePacket(byteBuf, contentLength);
            if (sekiroPacket != null) {
                out.add(sekiroPacket);
            }
        }
    }


    private SekiroPacket decodePacket(ByteBuf in, int contentLength) {
        SekiroPacket sekiroPacket = new SekiroPacket();
        byte type = in.readByte();
        int sn = in.readInt();

        sekiroPacket.setType(type);
        sekiroPacket.setSerialNumber(sn);

        byte headerSize = in.readByte();
        int dataLength = contentLength - PacketCommon.TYPE_SIZE - PacketCommon.SERIAL_NUMBER_SIZE - PacketCommon.HEADER_LEN_SIZE;
        Map<String, String> headers = new HashMap<>();
        for (int i = 0; i < headerSize; i++) {
            byte keyLength = in.readByte();
            byte[] keyBytes = new byte[keyLength];
            in.readBytes(keyBytes);
            byte valueLength = in.readByte();
            byte[] valueBytes = new byte[valueLength];
            in.readBytes(valueBytes);
            headers.put(new String(keyBytes, StandardCharsets.UTF_8), new String(valueBytes, StandardCharsets.UTF_8));
            // 需要减去记录 key 和 value 长度的占用字节数
            dataLength = dataLength - keyLength - PacketCommon.KEY_LEN_SIZE - valueLength - PacketCommon.VALUE_LEN_SIZE;
        }

        sekiroPacket.setHeaders(headers);
        if (dataLength < 0) {
            return null;
        }

        if (dataLength > 0) {
            byte[] data = new byte[dataLength];
            in.readBytes(data);
            sekiroPacket.setData(data);
        }
        return sekiroPacket;
    }
}
