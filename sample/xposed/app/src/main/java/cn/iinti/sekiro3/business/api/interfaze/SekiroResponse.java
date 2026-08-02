package cn.iinti.sekiro3.business.api.interfaze;

import cn.iinti.sekiro3.business.api.core.SekiroFastJson;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacket;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacketType;
import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import io.netty.channel.Channel;
import lombok.Getter;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Hashtable;
import java.util.concurrent.atomic.AtomicBoolean;

public class SekiroResponse {

    @Getter
    private final SekiroRequest sekiroRequest;
    private final SekiroPacket responsePacket = SekiroPacketType.C_TYPE_INVOKE_RESPONSE.createPacket();

    private final Channel channel;

    private final SekiroLogger sekiroLogger;
    private final AtomicBoolean respond = new AtomicBoolean(false);


    public SekiroResponse(Channel channel, SekiroRequest sekiroRequest) {
        this.sekiroRequest = sekiroRequest;
        this.channel = channel;
        this.sekiroLogger = sekiroRequest.getSekiroLogger();
        SekiroPacket requestSekiroPacket = sekiroRequest.getRequestSekiroPacket();
        responsePacket.setSerialNumber(requestSekiroPacket.getSerialNumber());
    }

    public void afterSekiroRequestInit() {
        if (sekiroRequest.containsKey(Constants.REVERSED_WORDS.DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO)) {
            // 证明来自Sekiro->Sekiro模式
            responsePacket.addHeader(Constants.COMPRESS.DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO, "true");
        }
    }

    public void failed(int errorCode, Throwable throwable) {
        send(CommonRes.failed(errorCode, getStackTrack(throwable)));
    }

    public void failed(int errorCode, String message) {
        send(CommonRes.failed(errorCode, message));
    }

    public void failed(String message) {
        send(CommonRes.failed(-1, message));
    }

    public <T> void success(T data) {
        send(CommonRes.success(data));
    }


    public void send(Object o) {
        if (!respond.compareAndSet(false, true)) {
            sekiroLogger.warn("the response data has been send already!!", new Throwable());
            return;
        }

        if (o instanceof CommonRes) {
            sendSekiroFastJson((CommonRes<?>) o);
            return;
        }
        if (o instanceof InputStream) {
            sendStream((InputStream) o);
            return;
        }
        if (o instanceof byte[]) {
            sendStream(new ByteArrayInputStream((byte[]) o));
            return;
        }
        if (o instanceof File) {
            responsePacket.addHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE,
                    getContentType(((File) o).getPath()));
            try {
                sendStream(new FileInputStream((File) o));
            } catch (FileNotFoundException e) {
                sekiroLogger.error("response with none exist file:", e);
                sendSekiroFastJson(CommonRes.failed("response with none exist file"));
            }
            return;
        }

        if (o instanceof String) {
            responsePacket.addHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE, "text/plain;charset=utf8");
            sendStream(new ByteArrayInputStream(((String) o).getBytes(StandardCharsets.UTF_8)));
            return;
        }
        // by default, we response a wrapper object
        sendSekiroFastJson(CommonRes.success(o));

    }

    private static String getContentType(String path) {
        String type = tryGetContentType(path);
        if (type != null)
            return type;
        return "text/plain";
    }

    private static String tryGetContentType(String path) {
        int index = path.lastIndexOf(".");
        if (index != -1) {
            String e = path.substring(index + 1);
            return mContentTypes.get(e);
        }
        return null;
    }

    private static final Hashtable<String, String> mContentTypes = new Hashtable<String, String>();

    static {
        mContentTypes.put("js", "application/javascript");
        mContentTypes.put("json", "application/json");
        mContentTypes.put("png", "image/png");
        mContentTypes.put("jpg", "image/jpeg");
        mContentTypes.put("html", "text/html");
        mContentTypes.put("css", "text/css");
        mContentTypes.put("mp4", "video/mp4");
        mContentTypes.put("mov", "video/quicktime");
        mContentTypes.put("wmv", "video/x-ms-wmv");
    }

    private void sendStream(InputStream inputStream) {
        String contentType
                = responsePacket.getHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE);
        if (TextUtil.isBlank(contentType)) {
            // setup default contentType
            responsePacket.addHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE, "application/octet-stream");
        }

        // 文件传输场景下，按1M大小分包，考虑调用方可能在弱网环境(如山区手机流量)，分包不超过1M
        autoJudeCompress();

        int bufferSize = 1024 * 1024;

        int readSize;
        try {
            do {
                byte[] buffer = new byte[bufferSize];
                readSize = inputStream.read(buffer);
                if (readSize < buffer.length) {
                    responsePacket.setData(Arrays.copyOfRange(buffer, 0, readSize));
                    channel.write(responsePacket);
                } else {
                    SekiroPacket sekiroPacket = responsePacket.duplicateForSegment();
                    sekiroPacket.setData(buffer);
                    sekiroPacket.addHeader(Constants.PAYLOAD_CONTENT_TYPE.SEGMENT_STREAM_FLAG, "true");
                    channel.write(sekiroPacket);
                }
            } while (readSize >= bufferSize);
        } catch (IOException e) {
            sekiroLogger.error("stream read exception", e);
            SekiroPacket packet = SekiroPacketType.C_TYPE_INVOKE_STREAM_CLOSE.createPacket();
            packet.setSerialNumber(responsePacket.getSerialNumber());
            channel.writeAndFlush(packet);
        } finally {
            channel.flush();
        }
    }


    public static String getStackTrack(Throwable throwable) {
        ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
        PrintWriter printWriter = new PrintWriter(new OutputStreamWriter(byteArrayOutputStream));
        throwable.printStackTrace(printWriter);
        printWriter.close();
        try {
            return byteArrayOutputStream.toString(StandardCharsets.UTF_8.name());
        } catch (UnsupportedEncodingException e) {
            throw new RuntimeException(e);
        }
    }


    private void sendSekiroFastJson(CommonRes<?> commonRes) {
        //sekiroLogger.info("sekiro response: " + JSONObject.toJSONString(commonRes));
        responsePacket.addHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE, Constants.PAYLOAD_CONTENT_TYPE.CONTENT_TYPE_SEKIRO_FAST_JSON);
        responsePacket.addHeader(Constants.REVERSED_WORDS.RESPONSE_STATUS, String.valueOf(commonRes.getStatus()));
        responsePacket.setData(SekiroFastJson.encode(commonRes));
        autoJudeCompress();
        channel.writeAndFlush(responsePacket);
    }


    //压缩相关API暴露开始

    /**
     * 禁止本本次返回的压缩，如果是内网同机房通信，可以关闭压缩
     */
    public void notCompress() {
        responsePacket.addHeader(Constants.COMPRESS.COMPRESS_METHOD, Constants.COMPRESS.COMPRESS_METHOD_NONE);
    }

    public void userCompressMethod(String compressMethod) {
        responsePacket.addHeader(Constants.COMPRESS.COMPRESS_METHOD, compressMethod);
    }

    private void autoJudeCompress() {
        String header = responsePacket.getHeader(Constants.COMPRESS.COMPRESS_METHOD);
        if (TextUtil.isNotBlank(header)) {
            return;
        }
        String contentType = responsePacket.getHeader(Constants.PAYLOAD_CONTENT_TYPE.PAYLOAD_CONTENT_TYPE)
                .toLowerCase();
        boolean needCompress = false;
        if (contentType.equals(Constants.PAYLOAD_CONTENT_TYPE.CONTENT_TYPE_SEKIRO_FAST_JSON.toLowerCase())
                && responsePacket.getData().length > 128
        ) {
            needCompress = true;
        } else if (contentType.contains("javascript")
                || contentType.contains("json")
                || contentType.startsWith("text/")
        ) {
            needCompress = true;
        }
        if (needCompress) {
            // 默认都做gzip压缩，这个默认两端都支持
            responsePacket.addHeader(Constants.COMPRESS.COMPRESS_METHOD, Constants.COMPRESS.COMPRESS_METHOD_GZIP);
        }
    }

    public void setHeader(String key, String value) {
        responsePacket.addHeader(key, value);
    }
}
