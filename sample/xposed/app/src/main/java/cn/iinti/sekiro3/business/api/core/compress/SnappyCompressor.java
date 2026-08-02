package cn.iinti.sekiro3.business.api.core.compress;

import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.interfaze.Compressor;
import org.xerial.snappy.Snappy;

import java.io.IOException;

public class SnappyCompressor implements Compressor {
    @Override
    public String method() {
        return Constants.COMPRESS.COMPRESS_METHOD_SNAPPY;
    }

    @Override
    public byte[] compress(byte[] input) throws IOException {
        return Snappy.compress(input);
    }

    @Override
    public byte[] decompress(byte[] input) throws IOException {
        return Snappy.uncompress(input);
    }
}
