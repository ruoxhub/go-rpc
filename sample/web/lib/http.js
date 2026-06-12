/**
 * HTTP 请求工具库
 * 提供 Fetch API 和 XMLHttpRequest 两种实现方式
 * 使用 IIFE 包裹以防止重复注入时声明冲突
 */

(function () {
  'use strict';

  // 防止重复注入
  if (typeof window !== 'undefined' && window.__crawler_http_loaded) {
    return;
  }

// ============ 全局配置 ============
const DEFAULT_CONFIG = {
  method: 'GET',
  timeout: 30000,
  responseType: 'text',
  credentials: 'include',
  bodyType: 'json',
  isParseResponse: true,
  params: {},
  headers: {
    'Accept': '*/*'
  },
  body: undefined
};

/**
 * 通过 bridge/background 代理请求，绕过页面 CORS 限制。
 * 仅在调用方显式设置 options.proxy=true 时启用。
 */
function proxyFetch(url, requestOptions, responseType) {
  return new Promise((resolve, reject) => {
    const requestId = 'http_proxy_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
    const timeout = Math.min(requestOptions.timeout || DEFAULT_CONFIG.timeout, 45000);
    const timeoutId = setTimeout(() => {
      window.removeEventListener('message', handler);
      reject(new Error(`Proxy request timeout after ${timeout}ms (${url})`));
    }, timeout + 1000);

    function handler(event) {
      if (event.source !== window) return;
      const msg = event.data;
      if (!msg || msg.source !== 'crawler_rpc_bridge' || msg.requestId !== requestId) return;
      clearTimeout(timeoutId);
      window.removeEventListener('message', handler);
      if (!msg.success) {
        reject(new Error(msg.error || `Proxy request failed (${url})`));
        return;
      }
      if (responseType === 'json') {
        try {
          resolve(JSON.parse(msg.data));
        } catch (error) {
          reject(new Error(`Proxy JSON parse failed (${url}): ${error.message}`));
        }
        return;
      }
      resolve(msg.data);
    }

    window.addEventListener('message', handler);
    window.postMessage({
      source: 'crawler_rpc_main',
      action: 'proxyFetch',
      requestId,
      url,
      options: requestOptions
    }, '*');
  });
}

// ============ 辅助工具函数 ============

/**
 * 构建 Headers 对象
 * @param {Record<string, string>} [customHeaders]
 * @param {Record<string, string>} [defaultHeaders]
 * @returns {Headers}
 */
function buildHeaders(customHeaders, defaultHeaders) {
  customHeaders = customHeaders || {};
  defaultHeaders = defaultHeaders || {};
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
 * @param {Record<string, any>} [params]
 * @returns {string}
 */
function buildUrlWithParams(url, params) {
  if (!params || typeof params !== 'object' || Object.keys(params).length === 0) {
    return url;
  }

  const processedParams = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined) continue;
    processedParams[key] = typeof value === 'object'
      ? JSON.stringify(value)
      : String(value);
  }

  const queryString = new URLSearchParams(processedParams).toString();
  const separator = url.includes('?') ? '&' : '?';
  return url + separator + queryString;
}

/**
 * 解析响应内容
 * @param {Response|XMLHttpRequest} source
 * @param {'text'|'json'|'eventstream'} type
 * @returns {Promise<any>}
 */
async function parseResponse(source, type) {
  if (source instanceof Response) {
    if (type === 'json') {
      const text = await source.text();
      if (!text) {
        const verify = source.headers.get('bdturing-verify');
        if (verify) {
          throw new Error(`Anti-bot verification required (${source.url})`);
        }
        throw new Error(`Empty response body (${source.url})`);
      }
      try {
        return JSON.parse(text);
      } catch (e) {
        console.warn('[HTTP] Failed to parse JSON response, falling back to text');
        return text;
      }
    }
    if (type === 'eventstream') {
      return source.text();
    }
    return source.text();
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
 * @param {string} url
 * @param {Object} opts
 * @param {string} [opts.method]
 * @param {Record<string, any>} [opts.params]
 * @param {Record<string, string>} [opts.headers]
 * @param {Object} [opts.options]
 * @returns {Promise<any>}
 */
async function _baseFetch(url, opts) {
  const method = opts.method || 'GET';
  const params = opts.params || {};
  const headers = opts.headers || {};
  const options = opts.options || {};

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

    const fetchHeaders = buildHeaders(
      headers,
      isPost
        ? { 'Content-Type': defaultContentType, ...DEFAULT_CONFIG.headers }
        : DEFAULT_CONFIG.headers
    );

    // 支持直接传递 body（用于二进制数据如 gzip 压缩内容）
    let body;
    if (options.body !== undefined) {
      body = options.body;
    } else if (isPost) {
      body = isJson ? JSON.stringify(params) : new URLSearchParams(params).toString();
    }

    // 如果 body 是二进制数据，确保 Content-Type 正确
    if ((body instanceof Uint8Array || body instanceof ArrayBuffer) && !headers['Content-Type'] && !headers['content-type']) {
      if (!headers['Content-Encoding'] && !headers['content-encoding']) {
        fetchHeaders.set('Content-Type', 'application/octet-stream');
      }
    }

    if (options.proxy === true) {
      return await proxyFetch(requestUrl, {
        method: method.toUpperCase(),
        headers: Object.fromEntries(fetchHeaders.entries()),
        body,
        timeout,
        credentials
      }, responseType);
    }

    console.log('[HTTP] Request:', {
      url: requestUrl,
      method: method.toUpperCase(),
      headers: Object.fromEntries(fetchHeaders.entries()),
      bodyType: body?.constructor?.name || typeof body,
      bodySize: body?.length || body?.byteLength
    });

    const response = await fetch(requestUrl, {
      method: method.toUpperCase(),
      credentials,
      headers: fetchHeaders,
      body,
      signal: controller.signal
    });

    console.log('[HTTP] Response:', response.status, response.statusText);

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
 * @param {string} url
 * @param {Object} opts
 * @param {string} [opts.method]
 * @param {Record<string, any>} [opts.params]
 * @param {Record<string, string>} [opts.headers]
 * @param {Object} [opts.options]
 * @returns {Promise<any>}
 */
function _baseXHR(url, opts) {
  const method = opts.method || 'GET';
  const params = opts.params || {};
  const headers = opts.headers || {};
  const options = opts.options || {};

  const config = { ...DEFAULT_CONFIG, ...options };
  const { timeout, responseType, credentials, bodyType = 'json' } = config;

  return new Promise((resolve, reject) => {
    const isPost = method.toUpperCase() === 'POST';
    const requestUrl = isPost ? url : buildUrlWithParams(url, params);

    const xhr = new XMLHttpRequest();
    xhr.withCredentials = credentials === 'include';
    xhr.timeout = timeout;

    xhr.open(method.toUpperCase(), requestUrl);

    // 设置 Headers
    const mergedHeaders = { ...DEFAULT_CONFIG.headers, ...headers };

    // 对于 POST 请求，如果用户没有指定 Content-Type，则根据 bodyType 设置默认值
    if (isPost && !headers['Content-Type'] && !headers['content-type']) {
      mergedHeaders['Content-Type'] = bodyType === 'json'
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
      if (options.body !== undefined) {
        xhr.send(options.body);
      } else if (bodyType === 'json') {
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
 * @param {string} url
 * @param {Record<string, any>} [params]
 * @param {Record<string, string>} [headers]
 * @param {Object} [options]
 * @returns {Promise<any>}
 */
function fetchPost(url, params, headers, options) {
  return _baseFetch(url, { method: 'POST', params: params || {}, headers: headers || {}, options: options || {} });
}

/**
 * Fetch GET 请求
 * @param {string} url
 * @param {Record<string, any>} [params]
 * @param {Record<string, string>} [headers]
 * @param {Object} [options]
 * @returns {Promise<any>}
 */
function fetchGet(url, params, headers, options) {
  return _baseFetch(url, { method: 'GET', params: params || {}, headers: headers || {}, options: options || {} });
}

/**
 * XMLHttpRequest POST 请求
 * @param {string} url
 * @param {Record<string, any>} [params]
 * @param {Record<string, string>} [headers]
 * @param {Object} [options]
 * @returns {Promise<any>}
 */
function XMLHttpRequestPost(url, params, headers, options) {
  return _baseXHR(url, { method: 'POST', params, headers, options });
}

/**
 * XMLHttpRequest GET 请求
 * @param {string} url
 * @param {Record<string, any>} [params]
 * @param {Record<string, string>} [headers]
 * @param {Object} [options]
 * @returns {Promise<any>}
 */
function XMLHttpRequestGet(url, params, headers, options) {
  return _baseXHR(url, { method: 'GET', params, headers, options });
}

/**
 * 通用请求方法
 * @param {string} method
 * @param {string} url
 * @param {Record<string, any>} [params]
 * @param {Record<string, string>} [headers]
 * @param {Object} [options]
 * @param {'fetch'|'xhr'} [impl]
 * @returns {Promise<any>}
 */
async function request(method, url, params, headers, options, impl) {
  impl = impl || 'fetch';
  const callArgs = { method, params, headers, options };
  return impl === 'fetch'
    ? _baseFetch(url, callArgs)
    : _baseXHR(url, callArgs);
}

// 导出到 window 对象（用于 Content Script）
if (typeof window !== 'undefined') {
  window.__crawler_http_loaded = true;
  window.fetchPost = fetchPost;
  window.fetchGet = fetchGet;
  window.XMLHttpRequestPost = XMLHttpRequestPost;
  window.XMLHttpRequestGet = XMLHttpRequestGet;
  window.request = request;
}

})();
