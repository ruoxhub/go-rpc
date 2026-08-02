package cn.iinti.sekiro3.business.api.core.compress;

import cn.iinti.sekiro3.business.api.protocol.SekiroPacket;
import cn.iinti.sekiro3.business.api.util.Constants;
import io.netty.channel.ChannelHandlerContext;
import io.netty.handler.codec.MessageToMessageDecoder;

import java.util.List;

public class NettyDecompressHandler extends MessageToMessageDecoder<SekiroPacket> {
    private final CompressorManager compressorManager;
    private final boolean isSekiroServer;

    public NettyDecompressHandler(CompressorManager compressorManager, boolean isSekiroServer) {
        this.compressorManager = compressorManager;
        this.isSekiroServer = isSekiroServer;
    }

    @Override
    protected void decode(ChannelHandlerContext ctx, SekiroPacket msg, List<Object> out) throws Exception {
        if (msg.getHeaders().containsKey(Constants.COMPRESS.DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO)
                && isSekiroServer
        ) {
            out.add(msg);
            return;
        }
        compressorManager.handleDecompress(msg);
        out.add(msg);
    }
}
