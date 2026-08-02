package cn.iinti.sekiro3.business.api.core.databind;

public class DataParseFailedException extends RuntimeException {

    private final String attributeName;

    private final Exception exception;


    public DataParseFailedException(String attributeName, Exception exception) {
        this.attributeName = attributeName;
        this.exception = exception;
    }

    public String getAttributeName() {
        return attributeName;
    }

    public Exception getException() {
        return exception;
    }
}

