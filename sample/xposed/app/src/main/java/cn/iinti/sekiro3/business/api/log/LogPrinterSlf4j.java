package cn.iinti.sekiro3.business.api.log;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * slf4j主要面对服务端，或者jvm模式的client集群，此时按照
 */
public class LogPrinterSlf4j implements LogPrinter {
    private static final Logger logger = LoggerFactory.getLogger(SekiroLogger.tag);

    @Override
    public void print(int level, String message, Throwable throwable) {
        switch (level) {
            case LogPrinter.INFO:
                if (throwable == null) {
                    logger.info(message);
                } else {
                    logger.info(message, throwable);
                }
                break;
            case LogPrinter.WARNING:
                if (throwable == null) {
                    logger.warn(message);
                } else {
                    logger.warn(message, throwable);
                }
                break;
            case LogPrinter.ERROR:
                if (throwable == null) {
                    logger.error(message);
                } else {
                    logger.error(message, throwable);
                }
                break;
        }
    }
}
