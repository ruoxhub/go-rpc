/**
 * HTTP 请求工具库
 * 提供 Fetch API 和 XMLHttpRequest 两种实现方式
 *
 * 优化点：
 * 1. 统一配置管理
 * 2. 抽取底层公共逻辑 (DRY)
 * 3. 增强 XHR 的响应处理能力，使其与 Fetch 对齐
 * 4. 统一请求凭证 (credentials) 的默认行为
 * 5. 增强错误处理和调试信息
 */

(function (global) {
    'use strict';

    // ============ 全局配置 ============
    const DEFAULT_CONFIG = {
        timeout: 30000,
        responseType: 'text', // 'text' | 'json'
        credentials: 'include',
        headers: {
            'Accept': '*/*'
        }
    };

    // ============ 辅助工具函数 ============

    /**
     * 构建 Headers 对象
     * @param {Object} customHeaders
     * @param {Object} defaultHeaders
     * @returns {Headers}
     */
    function buildHeaders(customHeaders = {}, defaultHeaders = {}) {
        const headers = new Headers(defaultHeaders);
        if (customHeaders && typeof customHeaders === 'object') {
            Object.keys(customHeaders).forEach(key => {
                if (customHeaders[key] !== undefined) {
                    headers.set(key, customHeaders[key]);
                }
            });
        }
        return headers;
    }

    /**
     * 构建带查询参数的 URL
     * @param {string} url
     * @param {Object} params
     * @returns {string}
     */
    function buildUrlWithParams(url, params) {
        if (!params || typeof params !== 'object' || Object.keys(params).length === 0) {
            return url;
        }

        const processedParams = {};
        for (const [key, value] of Object.entries(params)) {
            if (value === null || value === undefined) continue;
            // 嵌套对象处理：序列化为 JSON 字符串
            processedParams[key] = typeof value === 'object' ? JSON.stringify(value) : value;
        }

        const queryString = new URLSearchParams(processedParams).toString();
        const separator = url.includes('?') ? '&' : '?';
        return url + separator + queryString;
    }

    /**
     * 解析响应内容
     * @param {Response|XMLHttpRequest} source
     * @param {string} type - 'json' | 'text'
     */
    async function parseResponse(source, type) {
        if (source instanceof Response) {
            return type === 'json' ? source.json() : source.text();
        }
        // 处理 XMLHttpRequest
        const text = source.responseText;
        if (type === 'json') {
            try {
                return JSON.parse(text);
            } catch (e) {
                console.warn('[HTTP] Failed to parse JSON response, falling back to text');
                return text;
            }
        }
        return text;
    }

    // ============ 底层实现逻辑 ============

    /**
     * Fetch 底层封装
     */
    async function _baseFetch(url, {
        method = 'GET',
        params = {},
        headers = {},
        options = {}
    }) {
        const config = { ...DEFAULT_CONFIG, ...options };
        const { timeout, responseType, credentials, bodyType = 'json', isParseResponse = true } = config;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const isPost = method.toUpperCase() === 'POST';
            const requestUrl = isPost ? url : buildUrlWithParams(url, params);

            const isJson = bodyType === 'json';
            const defaultContentType = isJson
                ? 'application/json'
                : 'application/x-www-form-urlencoded';

            const fetchHeaders = buildHeaders(headers, isPost ? {
                'Content-Type': defaultContentType,
                ...DEFAULT_CONFIG.headers
            } : DEFAULT_CONFIG.headers);

            const body = isPost
                ? (isJson ? JSON.stringify(params) : new URLSearchParams(params).toString())
                : undefined;

            const response = await fetch(requestUrl, {
                method: method.toUpperCase(),
                credentials,
                headers: fetchHeaders,
                body,
                signal: controller.signal
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status} ${response.statusText} (${url})`);
            }

            return isParseResponse ? await parseResponse(response, responseType) : response;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error(`Request timeout after ${timeout}ms (${url})`);
            }
            throw error;
        } finally {
            clearTimeout(timeoutId);
        }
    }

    /**
     * XHR 底层封装
     */
    function _baseXHR(url, {
        method = 'GET',
        params = {},
        headers = {},
        options = {}
    }) {
        const config = { ...DEFAULT_CONFIG, ...options };
        const { timeout, responseType, credentials, bodyType = 'json' } = config;

        return new Promise((resolve, reject) => {
            const isPost = method.toUpperCase() === 'POST';
            const requestUrl = isPost ? url : buildUrlWithParams(url, params);

            const xhr = new XMLHttpRequest();
            xhr.withCredentials = credentials === 'include';
            xhr.timeout = timeout;

            xhr.open(method.toUpperCase(), requestUrl);

            // 设置 Headers（POST 请求时，仅在用户未自定义 Content-Type 时设置默认值）
            const mergedHeaders = { ...DEFAULT_CONFIG.headers, ...headers };
            const isJson = bodyType === 'json';

            // 对于 POST 请求，如果用户没有指定 Content-Type，则根据 bodyType 设置默认值
            if (isPost && !headers['Content-Type'] && !headers['content-type']) {
                mergedHeaders['Content-Type'] = isJson
                    ? 'application/json'
                    : 'application/x-www-form-urlencoded';
            }

            Object.keys(mergedHeaders).forEach(key => {
                xhr.setRequestHeader(key, mergedHeaders[key]);
            });

            xhr.onload = async function () {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const result = await parseResponse(xhr, responseType);
                        resolve(result);
                    } catch (e) {
                        reject(e);
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status} ${xhr.statusText} (${url})`));
                }
            };

            xhr.onerror = () => reject(new Error(`Network error (${url})`));
            xhr.ontimeout = () => reject(new Error(`Request timeout after ${timeout}ms (${url})`));

            if (isPost) {
                if (isJson) {
                    xhr.send(JSON.stringify(params));
                } else {
                    xhr.send(new URLSearchParams(params).toString());
                }
            } else {
                xhr.send();
            }
        });
    }

    // ============ 公开 API ============

    /**
     * Fetch POST 请求
     */
    global.fetchPost = function(url, params = {}, headers = {}, options = {}) {
        return _baseFetch(url, { method: 'POST', params, headers, options });
    };

    /**
     * Fetch GET 请求
     */
    global.fetchGet = function(url, params = {}, headers = {}, options = {}) {
        return _baseFetch(url, { method: 'GET', params, headers, options });
    };

    /**
     * XMLHttpRequest POST 请求
     */
    global.XMLHttpRequestPost = function(url, params = {}, headers = {}, options = {}) {
        return _baseXHR(url, { method: 'POST', params, headers, options });
    };

    /**
     * XMLHttpRequest GET 请求
     */
    global.XMLHttpRequestGet = function(url, params = {}, headers = {}, options = {}) {
        return _baseXHR(url, { method: 'GET', params, headers, options });
    };

    /**
     * 通用请求方法
     * @param {string} method - GET/POST
     * @param {string} url
     * @param {Object} params
     * @param {Object} headers
     * @param {Object} options
     * @param {string} impl - 'fetch' | 'xhr'
     */
    global.request = async function(method, url, params = {}, headers = {}, options = {}, impl = 'fetch') {
        const callArgs = { method: method.toUpperCase(), params, headers, options };
        return impl === 'fetch' ? _baseFetch(url, callArgs) : _baseXHR(url, callArgs);
    };

})(typeof window !== 'undefined' ? window : global);
