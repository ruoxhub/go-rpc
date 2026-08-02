package cn.iinti.sekiro3.business.api.log;

import lombok.Getter;

/**
 * 系统级别日志，使用这个工具类打印
 */
public class SekiroGlobalLogger {
    @Getter
    private static final SekiroLogger global = SekiroLoggerFactory.createLogger();

    public static void info(String msg) {
        global.info(msg);
    }

    public static void info(String msg, Throwable throwable) {
        global.info(msg, throwable);
    }

    public static void warn(String msg) {
        global.warn(msg);
    }

    public static void warn(String msg, Throwable throwable) {
        global.warn(msg, throwable);
    }

    public static void error(String msg) {
        global.error(msg);
    }

    public static void error(String msg, Throwable throwable) {
        global.error(msg, throwable);
    }
}
