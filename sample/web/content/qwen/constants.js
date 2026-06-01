/**
 * qwenai 常量定义
 */
(function() {
    window.__qwenai = window.__qwenai || {};

    // 模型名称
    var MODEL_NAME = 'qwen';

    // 最大重试次数
    var MAX_RETRY_COUNT = 3;

    // 重试延迟 (ms)
    var RETRY_DELAY = 5000;

    // 请求超时时间 (ms)
    var TIMEOUT = 120000;

    // 文件最大大小 (100MB)
    var FILE_MAX_SIZE = 100 * 1024 * 1024;

    // 支持的图像格式
    var SUPPORTED_IMAGE_TYPES = [
        'image/jpeg',
        'image/jpg',
        'image/tiff',
        'image/png',
        'image/bmp',
        'image/gif',
        'image/svg+xml',
        'image/webp',
        'image/ico',
        'image/heic',
        'image/heif',
        'image/x-icon',
        'image/vnd.microsoft.icon',
        'image/x-png'
    ];

    // 请求选项配置
    var Options = {
        timeout: TIMEOUT,
        credentials: 'include',
        headers: {
            'Accept': '*/*',
        },
        bodyType: 'json'
    };

    window.__qwenai.MODEL_NAME = MODEL_NAME;
    window.__qwenai.MAX_RETRY_COUNT = MAX_RETRY_COUNT;
    window.__qwenai.RETRY_DELAY = RETRY_DELAY;
    window.__qwenai.TIMEOUT = TIMEOUT;
    window.__qwenai.FILE_MAX_SIZE = FILE_MAX_SIZE;
    window.__qwenai.SUPPORTED_IMAGE_TYPES = SUPPORTED_IMAGE_TYPES;
    window.__qwenai.Options = Options;
})();
