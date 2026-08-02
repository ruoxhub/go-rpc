package cn.iinti.sekiro3.business.api.interfaze;

import java.io.IOException;

public interface Compressor {
    /**
     * 压缩算法
     *
     * @return gzip\Snappy\等
     */
    String method();

    byte[] compress(byte[] input) throws IOException;

    byte[] decompress(byte[] input) throws IOException;
}
