package cn.iinti.sekiro3.business.api.core.databind;

public class ParamNotPresentException extends RuntimeException {
    private final String attributeName;

    ParamNotPresentException(String attributeName) {
        this.attributeName = attributeName;
    }

    public String getAttributeName() {
        return attributeName;
    }
}
