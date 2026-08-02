package cn.iinti.sekiro3.business.api.invoker;

import java.io.IOException;

public interface Callback {

    void onFailure(Call call, IOException e);

    void onResponse(Call call, InvokerResponse response);
}
