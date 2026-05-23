/**
 * qwenai API 端点定义
 */
(function() {
    window.__qwenai = window.__qwenai || {};

    window.__qwenai.Endpoints = {

        // chat.qwen.ai 接口
        models: "https://chat.qwen.ai/api/models",

        // ===== API V2 (chat2.qianwen.com) - 使用 Baxia 签名 =====
        // V2 对话补全
        chatV2: "https://chat2.qianwen.com/api/v2/chat",
        // V2 会话列表
        sessionListV2: "https://chat2-api.qianwen.com/api/v2/session/page/list",
        // V2 创建会话
        sessionCreateV2: "https://chat2-api.qianwen.com/api/v2/session/create",
        // V2 更新会话
        sessionUpdateV2: "https://chat2-api.qianwen.com/api/v2/session/update",
        // V2 生成图片
        imagesV2: "https://chat2-api.qianwen.com/api/v2/images/generate",
        // V2 Token 检查
        tokenCheckV2: "https://chat2-api.qianwen.com/v1/token/check",
        // V2 上传 Token
        uploadTokenV2: "https://chat2-api.qianwen.com/api/v2/upload/token",
        // V2 用户信息
        userInfo: "https://api.qianwen.com/growth/user/benefit/user/member/info",
    };
})();
