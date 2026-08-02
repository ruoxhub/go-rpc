package cn.iinti.sekiro3.business.api.core;

import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.core.databind.DataParseFailedException;
import cn.iinti.sekiro3.business.api.core.databind.ParamNotPresentException;
import cn.iinti.sekiro3.business.api.interfaze.*;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.util.Constants;
import cn.iinti.sekiro3.business.api.util.TextUtil;

public class RequestTaskRunner implements HandlerThreadPool.TaskRunner {
    private final SekiroRequest sekiroRequest;
    private final SekiroResponse sekiroResponse;

    private final SekiroLogger sekiroLogger;


    RequestTaskRunner(SekiroRequest sekiroRequest, SekiroResponse sekiroResponse) {
        this.sekiroRequest = sekiroRequest;
        this.sekiroResponse = sekiroResponse;
        this.sekiroLogger = sekiroRequest.getSekiroLogger();
    }

    private void executeSekiroTask() {
        SekiroClient sekiroClient = sekiroRequest.getSekiroClient();
        if (sekiroClient.isDestroyed()) {
            sekiroResponse.failed(CommonRes.statusSekiroDestroy, "sekiro client destroying");
            return;
        }

        try {
            // 这一步一般涉及到json的解析，高并发场景可能消耗cpu，所以从这里开始放到线程池处理
            sekiroRequest.doInit();
            sekiroResponse.afterSekiroRequestInit();
        } catch (Exception e) {
            sekiroResponse.failed(CommonRes.statusBadRequest, e);
            return;
        }

        String action = sekiroRequest.getString(Constants.REVERSED_WORDS.ACTION);
        if (TextUtil.isBlank(action)) {
            sekiroResponse.failed("the param:{" + Constants.REVERSED_WORDS.ACTION + "} not present");
            return;
        }

        action = action.trim();

        HandlerRegistry handlerRegistry = new HandlerRegistry(sekiroRequest);
        sekiroClient.getSekiroRequestInitializer().onSekiroRequest(sekiroRequest, handlerRegistry);

        RequestHandler requestHandler;
        try {
            requestHandler = handlerRegistry.fetchRequestHandler();
        } catch (ParamNotPresentException paramNotPresentException) {
            sekiroResponse.failed("the param: {" + paramNotPresentException.getAttributeName() + "} not presented");
            return;
        } catch (DataParseFailedException dataParseFailedException) {
            sekiroResponse.failed(CommonRes.statusBadRequest, dataParseFailedException);
            return;
        }
        if (requestHandler == null) {
            if (action.equals(Constants.REVERSED_WORDS.ACTION_LIST)) {
                sekiroResponse.success(handlerRegistry.actionList());
            } else if (action.equals(Constants.REVERSED_WORDS.SYSTEM_MSG_TOO_MANY_TIMEOUT)) {
                sekiroLogger.warn("too many timeout task, please increase endpoint size or increase thread size config!!");
                // todo notify listener
            } else {
                sekiroResponse.failed("unknown action: " + action);
            }
            return;
        }

        requestHandler.handleRequest(sekiroRequest, sekiroResponse);
    }

    @Override
    public void run() {
        try {
            executeSekiroTask();
        } catch (Throwable e) {
            // 使用xposed的时候，有很多反射错误，
            // 反射错误属于error级别，exception包不住
            // 在Android中，这种错误会直接导致app crash
            sekiroLogger.error("error to execute Sekiro task", e);
            sekiroResponse.failed(CommonRes.statusBadRequest, e);
        }
    }
}

