package cn.iinti.sekiro3.business.api.log;

public interface LogPrinter {
    void print(int level, String message, Throwable throwable);

    int INFO = 0;
    int WARNING = 1;
    int ERROR = 3;
}
