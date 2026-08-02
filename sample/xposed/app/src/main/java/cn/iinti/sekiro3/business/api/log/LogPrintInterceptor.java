package cn.iinti.sekiro3.business.api.log;

public interface LogPrintInterceptor {
    void doPrint(LogPrinter logPrinter, int level, String message, Throwable throwable);
}
