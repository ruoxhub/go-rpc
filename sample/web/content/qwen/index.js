/**
 * qwenai 模块入口
 * 支持 V1 和 V2 两个 API 版本
 */
(function() {
    'use strict';

    if (!window.location.hostname.includes('chat.qwen.ai')) {
        return;
    }
    var { Endpoints } = window.__qwenai;
    var {
        // V2 API
        chatCompletions,
        getModel,
        createChat,
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
            // chatCompletions 走流式：method 返回原始 Response，BaseClient 用 reader 逐 chunk 推送 invoke_stream 帧
            chatCompletions: createStream(chatCompletions),
            getModel: createAction(getModel),
            createChat: createAction(createChat),
        }
    });
})();
