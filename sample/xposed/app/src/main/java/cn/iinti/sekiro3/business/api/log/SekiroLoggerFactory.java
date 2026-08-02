package cn.iinti.sekiro3.business.api.log;

import android.util.Log;
import org.slf4j.LoggerFactory;

public class SekiroLoggerFactory {

    private static final LogPrinter defaultLogPrinter = adaptLogPrinter();
    private static LogSupplier logSupplier = new LogSupplier() {
        @Override
        public SekiroLogger createLogger() {
            // 在Android上面，发现如果使用部分情况调用 invoke-custom 会报错
            // 涉及到R8字节码转换过程
            // 所以这里修改为匿名内部类，而不是用lambda表达式
            return new SekiroLogger(defaultLogPrinter);
        }
    };

    @SuppressWarnings("unused")
    public static void setupLogSupplier(LogSupplier logSupplier) {
        if (logSupplier != null) {
            SekiroLoggerFactory.logSupplier = logSupplier;
        }
    }

    public static SekiroLogger createLogger() {
        return logSupplier.createLogger();
    }

    private interface LogSupplier {
        SekiroLogger createLogger();
    }

    private static LogPrinter adaptLogPrinter() {
        try {
            Log.i(SekiroLogger.tag, "test sekiro log");
            return new LogPrinterAndroid();
        } catch (Throwable throwable) {
            //ignore
        }
        try {
            LoggerFactory.getLogger(SekiroLogger.tag).info("test sekiro log");
            return new LogPrinterSlf4j();
        } catch (Throwable throwable) {
            //ignore
        }
        return new LogPrinterSystemOut();
    }
}
