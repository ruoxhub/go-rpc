package cn.iinti.sekiro3.business.api.log;

import java.io.PrintStream;

public class LogPrinterSystemOut implements LogPrinter {
    @Override
    public void print(int level, String message, Throwable throwable) {
        PrintStream printStream;
        switch (level) {
            case LogPrinter.INFO:
            case LogPrinter.WARNING:
                printStream = System.out;
                break;
            default:
                printStream = System.err;
                break;
        }
        printStream.println(message);
        if (throwable != null) {
            throwable.printStackTrace(printStream);
        }
    }
}
