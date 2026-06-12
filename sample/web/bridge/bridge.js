/**
 * Bridge Script - 运行在 ISOLATED 世界
 *
 * 作为 MAIN 世界脚本和浏览器扩展 API 之间的桥梁
 * 通过 window.postMessage 接收请求，使用 chrome.storage 处理，然后返回结果
 * 支持 Chrome 和 Firefox (Manifest V3)
 */

(function () {
  'use strict';

  // 防止重复注入
  if (window.__crawler_bridge_loaded) {
    return;
  }
  window.__crawler_bridge_loaded = true;

const STORAGE_KEY = 'crawler_rpc_config';
const MESSAGE_SOURCE = 'crawler_rpc_bridge';

console.log('[Bridge] Initializing config bridge...');

/**
 * 从浏览器 Storage 获取配置
 * @returns {Promise<Object>}
 */
async function getConfig() {
  return new Promise((resolve) => {
    if (typeof chrome === 'undefined' || !chrome.storage) {
      console.warn('[Bridge] Browser Storage API not available');
      resolve({});
      return;
    }

    chrome.storage.local.get([STORAGE_KEY], (result) => {
      var lastError = chrome.runtime ? chrome.runtime.lastError : null;
      if (lastError) {
        console.error('[Bridge] Get config error:', lastError);
        resolve({});
      } else {
        const config = result[STORAGE_KEY] || {};
        console.log('[Bridge] Got config:', config);
        resolve(config);
      }
    });
  });
}

/**
 * 保存配置到浏览器 Storage
 * @param {Object} config
 * @returns {Promise<void>}
 */
async function saveConfig(config) {
  return new Promise((resolve, reject) => {
    if (typeof chrome === 'undefined' || !chrome.storage) {
      reject(new Error('Browser Storage API not available'));
      return;
    }

    chrome.storage.local.set({ [STORAGE_KEY]: config }, () => {
      var lastError = chrome.runtime ? chrome.runtime.lastError : null;
      if (lastError) {
        console.error('[Bridge] Save config error:', lastError);
        reject(lastError);
      } else {
        console.log('[Bridge] Config saved:', config);
        resolve();
      }
    });
  });
}

/**
 * 代理 fetch 请求（通过 background script）
 * @param {string} url
 * @param {RequestInit & {timeout?: number}} [options={}]
 * @returns {Promise<{success: boolean, data?: string, error?: string}>}
 */
async function proxyFetch(url, options = {}) {
  return new Promise((resolve) => {
    if (typeof chrome === 'undefined' || !chrome.runtime) {
      resolve({ success: false, error: 'Chrome Runtime API not available' });
      return;
    }

    const timeout = Math.min(options.timeout || 10000, 45000);

    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error(`Request timeout after ${timeout}ms`)), timeout);
    });

    const fetchPromise = chrome.runtime.sendMessage({
      action: 'proxyFetch',
      url,
      options
    });

    Promise.race([fetchPromise, timeoutPromise])
      .then((result) => {
        if (result && result.success) {
          resolve({ success: true, data: result.data });
        } else {
          resolve({
            success: false,
            error: result ? result.error : 'Unknown error'
          });
        }
      })
      .catch((err) => {
        console.error('[Bridge] proxyFetch error:', err);
        resolve({ success: false, error: err.message || 'proxyFetch failed' });
      });
  });
}

/**
 * 发送消息到 background script（浏览器控制操作）
 * @param {string} action
 * @param {Object} data
 * @returns {Promise<any>}
 */
async function sendToBackground(action, data) {
  return new Promise((resolve, reject) => {
    if (typeof chrome === 'undefined' || !chrome.runtime) {
      reject(new Error('Chrome Runtime API not available'));
      return;
    }

    const timeout = 30000;
    const timeoutId = setTimeout(() => {
      reject(new Error(`Background action ${action} timeout after ${timeout}ms`));
    }, timeout);

    chrome.runtime.sendMessage({ action, ...data })
      .then((result) => {
        clearTimeout(timeoutId);
        if (result && result.success) {
          resolve(result);
        } else {
          reject(new Error(result?.error || `Background action ${action} failed`));
        }
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        reject(err);
      });
  });
}

/**
 * 监听来自 MAIN 世界的消息
 */
window.addEventListener('message', async (event) => {
  if (event.source !== window) return;

  const data = event.data;

  if (!data || data.source !== 'crawler_rpc_main') return;

  console.log('[Bridge] Received message:', data);

  try {
    let response = { source: MESSAGE_SOURCE, requestId: data.requestId };

    if (data.action === 'wsConnect') {
      const port = ensureWsPort(data.connId);
      port.postMessage({ action: 'connect', url: data.url });
      response.success = true;
    } else if (data.action === 'wsSend') {
      const port = wsPorts.get(data.connId);
      if (port) {
        port.postMessage({ action: 'send', data: data.data });
        response.success = true;
      } else {
        response.success = false;
        response.error = 'WebSocket port not connected';
      }
    } else if (data.action === 'wsDisconnect') {
      const port = wsPorts.get(data.connId);
      if (port) {
        try { port.postMessage({ action: 'disconnect' }); } catch (e) {}
        try { port.disconnect(); } catch (e) {}
        wsPorts.delete(data.connId);
      }
      response.success = true;
    } else if (data.action === 'getConfig') {
      const config = await getConfig();
      response.success = true;
      response.config = config;
    } else if (data.action === 'saveConfig') {
      await saveConfig(data.config);
      response.success = true;
    } else if (data.action === 'proxyFetch') {
      const result = await proxyFetch(data.url, data.options || {});
      if (result.success) {
        response.success = true;
        response.data = result.data;
      } else {
        response.success = false;
        response.error = result.error;
      }
    } else if (data.action === 'navigate') {
      try {
        const result = await sendToBackground('navigate', data);
        response.success = true;
        response.tabId = result.tabId;
        response.title = result.title;
        response.url = result.url;
      } catch (err) {
        response.success = false;
        response.error = err instanceof Error ? err.message : 'Navigate failed';
      }
    } else if (data.action === 'getDnrRules') {
      try {
        const result = await sendToBackground('getDnrRules', data);
        response.success = true;
        response.rules = result.rules;
      } catch (err) {
        response.success = false;
        response.error = err instanceof Error ? err.message : 'getDnrRules failed';
      }
    } else if (data.action === 'getCookies') {
      try {
        const result = await sendToBackground('getCookies', data);
        response.success = true;
        response.cookies = result.cookies;
      } catch (err) {
        response.success = false;
        response.error = err instanceof Error ? err.message : 'GetCookies failed';
      }
    } else if (data.action === 'tabs') {
      try {
        const result = await sendToBackground('tabs', data);
        response.success = true;
        response.tabs = result.tabs;
        response.tabId = result.tabId;
      } catch (err) {
        response.success = false;
        response.error = err instanceof Error ? err.message : 'Tabs action failed';
      }
    } else if (data.action === 'screenshot') {
      try {
        const result = await sendToBackground('screenshot', data);
        response.success = true;
        response.data = result.data;
      } catch (err) {
        response.success = false;
        response.error = err instanceof Error ? err.message : 'Screenshot failed';
      }
    } else {
      response.success = false;
      response.error = `Unknown action: ${data.action}`;
    }

    window.postMessage(response, '*');
  } catch (error) {
    console.error('[Bridge] Error handling message:', error);
    window.postMessage({
      source: MESSAGE_SOURCE,
      requestId: data.requestId,
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error'
    }, '*');
  }
});

/**
 * 监听 Chrome Storage 变更（来自 popup 保存的配置）
 * 当配置变更时，广播通知到 MAIN 世界
 */
if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged && chrome.storage.onChanged.addListener) {
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== 'local') return;

    if (changes[STORAGE_KEY]) {
      const newConfig = changes[STORAGE_KEY].newValue || {};
      console.log('[Bridge] Config changed, broadcasting update:', newConfig);

      window.postMessage({
        source: MESSAGE_SOURCE,
        action: 'configUpdated',
        config: newConfig
      }, '*');
    }
  });
}

/** WebSocket Port 连接（转发到 Background Service Worker）
 *  按 connId 维护独立 port：每个 BackgroundWebSocket 实例对应一条 chrome.runtime.Port，
 *  从而让 background 给每个 connId 绑定独立的真实 ws，避免同一标签页内多 group 互踩。
 */
const wsPorts = new Map();

function ensureWsPort(connId) {
  if (!connId) {
    console.warn('[Bridge] ensureWsPort called without connId; refusing to create port');
    return null;
  }
  let port = wsPorts.get(connId);
  if (port) return port;

  port = chrome.runtime.connect({ name: 'ws-bridge' });

  port.onMessage.addListener((msg) => {
    // 将 Background 的 WebSocket 事件转发给 MAIN 世界，必须带上 connId 以便实例侧过滤
    window.postMessage({
      source: MESSAGE_SOURCE,
      action: 'wsEvent',
      connId: connId,
      eventType: msg.type,
      data: msg.data,
      code: msg.code,
      reason: msg.reason,
      url: msg.url
    }, '*');
  });

  port.onDisconnect.addListener(() => {
    console.log('[Bridge] WS port disconnected, connId:', connId);
    // 广播 close 事件到 MAIN world，避免 BackgroundWebSocket 因收不到 close 事件而卡在假连接状态
    window.postMessage({
      source: MESSAGE_SOURCE,
      action: 'wsEvent',
      connId: connId,
      eventType: 'close',
      code: 1001,
      reason: 'Bridge port disconnected'
    }, '*');
    wsPorts.delete(connId);
  });

  wsPorts.set(connId, port);
  return port;
}

// 通知 MAIN 世界桥接已准备就绪
window.postMessage({
  source: MESSAGE_SOURCE,
  action: 'bridgeReady'
}, '*');

console.log('[Bridge] Config bridge initialized');

})();
