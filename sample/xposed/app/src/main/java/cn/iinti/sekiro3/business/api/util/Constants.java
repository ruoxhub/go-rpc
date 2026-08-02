package cn.iinti.sekiro3.business.api.util;

public interface Constants {
    int SERVER_READ_IDLE = 30;

    int SERVER_WRITE_IDLE = 20;

    int SERVER_READ_WRITE = 35;


    int DEFAULT_INVOKE_TIMEOUT = 15000;


    interface DEFAULT_SERVER_CONF {
        String DEFAULT_STAND_ALONG_SERVER = "sekiro.iinti.cn";
        int DEFAULT_STAND_ALONG_PORT = 5612;
    }

    interface REVERSED_WORDS {

        String GROUP = "group";

        String ACTION = "action";

        String API_TOKEN = "sekiro_token";

        String BIND_CLIENT = "bind_client";

        String INVOKE_TIME_OUT = "invoke_timeout";

        String CONSISTENT_INVOKE = "consistent_key";

        String INVOKE_TRACE_ID = "__invoke_trace_id";

        String ACTION_LIST = "__action_list";

        String SYSTEM_MSG_TOO_MANY_TIMEOUT = "__sekiro_system_timeout";

        String RESPONSE_5XX_AS_JSON = "__response_5xx_as_json";

        String WEB_SOCKET_SEQ_NUMBER = "__sekiro_seq__";

        String DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO = COMPRESS.DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO;

        String RESPONSE_STATUS = "__status__";
    }

    interface PAYLOAD_CONTENT_TYPE {
        String PAYLOAD_CONTENT_TYPE = "PAYLOAD_CONTENT_TYPE";
        String CONTENT_TYPE_SEKIRO_FAST_JSON = "CONTENT_TYPE_SEKIRO_FAST_JSON";

        String SEGMENT_STREAM_FLAG = "SEGMENT_STREAM_FLAG";
    }

    interface COMMON_HEADERS {
        String HEADER_CLIENT_ID = "SEKIRO_CLIENT_ID";
        String HEADER_SEKIRO_GROUP = "SEKIRO_GROUP";
        String HTTP_CONTENT_TYPE = "Content-Type";
        String HTTP_CONTENT_TYPE_JSON = "application/json;charset=utf8;";
    }

    interface COMPRESS {
        String COMPRESS_METHOD = "COMPRESS_METHOD";
        String COMPRESS_METHOD_GZIP = "COMPRESS_METHOD_GZIP";
        String COMPRESS_METHOD_SNAPPY = "COMPRESS_METHOD_SNAPPY";
        String COMPRESS_METHOD_NONE = "COMPRESS_METHOD_NONE";
        String DO_NOT_COMPRESS_FOR_SEKIRO_SEKIRO = "__NOT_COMPRESS_FOR_SEKIRO_SEKIRO";
    }
}
