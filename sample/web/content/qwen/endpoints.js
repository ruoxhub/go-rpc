/**
 * qwenai API 端点定义
 */
(function() {
    window.__qwenai = window.__qwenai || {};

    window.__qwenai.Endpoints = {

        // chat.qwen.ai 接口
        models: "https://chat.qwen.ai/api/models",
        // 新建对话（chat.qwen.ai 站点）
        chatsNew: "https://chat.qwen.ai/api/v2/chats/new",
        // 流式对话（chat.qwen.ai 站点）
        chatsChat: "https://chat.qwen.ai/api/v2/chat/completions",
    };
})();
