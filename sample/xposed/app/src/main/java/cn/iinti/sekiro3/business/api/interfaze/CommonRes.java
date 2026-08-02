package cn.iinti.sekiro3.business.api.interfaze;

import cn.iinti.sekiro3.business.api.log.SekiroGlobalLogger;
import cn.iinti.sekiro3.business.api.util.TextUtil;
import lombok.Data;

@Data
public class CommonRes<T> {
    private int status = statusOK;
    private String message;
    private T data;
    private String clientId;

    public static final int statusOK = 0;
    public static final int statusError = -1;
    public static final int statusBadRequest = -2;
    public static final int statusSekiroDestroy = -3;

    public static <T> CommonRes<T> failed(String message) {
        return failed(statusError, message);
    }

    public static <T> CommonRes<T> failed(int status, String message) {
        CommonRes<T> ret = new CommonRes<>();
        ret.status = status;
        ret.message = message;
        if (status != statusOK && TextUtil.isEmpty(message)) {
            SekiroGlobalLogger.warn("empty error message", new Throwable());
        }
        return ret;
    }

    public static <T> CommonRes<T> failed(int errorCode, Throwable throwable) {
        return failed(errorCode, SekiroResponse.getStackTrack(throwable));

    }

    public static <T> CommonRes<T> success(T t) {
        CommonRes<T> ret = new CommonRes<>();
        ret.status = statusOK;
        ret.message = null;
        ret.data = t;
        return ret;
    }

}
