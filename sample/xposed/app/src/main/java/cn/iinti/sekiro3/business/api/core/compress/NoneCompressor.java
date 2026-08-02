package cn.iinti.sekiro3.business.api.core.compress;

import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.interfaze.Compressor;

import java.io.IOException;

public class NoneCompressor implements Compressor {
    @Override
    public String method() {
        return Constants.COMPRESS.COMPRESS_METHOD_NONE;
    }

    @Override
    public byte[] compress(byte[] input) throws IOException {
        return input;
    }

    @Override
    public byte[] decompress(byte[] input) throws IOException {
        return input;
    }
}
