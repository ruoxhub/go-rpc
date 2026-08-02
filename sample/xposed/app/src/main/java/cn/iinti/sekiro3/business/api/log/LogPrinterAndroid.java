package cn.iinti.sekiro3.business.api.log;

import android.util.Log;

public class LogPrinterAndroid implements LogPrinter {
    @Override
    public void print(int level, String message, Throwable throwable) {
        switch (level) {
            case LogPrinter.INFO:
                if (throwable == null) {
                    Log.i(SekiroLogger.tag, message);
                } else {
                    Log.i(SekiroLogger.tag, message, throwable);
                }
                break;
            case LogPrinter.WARNING:
                if (throwable == null) {
                    Log.w(SekiroLogger.tag, message);
                } else {
                    Log.w(SekiroLogger.tag, message, throwable);
                }
                break;
            case LogPrinter.ERROR:
                if (throwable == null) {
                    Log.e(SekiroLogger.tag, message);
                } else {
                    Log.e(SekiroLogger.tag, message, throwable);
                }
                break;
        }
    }
}
