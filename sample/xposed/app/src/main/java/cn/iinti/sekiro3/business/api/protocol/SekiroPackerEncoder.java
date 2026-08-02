package cn.iinti.sekiro3.business.api.protocol;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.MessageToByteEncoder;
import lombok.Data;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class SekiroPackerEncoder extends MessageToByteEncoder<SekiroPacket> {

    private static final int headerSize = PacketCommon.TYPE_SIZE + PacketCommon.SERIAL_NUMBER_SIZE + PacketCommon.HEADER_LEN_SIZE;

    @Override
    protected void encode(ChannelHandlerContext ctx, SekiroPacket msg, ByteBuf out) {

        int bodyLength = headerSize;

        Map<String, String> headers = msg.getHeaders();
        if (headers.size() > 127) {
            throw new IllegalStateException("too many headers: " + headers.size());
        }

        List<HeaderHelper> headerHelpers = new ArrayList<>();
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            HeaderHelper headerHelper = new HeaderHelper(entry.getKey(), entry.getValue());
            headerHelpers.add(headerHelper);

            // 需要加上记录 key 和 value 长度的占用字节数
            bodyLength += PacketCommon.KEY_LEN_SIZE + headerHelper.keyLength;
            bodyLength += PacketCommon.VALUE_LEN_SIZE + headerHelper.valueLength;
        }

        if (msg.getData() != null) {
            bodyLength += msg.getData().length;
        }

        // 魔数，解码时用于判断是否为合法数据包，避免无效数据攻击
        out.writeLong(PacketCommon.MAGIC);
        out.writeInt(bodyLength);
        out.writeByte(msg.getType());
        out.writeInt(msg.getSerialNumber());
        out.writeByte(headers.size());

        for (HeaderHelper headerHelper : headerHelpers) {
            out.writeByte(headerHelper.keyLength);
            out.writeBytes(headerHelper.keyBytes);
            out.writeByte(headerHelper.valueLength);
            out.writeBytes(headerHelper.valueBytes);
        }

        if (msg.getData() != null) {
            out.writeBytes(msg.getData());
        }

    }

    @Data
    private static class HeaderHelper {

        private String key;
        private int keyLength;
        private byte[] keyBytes;

        private String value;
        private int valueLength;
        private byte[] valueBytes;

        public HeaderHelper(String key, String value) {
            keyBytes = key.getBytes(StandardCharsets.UTF_8);
            keyLength = keyBytes.length;
            if (keyLength > 127) {
                throw new IllegalStateException("too large key: " + key);
            }
            valueBytes = value.getBytes(StandardCharsets.UTF_8);
            valueLength = valueBytes.length;
            if (valueLength > 127) {
                throw new IllegalStateException("too large value: " + key);
            }
        }

    }


}
