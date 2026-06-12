/**
 * Bilibili 数据采集入口
 * 域名检查 + BaseClient 注册
 */
(function () {
    'use strict';

    // 域名检查
    var hostname = window.location.hostname;
    if (!hostname.includes('space.bilibili.com') && !hostname.includes('www.bilibili.com')) {
        return;
    }

    // 创建客户端
    BaseClient.create({
        platform: 'bilibili',
        hostnames: 'bilibili.com',
        logPrefix: 'Bilibili Extractor',
        endpoints: window.__bilibili.Endpoints,

        // Action 配置 - 声明式定义，自动处理参数提取和错误处理
        actions: {
            getUserInfo: createAction(window.__bilibili.getUserInfo),
            getContent: createAction(window.__bilibili.getContent),
            getComment: createAction(window.__bilibili.getComment),
            getVideoSubtitle: createAction(window.__bilibili.getVideoSubtitle),
            getVideoInfo: createAction(window.__bilibili.getVideoInfo),
            getFeedRcmd: createAction(window.__bilibili.getFeedRcmd)
        }
    });
})();
