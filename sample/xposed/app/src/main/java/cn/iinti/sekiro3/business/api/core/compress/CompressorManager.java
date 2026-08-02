package cn.iinti.sekiro3.business.api.core.compress;

import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.interfaze.Compressor;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacket;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacketType;
import cn.iinti.sekiro3.business.api.util.TextUtil;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class CompressorManager {
    private final Map<String, Compressor> compressorMap = new HashMap<>();

    public CompressorManager() {
        setupDefaultCompressor();
    }

    private void setupDefaultCompressor() {
        registerCompressor(new GzipCompressor());
        registerCompressor(new NoneCompressor());
        try {
            Class.forName("org.xerial.snappy.Snappy");
            registerCompressor(new SnappyCompressor());
        } catch (Throwable throwable) {
            //ignore
        }
    }

    public CompressorManager registerCompressor(Compressor compressor) {
        compressorMap.put(compressor.method().trim(), compressor);
        return this;
    }

    private Compressor fetchCompressor(SekiroPacket sekiroPacket) {
        if (sekiroPacket.getType() != SekiroPacketType.C_TYPE_INVOKE_RESPONSE.getCode()
                && sekiroPacket.getType() != SekiroPacketType.S_TYPE_INVOKE_RESPONSE.getCode()
        ) {
            return null;
        }
        String method = sekiroPacket.getHeaders().get(Constants.COMPRESS.COMPRESS_METHOD);
        if (TextUtil.isBlank(method)) {
            return null;
        }
        Compressor compressor = compressorMap.get(method.trim());
        if (compressor == null) {
            throw new IllegalStateException("can not decompress sekiro package with compress method: " + method);
        }
        return compressor;
    }

    public void handleDecompress(SekiroPacket sekiroPacket) throws IOException {
        Compressor compressor = fetchCompressor(sekiroPacket);
        if (compressor == null) {
            return;
        }

        byte[] decompress = compressor.decompress(sekiroPacket.getData());
        sekiroPacket.setData(decompress);
    }

    public void doCompress(SekiroPacket sekiroPacket) throws IOException {
        Compressor compressor = fetchCompressor(sekiroPacket);
        if (compressor == null) {
            return;
        }

        byte[] decompress = compressor.compress(sekiroPacket.getData());
        sekiroPacket.setData(decompress);
    }
}
