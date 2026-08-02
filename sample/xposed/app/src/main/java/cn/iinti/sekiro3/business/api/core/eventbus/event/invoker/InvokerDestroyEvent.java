package cn.iinti.sekiro3.business.api.core.eventbus.event.invoker;

import cn.iinti.sekiro3.business.api.core.eventbus.support.AutoEvent;
import cn.iinti.sekiro3.business.api.invoker.InvokerInstance;

public interface InvokerDestroyEvent extends InvokerEvent {
    @AutoEvent
    void onInvokerDestroy(InvokerInstance invokerInstance);
}
