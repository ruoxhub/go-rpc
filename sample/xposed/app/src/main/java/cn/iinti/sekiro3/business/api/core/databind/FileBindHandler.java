package cn.iinti.sekiro3.business.api.core.databind;

import cn.iinti.sekiro3.business.api.interfaze.AutoBind;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import com.alibaba.fastjson.JSONObject;
import com.alibaba.fastjson.parser.ParserConfig;
import com.alibaba.fastjson.util.TypeUtils;
import lombok.Getter;

import java.lang.reflect.Field;

class FileBindHandler {
    private String attributeName = null;
    private final Object defaultValue;
    private boolean notNull;
    @Getter
    private final Field targetFiled;

    FileBindHandler(Object defaultValue, Field targetFiled, AutoBind autoBind) {
        this.defaultValue = defaultValue;
        this.targetFiled = targetFiled;
        if (autoBind != null) {
            notNull = autoBind.require();
            attributeName = autoBind.value();
        }
        if (attributeName == null || attributeName.trim().isEmpty()) {
            attributeName = targetFiled.getName();
        }
    }

    Object transfer(SekiroRequest invokeRequest) {
        Object value = transferInternal(invokeRequest);
        if (notNull && value == null) {
            throw new ParamNotPresentException(attributeName);
        }
        return value;
    }

    private Object transferInternal(SekiroRequest invokeRequest) {
        if (targetFiled.getType() == String.class) {
            String ret = invokeRequest.getString(attributeName);
            if (ret == null) {
                if (defaultValue == null) {
                    return null;
                }
                ret = defaultValue.toString();
            }
            return ret;
        }
        JSONObject jsonModel = invokeRequest.getJsonModel();

        Object fieldValue = jsonModel.get(attributeName);
        if (fieldValue == null) {
            return defaultValue;
        }
        return TypeUtils.cast(fieldValue, targetFiled.getGenericType(), ParserConfig.getGlobalInstance());
    }
}
