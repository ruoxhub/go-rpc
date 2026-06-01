/**
 * qwenai 工具函数
 * 包括设备指纹生成、Headers 构建、Cookie 生成、Baxia 签名获取等
 */
(function() {
    window.__qwenai = window.__qwenai || {};

    // ===== 缓存变量 =====
    var cachedTicket = null;
    var cachedDeviceId = null;

    /**
     * 清除缓存（需要在 Cookie 变更或设备 ID 重置时调用）
     */
    window.__qwenai.clearCache = function() {
        cachedTicket = null;
        cachedDeviceId = null;
    };

    /**
     * 生成随机字符串
     * @param {number} length
     * @param {string} [charset]
     * @returns {string}
     */
    function randomString(length, charset) {
        charset = charset || 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        var result = '';
        for (var i = 0; i < length; i++) {
            result += charset[Math.floor(Math.random() * charset.length)];
        }
        return result;
    }

    /**
     * 生成 UUID (版本 4)
     * @returns {string}
     */
    function generateUUID() {
        var bytes = new Uint8Array(16);
        crypto.getRandomValues(bytes);

        // 设置版本号为 4
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        // 设置变体为 RFC4122
        bytes[8] = (bytes[8] & 0x3f) | 0x80;

        var hex = Array.from(bytes).map(function(b) { return b.toString(16).padStart(2, '0'); }).join('');
        return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' + hex.slice(16, 20) + '-' + hex.slice(20);
    }

    /**
     * Base64 编码（浏览器兼容）
     * @param {string} str
     * @returns {string}
     */
    function base64Encode(str) {
        var bytes = new Uint8Array(str.length);
        for (var i = 0; i < str.length; i++) {
            bytes[i] = str.charCodeAt(i);
        }
        var binary = '';
        for (var j = 0; j < bytes.byteLength; j++) {
            binary += String.fromCharCode(bytes[j]);
        }
        return btoa(binary);
    }

    /**
     * 简单的字符串 hash 函数 (生成 32 位 hex)
     * @param {string} str
     * @returns {string}
     */
    function simpleHash(str) {
        var hash = 0;
        var result = new Array(8).fill(0);

        for (var i = 0; i < str.length; i++) {
            var char = str.charCodeAt(i);
            result[i % 8] ^= char;
            result[i % 8] = (result[i % 8] << 5) | (result[i % 8] >> 27);
            result[i % 8] >>>= 0;
        }

        var timestamp = Date.now().toString(16).padStart(16, '0');
        for (var j = 0; j < 8; j++) {
            result[j] ^= parseInt(timestamp.slice(j * 2, j * 2 + 2) || '0', 16);
        }

        return result.map(function(n) { return n.toString(16).padStart(8, '0'); }).join('');
    }

    /**
     * 生成基础设备指纹
     * @returns {string}
     */
    function generateBaseFingerprint() {
        var features = [
            Date.now().toString(36),
            Math.random().toString(36).slice(2),
            navigator.userAgent,
            navigator.language,
            screen.width + 'x' + screen.height,
            (screen.colorDepth && screen.colorDepth.toString()) || '24',
            new Date().getTimezoneOffset().toString(),
            (navigator.hardwareConcurrency && navigator.hardwareConcurrency.toString()) || '8',
            (navigator.deviceMemory && navigator.deviceMemory.toString()) || '16',
        ].join('|');

        return simpleHash(features);
    }

    /**
     * 生成设备 ID
     * @param {string} fingerprint
     * @returns {string}
     */
    function generateDeviceId(fingerprint) {
        var randomPart = randomString(16);
        var deviceIdData = fingerprint + ':' + randomPart + ':' + Date.now();

        var result = base64Encode(deviceIdData)
            .replace(/\+/g, '#')
            .replace(/\//g, '@')
            .replace(/=/g, '');

        return result;
    }

    /**
     * 生成完整的设备指纹信息
     * @returns {{ deviceFingerprint: string, deviceId: string, umV1: string, ckV1: string, tfstk: string, xsrfToken: string }}
     */
    function generateFullFingerprint() {
        var deviceFingerprint = generateBaseFingerprint();
        var deviceId = generateDeviceId(deviceFingerprint);

        var userIdData = {
            ud: randomString(64),
            ep: Date.now() + 7 * 24 * 60 * 60 * 1000,
        };
        var umV1 = base64Encode(JSON.stringify(userIdData));

        var deviceData = {
            deviceId: deviceId,
            deviceFingerprint: deviceFingerprint,
        };
        var ckV1 = base64Encode(JSON.stringify(deviceData));

        var randomPart = randomString(32);
        var deviceIdHash = simpleHash(deviceId);
        var tfstkRaw = randomPart + ':' + Date.now() + ':' + deviceIdHash;
        var tfstk = base64Encode(tfstkRaw)
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=/g, '');

        var xsrfToken = generateUUID();

        return {
            deviceFingerprint: deviceFingerprint,
            deviceId: deviceId,
            umV1: umV1,
            ckV1: ckV1,
            tfstk: tfstk,
            xsrfToken: xsrfToken,
        };
    }

    /**
     * 生成 Cookie 字符串
     * @param {string} ticket
     * @param {Object} fp - generateFullFingerprint 返回的指纹对象
     * @returns {string}
     */
    window.__qwenai.generateCookie = function(ticket, fp) {
        if (!ticket) {
            console.error('[qwenai] generateCookie: Ticket is empty');
            return '';
        }

        var isLongTicket = ticket.length > 100;
        var ticketKey = isLongTicket ? 'login_aliyunid_ticket' : 'tongyi_sso_ticket';

        return [
            ticketKey + '=' + ticket,
            'aliyun_choice=intl',
            '_samesite_flag_=true',
            't=' + generateUUID().replace(/-/g, ''),
            'XSRF-TOKEN=' + fp.xsrfToken,
            '_qk_bx_um_v1=' + fp.umV1,
            '_qk_bx_ck_v1=' + fp.ckV1,
            'tfstk=' + fp.tfstk,
        ].join('; ');
    };

    /**
     * 获取 Baxia 安全 Token（浏览器环境）
     * @returns {Promise<{ etToken?: string, fyToken?: string, uidToken?: string, error?: string }>}
     */
    window.__qwenai.getBaxiaTokens = async function() {
        var baxia = window.__baxia__;

        if (!baxia) {
            return { error: 'Baxia module not initialized' };
        }

        try {
            var bxua = (baxia.getFYModule && baxia.getFYModule.fyObj && baxia.getFYModule.fyObj.getFYToken && baxia.getFYModule.fyObj.getFYToken()) || (baxia.getFYModule && baxia.getFYModule.getFYToken && baxia.getFYModule.getFYToken())
            return bxua;
        } catch (error) {
            console.error('[qwenai] Failed to get Baxia tokens:', error);
            return { error: error.message };
        }
    };

    /**
     * 获取客户端签名 Token（从 localStorage）
     * @returns {Object|null}
     */
    window.__qwenai.getClientTokens = function() {
        try {
            var storageData = localStorage.getItem('_qk_busc_info_v1qwen_web');
            if (!storageData) {
                return null;
            }

            var data = JSON.parse(storageData);
            var sceneData = (data.scene_list && data.scene_list.qwen_chat) || (data.scene_list && data.scene_list.qwen_web);

            if (!sceneData) {
                return null;
            }

            return {
                dvidn: sceneData['eo-clt-dvidn'],
                actkn: sceneData['eo-clt-actkn'],
                actknDl: sceneData['eo-clt-actkn-dl'],
                bacsft: sceneData['eo-clt-bacsft'],
                snver: sceneData['eo-clt-snver'],
                expireTime: sceneData.expireTime,
            };
        } catch (error) {
            console.error('[qwenai] Failed to get client tokens:', error);
            return null;
        }
    };

    /**
     * 生成 nonce（8 位随机字符串）
     * @param {number} [length=8]
     * @returns {string}
     */
    window.__qwenai.generateNonce = function(length) {
        length = length || 8;
        var chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
        var result = '';
        for (var i = 0; i < length; i++) {
            result += chars.charAt(Math.floor(Math.random() * chars.length));
        }
        return result;
    };

    /**
     * 获取设备 ID（从 Cookie 或生成）
     * @returns {string}
     */
    window.__qwenai.getDeviceId = function() {
        if (cachedDeviceId !== null) {
            return cachedDeviceId;
        }

        var stored = localStorage.getItem('qianwen-uniq-id');
        if (stored) {
            cachedDeviceId = stored;
            return stored;
        }

        var cookieMatch = document.cookie.match(/b-user-id=([^;]+)/);
        if (cookieMatch && cookieMatch[1]) {
            cachedDeviceId = cookieMatch[1];
            return cookieMatch[1];
        }

        var newDeviceId = generateUUID();
        localStorage.setItem('qian_device_id', newDeviceId);
        cachedDeviceId = newDeviceId;
        return newDeviceId;
    };

    /**
     * 构建 API v2 请求 Headers（使用 Baxia 签名）
     * @returns {Promise<Object>}
     */
    window.__qwenai.buildHeadersV2 = async function() {

        var headers = {
            'Accept': 'application/json, text/event-stream, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Content-Type': 'application/json',
            'Origin': 'https://chat.qwen.ai',
            'Referer': 'https://chat.qwen.ai/',
        };
        headers['Bx-Ua'] = await window.__qwenai.getBaxiaTokens();
        headers['Bx-Umidtoken'] = "default_not_value";
        headers['bx-v'] = "2.5.36";
        return headers;
    };



    /**
     * 从 Cookie 中获取 ticket
     * @returns {string|null}
     */
    window.__qwenai.getTicketFromCookie = function() {
        if (cachedTicket !== null) {
            return cachedTicket;
        }

        var cookies = document.cookie.split('; ');
        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].split('=');
            var name = parts[0];
            var value = parts.slice(1).join('=');
            if (name === 'login_aliyunid_ticket') {
                cachedTicket = value;
                return value;
            }
            if (name === 'tongyi_sso_ticket') {
                cachedTicket = value;
                return value;
            }
        }

        cachedTicket = null;
        return null;
    };

    // 暴露内部工具函数供 api.js 使用
    window.__qwenai._generateFullFingerprint = generateFullFingerprint;
    window.__qwenai._generateUUID = generateUUID;
    window.__qwenai._randomString = randomString;
})();
