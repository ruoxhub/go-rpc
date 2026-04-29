// Background script for XHS Post Extractor

const STORAGE_KEY = 'crawler_rpc_config';

let wsConnection = null;

let hasCapturedXClientData = false;
let hasCapturedXBrowserValidation = false;

// ── APM 上报拦截（zhipin.com DEVICE_ACTION 反检测） ──
// 拦截发往 apm-fe.zhipin.com 的 DEVICE_ACTION 上报请求，
// 阻止服务端获知本地 WebSocket 代理和 Chrome 扩展检测结果。
(function installApmBlockRule() {
  var dnr = (typeof chrome !== 'undefined') && chrome.declarativeNetRequest;
  if (!dnr) return;

  // 细粒度功能检测：确保动态规则 API 可用
  if (typeof dnr.addDynamicRules !== 'function' || typeof dnr.getDynamicRules !== 'function') {
    console.warn('[Background] declarativeNetRequest dynamic rules API not available in this Chrome version');
    return;
  }

  var RULE_ID_ZHIPIN_APM = 1;

  try {
    dnr.getDynamicRules().then(function (existingRules) {
      var hasRule = existingRules.some(function (r) { return r.id === RULE_ID_ZHIPIN_APM; });
      if (hasRule) return; // 规则已存在，不重复添加

      return dnr.addDynamicRules([{
        id: RULE_ID_ZHIPIN_APM,
        priority: 1,
        action: {
          type: 'block'
        },
        condition: {
          urlFilter: '||apm-fe.zhipin.com/wapi/zpApm/actionLog',
          resourceTypes: ['xmlhttprequest']
        }
      }]);
    }).then(function () {
      console.log('[Background] APM DEVICE_ACTION block rule installed for zhipin.com');
    }).catch(function (e) {
      console.warn('[Background] Failed to install APM block rule:', e.message || e);
    });
  } catch (e) {
    console.warn('[Background] declarativeNetRequest error:', e);
  }
})();

chrome.webRequest.onBeforeSendHeaders.addListener(
    async (details) => {
        for (let header of details.requestHeaders) {
            if (header.name.toLowerCase() === 'x-client-data') {
                // 只截获一次
                if (hasCapturedXClientData) {
                    continue;
                }
                hasCapturedXClientData = true;

                const newValue = header.value;

                // 将变量注入到网页的真实 window 对象中 (MAIN world)
                chrome.scripting.executeScript({
                    target: { tabId: details.tabId },
                    world: "MAIN", // 关键：注入到网页的主环境，而非沙箱
                    func: (val) => {
                        window.x_client_data = val;
                        console.log("YouTube x-client-data 已更新至 window.x_client_data");
                    },
                    args: [newValue]
                }).catch(err => console.debug("注入失败（可能是非网页页面）:", err));
                continue; // 继续检查其他头部
            }
            else if (header.name.toLowerCase() === 'x-browser-validation') {
                // 只截获一次
                if (hasCapturedXBrowserValidation) {
                    continue;
                }
                hasCapturedXBrowserValidation = true;

                const newValue = header.value;

                // 将变量注入到网页的真实 window 对象中 (MAIN world)
                chrome.scripting.executeScript({
                    target: { tabId: details.tabId },
                    world: "MAIN", // 关键：注入到网页的主环境，而非沙箱
                    func: (val) => {
                        window.x_browser_validation = val;
                        console.log("YouTube x-browser-validation 已更新至 window.x_browser_validation");
                    },
                    args: [newValue]
                }).catch(err => console.debug("注入失败（可能是非网页页面）:", err));
                continue; // 继续检查其他头部
            }
        }
    },
    { urls: ["*://*.youtube.com/*"] },
    ["requestHeaders", "extraHeaders"]
);

// Listen for messages from content script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    // 使用安全的响应函数，防止在通道关闭后尝试发送响应
    let isResponseSent = false;
    const safeSendResponse = (response) => {
        if (isResponseSent) {
            console.log('[Background] Response already sent, ignoring duplicate');
            return;
        }
        try {
            sendResponse(response);
            isResponseSent = true;
        } catch (error) {
            // 消息通道可能已关闭（页面被刷新或关闭）
            console.log('[Background] Could not send response (channel may be closed):', error.message);
        }
    };

    if (request.action === 'log') {
        console.log('Content Script:', request.message);
        safeSendResponse({ success: true });
        return false; // 同步响应，不需要保持通道打开
    }
    else if (request.action === 'getConfig') {
        // 获取存储的配置
        chrome.storage.local.get([STORAGE_KEY], (result) => {
            if (chrome.runtime.lastError) {
                console.error('[Background] Get config error:', chrome.runtime.lastError);
                safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
            } else {
                const config = result[STORAGE_KEY] || {};
                console.log('[Background] Getting config:', config);
                safeSendResponse({ success: true, config });
            }
        });
        return true; // 保持消息通道打开以进行异步响应
    }
    else if (request.action === 'saveConfig') {
        // 保存配置
        const config = request.config || {};
        chrome.storage.local.set({ [STORAGE_KEY]: config }, () => {
            if (chrome.runtime.lastError) {
                console.error('[Background] Save config error:', chrome.runtime.lastError);
                safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
            } else {
                console.log('[Background] Config saved:', config);
                safeSendResponse({ success: true });
            }
        });
        return true; // 保持消息通道打开以进行异步响应
    }
    else if (request.action === 'proxyFetch') {
        // 代理跨域 fetch 请求
        const { url, options = {} } = request;
        console.log('[Background] Proxy fetch:', url);

        // 设置较短的超时时间，避免超过消息通道的超时限制（约 60 秒）
        const timeout = Math.min(options.timeout || 10000, 50000);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            controller.abort();
        }, timeout);

        // 确保一定会发送响应，避免消息通道超时错误
        fetch(url, {
            method: options.method || 'GET',
            headers: options.headers || {},
            body: options.body,
            credentials: options.credentials || 'omit',
            signal: controller.signal
        })
            .then(async response => {
                clearTimeout(timeoutId);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const text = await response.text();
                console.log('[Background] Proxy fetch success, length:', text.length);
                safeSendResponse({ success: true, data: text });
            })
            .catch(error => {
                clearTimeout(timeoutId);
                const errorMsg = error.name === 'AbortError'
                    ? `Request timeout after ${timeout}ms`
                    : error.message;
                console.error('[Background] Proxy fetch error:', errorMsg);
                safeSendResponse({ success: false, error: errorMsg });
            })
            .finally(() => {
                // 确保超时被清除
                clearTimeout(timeoutId);
            });
        return true; // 保持消息通道打开以进行异步响应
    }
    else {
        // 未知的 action，同步返回错误
        console.warn('[Background] Unknown action:', request.action);
        safeSendResponse({ success: false, error: `Unknown action: ${request.action}` });
        return false; // 同步响应
    }
});

// ── Background WebSocket Bridge ──
// 为每个标签页的 content script 维护独立的 WebSocket 连接，
// 解决 HTTPS 页面无法直连 localhost 的 Private Network Access 限制。

const wsConnections = new Map();

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'ws-bridge') return;

  const tabId = port.sender?.tab?.id || 'unknown';
  console.log('[Background] WS bridge connected from tab:', tabId);

  let ws = null;

  port.onMessage.addListener((msg) => {
    if (msg.action === 'connect') {
      if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
      }

      try {
        ws = new WebSocket(msg.url);

        ws.onopen = () => {
          port.postMessage({ type: 'open', url: msg.url });
        };

        ws.onmessage = (event) => {
          port.postMessage({ type: 'message', data: event.data, url: msg.url });
        };

        ws.onclose = (event) => {
          port.postMessage({ type: 'close', code: event.code, reason: event.reason, url: msg.url });
          ws = null;
        };

        ws.onerror = () => {
          port.postMessage({ type: 'error', url: msg.url });
        };

        wsConnections.set(port, ws);
        console.log('[Background] WebSocket created for tab:', tabId, 'url:', msg.url);
      } catch (e) {
        console.error('[Background] Failed to create WebSocket:', e);
        port.postMessage({ type: 'error', url: msg.url, error: e.message });
      }
    } else if (msg.action === 'send') {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(msg.data);
      } else {
        console.warn('[Background] WebSocket not open, cannot send');
      }
    } else if (msg.action === 'disconnect') {
      if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
      }
      wsConnections.delete(port);
      console.log('[Background] WebSocket disconnected for tab:', tabId);
    }
  });

  port.onDisconnect.addListener(() => {
    console.log('[Background] WS bridge port disconnected from tab:', tabId);
    if (ws) {
      try { ws.close(); } catch (e) {}
      ws = null;
    }
    wsConnections.delete(port);
  });
});