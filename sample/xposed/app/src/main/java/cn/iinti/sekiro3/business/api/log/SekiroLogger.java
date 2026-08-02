package cn.iinti.sekiro3.business.api.log;

public class SekiroLogger {
    private LogPrinter logPrinter;
    public static String tag = "Sekiro";


    public SekiroLogger(LogPrinter logPrinter) {
        this.logPrinter = logPrinter;
    }

    public SekiroLogger createChildLogger(final LogPrintInterceptor interceptor) {
        SekiroLogger childLogger = new SekiroLogger(logPrinter);
        return childLogger.setupInterceptor(interceptor);
    }

    public SekiroLogger setupInterceptor(final LogPrintInterceptor interceptor) {
        final LogPrinter delegate = logPrinter;
        logPrinter = new LogPrinter() {
            @Override
            public void print(int level, String message, Throwable throwable) {
                interceptor.doPrint(delegate, level, message, throwable);
            }
        };
        return this;
    }


    public void info(String msg) {
        logPrinter.print(LogPrinter.INFO, msg, null);
    }


    public void info(String msg, Throwable throwable) {
        logPrinter.print(LogPrinter.INFO, msg, throwable);
    }


    public void warn(String msg) {
        logPrinter.print(LogPrinter.WARNING, msg, null);
    }


    public void warn(String msg, Throwable throwable) {
        logPrinter.print(LogPrinter.WARNING, msg, throwable);
    }


    public void error(String msg) {
        logPrinter.print(LogPrinter.ERROR, msg, null);
    }


    public void error(String msg, Throwable throwable) {
        logPrinter.print(LogPrinter.ERROR, msg, throwable);
    }


}
