package cn.iinti.sekiro3.business.api.interfaze;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class HandlerRegistryTest {
    @Test
    public void registersActionHandlersAndSortsActionNames() {
        HandlerRegistry registry = new HandlerRegistry();
        registry.registerRpcHandler(handler("zeta"));
        registry.registerRpcHandler(handler("alpha"));

        assertEquals("alpha", registry.actionList().get(0));
        assertEquals("zeta", registry.actionList().get(1));
    }

    @Test(expected = IllegalStateException.class)
    public void rejectsDuplicateActions() {
        HandlerRegistry registry = new HandlerRegistry();
        registry.registerRpcHandler(handler("echo"));
        registry.registerRpcHandler(handler("echo"));
    }

    private static ActionHandler handler(final String action) {
        return new ActionHandler() {
            @Override
            public String action() {
                return action;
            }

            @Override
            public void handleRequest(RpcRequest request, RpcResponse response) {
            }
        };
    }
}
