/**
 * qwenai 模块入口
 * 支持 V1 和 V2 两个 API 版本
 */
(function() {
    'use strict';

    if (!window.location.hostname.includes('qianwen.com') && !window.location.hostname.includes('qwen.ai')) {
        return;
    }

    var { Endpoints } = window.__qwenai;
    var {
        // V2 API
        chatV2,
        chatStreamV2,
        generateImagesV2,
        checkTokenLiveV2,
        deleteSessionV2,
        getSessionListV2,
        getTicket,
        getModel,
    } = window.__qwenai;

    console.log('Qwenai Extractor: Initializing...');

    BaseClient.create({
        platform: 'qwenai',
        hostnames: ['qianwen.com', 'qwen.ai'],
        logPrefix: 'qwenai Extractor',
        endpoints: Endpoints,

        // Action 配置 - 声明式定义，自动处理参数提取和错误处理
        actions: {
            // ===== V2 API Actions (使用 Baxia 签名) =====
            chatV2: createAction(chatV2),
            chatStreamV2: createAction(chatStreamV2),
            imagesV2: createAction(generateImagesV2),
            tokenCheckV2: createAction(checkTokenLiveV2),
            sessionDeleteV2: createAction(deleteSessionV2),
            sessionListV2: createAction(getSessionListV2),

            // ===== 工具 Actions =====
            getTicket: createAction(getTicket),
            getModel: createAction(getModel),
        }
    });
})();
