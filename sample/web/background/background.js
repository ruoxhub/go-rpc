// Background script for XHS Post Extractor

const STORAGE_KEY = 'crawler_rpc_config';

// SW 端心跳间隔（ms）。MAIN 世界的 setInterval 在后台标签会被节流到 30s+，
// 服务端 60s 内收不到任何消息会踢人，所以心跳必须由 SW 发起 — SW 内的 timer 不受标签节流影响。
const SW_HEARTBEAT_INTERVAL_MS = 20000;

// SW 保活 alarm。MV3 SW 空闲 30s 即被回收，所有 chrome.runtime.Port 一并断开。
// 用 chrome.alarms 周期性唤醒 SW（最小 0.5 分钟），结合 ws/心跳活动一起保活。
const SW_KEEPALIVE_ALARM = 'sekiro-sw-keepalive';

if (typeof chrome !== 'undefined' && chrome.alarms) {
  chrome.alarms.create(SW_KEEPALIVE_ALARM, { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    // 处理函数留空：alarm 触发本身即唤醒 SW，足以重置空闲计时。
    if (alarm.name === SW_KEEPALIVE_ALARM) return;
  });
}

let wsConnection = null;

let hasCapturedXClientData = false;
let hasCapturedXBrowserValidation = false;

// ── 浏览器环境检测 ──
// Firefox 在全局暴露 browser 对象（且 browser !== chrome），Chrome 不暴露
const isFirefox = (function () {
  try {
    return typeof browser !== 'undefined' && browser.runtime && browser.runtime.getURL('').indexOf('moz-extension:') === 0;
  } catch (e) {
    return false;
  }
})();

// ── APM 上报拦截（zhipin.com DEVICE_ACTION 反检测） ──
// 拦截发往 apm-fe.zhipin.com 的 DEVICE_ACTION 上报请求，
// 阻止服务端获知本地 WebSocket 代理和 Chrome 扩展检测结果。
(function installApmBlockRule() {
  var dnr = (typeof chrome !== 'undefined' && chrome.declarativeNetRequest) ||
            (typeof browser !== 'undefined' && browser.declarativeNetRequest);
  if (!dnr) return;

  // 细粒度功能检测：确保动态规则 API 可用
  if (typeof dnr.addDynamicRules !== 'function' || typeof dnr.getDynamicRules !== 'function') {
    console.warn('[Background] declarativeNetRequest dynamic rules API not available');
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

// ── webRequest 拦截 YouTube 请求头 ──
// Firefox 不支持 extraHeaders 选项，需要做兼容处理
var webRequestExtraInfoSpec = ["requestHeaders"];
if (!isFirefox) {
  // Chrome 需要 extraHeaders 才能获取 X-Client-Data 等自定义头
  webRequestExtraInfoSpec.push("extraHeaders");
}

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
    webRequestExtraInfoSpec
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
    else if (request.action === 'navigate') {
        // 浏览器标签页导航
        const { url, tabId, newTab } = request;
        if (!url) {
            safeSendResponse({ success: false, error: 'URL is required' });
            return false;
        }

        const doNavigate = (targetTabId) => {
            chrome.tabs.update(targetTabId, { url }, (tab) => {
                if (chrome.runtime.lastError) {
                    safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    return;
                }
                safeSendResponse({
                    success: true,
                    tabId: tab.id,
                    title: tab.title || '',
                    url: tab.url || url
                });
            });
        };

        if (newTab) {
            chrome.tabs.create({ url }, (tab) => {
                safeSendResponse({
                    success: true,
                    tabId: tab.id,
                    title: tab.title || '',
                    url: tab.url || url
                });
            });
            return true;
        }

        if (tabId) {
            doNavigate(tabId);
        } else {
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                if (tabs && tabs.length > 0) {
                    doNavigate(tabs[0].id);
                } else {
                    safeSendResponse({ success: false, error: 'No active tab found' });
                }
            });
        }
        return true;
    }
    else if (request.action === 'tabs') {
        // 标签页查询与操作 (query/create/update/remove/get)
        const { method, args } = request;
        if (!method || !chrome.tabs[method]) {
            safeSendResponse({ success: false, error: `Unknown tabs method: ${method}` });
            return false;
        }

        try {
            const methodFn = chrome.tabs[method];
            const methodArgs = args || [];

            // chrome.tabs.remove 接受 (tabIds, callback) 或 (tabIds) → Promise
            // chrome.tabs.query/get/create/update 接受 (arg1, ..., callback) 或 (arg1, ...) → Promise
            if (method === 'remove') {
                methodFn(methodArgs[0], () => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, tabs: null, tabId: null });
                    }
                });
            } else if (method === 'query') {
                methodFn(methodArgs[0] || {}, (tabs) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, tabs: tabs, tabId: tabs && tabs.length > 0 ? tabs[0].id : null });
                    }
                });
            } else if (method === 'get') {
                methodFn(methodArgs[0], (tab) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, tabs: tab, tabId: tab.id });
                    }
                });
            } else if (method === 'create') {
                methodFn(methodArgs[0] || {}, (tab) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, tabs: tab, tabId: tab.id });
                    }
                });
            } else if (method === 'update') {
                methodFn(methodArgs[0], methodArgs[1] || {}, (tab) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, tabs: tab, tabId: tab.id });
                    }
                });
            } else {
                safeSendResponse({ success: false, error: `Unsupported tabs method: ${method}` });
            }
        } catch (e) {
            safeSendResponse({ success: false, error: e.message || 'Tabs operation failed' });
        }
        return true;
    }
    else if (request.action === 'getCookies') {
        // 获取 Cookie（需要 cookies 权限）
        const { url, name } = request;
        try {
            const getAll = () => {
                chrome.cookies.getAll({ url: url || undefined }, (cookies) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, cookies: cookies || [] });
                    }
                });
            };

            if (name) {
                // 按名称过滤特定 cookie
                chrome.cookies.getAll({ url: url || undefined, name }, (cookies) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, cookies: cookies || [] });
                    }
                });
            } else {
                getAll();
            }
        } catch (e) {
            safeSendResponse({ success: false, error: e.message || 'getCookies failed', cookies: [] });
        }
        return true;
    }
    else if (request.action === 'screenshot') {
        // 截取标签页截图（需要 activeTab 或 tabs 权限）
        const { tabId } = request;
        try {
            const captureOptions = {};
            if (tabId) {
                // chrome.tabs.captureVisibleTab 只能截取窗口，不支持指定 tabId
                // 这里使用 tabId 找到对应窗口
                chrome.tabs.get(tabId, (tab) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                        return;
                    }
                    chrome.tabs.captureVisibleTab(tab.windowId, captureOptions, (dataUrl) => {
                        if (chrome.runtime.lastError) {
                            safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                        } else {
                            safeSendResponse({ success: true, data: dataUrl });
                        }
                    });
                });
            } else {
                chrome.tabs.captureVisibleTab(null, captureOptions, (dataUrl) => {
                    if (chrome.runtime.lastError) {
                        safeSendResponse({ success: false, error: chrome.runtime.lastError.message });
                    } else {
                        safeSendResponse({ success: true, data: dataUrl });
                    }
                });
            }
        } catch (e) {
            safeSendResponse({ success: false, error: e.message || 'Screenshot failed' });
        }
        return true;
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
  let disconnected = false;
  let heartbeatTimer = null;
  let currentGroup = '';
  let currentClientId = '';

  const safePostMessage = (msg) => {
    if (disconnected) return;
    try {
      port.postMessage(msg);
    } catch (e) {
      if (e.message.includes('disconnected port')) {
        disconnected = true;
      } else {
        console.error('[Background] postMessage error:', e);
      }
    }
  };

  const stopHeartbeat = () => {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  // 在 SW 内启动心跳：MAIN 世界的 setInterval 在后台标签会被节流到 30s+，
  // 服务端 60s 没收到任何消息会踢人，所以心跳必须由 SW 发出。
  // SW 的定时器不受标签节流影响，配合 chrome.alarms 保活，足以稳定撑住连接。
  const startHeartbeat = () => {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return;
      }
      try {
        ws.send(JSON.stringify({
          type: 'heartbeat',
          group: currentGroup,
          clientId: currentClientId,
          timestamp: Date.now()
        }));
      } catch (e) {
        console.warn('[Background] Heartbeat send failed:', e.message || e);
      }
    }, SW_HEARTBEAT_INTERVAL_MS);
  };

  // 从 ws://host:port/business/register?group=X&clientId=Y 解析 group/clientId
  const parseRegisterURL = (url) => {
    try {
      const u = new URL(url);
      return {
        group: u.searchParams.get('group') || '',
        clientId: u.searchParams.get('clientId') || ''
      };
    } catch (e) {
      return { group: '', clientId: '' };
    }
  };

  port.onMessage.addListener((msg) => {
    if (msg.action === 'connect') {
      stopHeartbeat();
      if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
      }

      const meta = parseRegisterURL(msg.url);
      currentGroup = meta.group;
      currentClientId = meta.clientId;

      try {
        ws = new WebSocket(msg.url);

        ws.onopen = () => {
          safePostMessage({ type: 'open', url: msg.url });
          startHeartbeat();
        };

        ws.onmessage = (event) => {
          safePostMessage({ type: 'message', data: event.data, url: msg.url });
        };

        ws.onclose = (event) => {
          stopHeartbeat();
          safePostMessage({ type: 'close', code: event.code, reason: event.reason, url: msg.url });
          ws = null;
        };

        ws.onerror = () => {
          safePostMessage({ type: 'error', url: msg.url });
        };

        wsConnections.set(port, ws);
        console.log('[Background] WebSocket created for tab:', tabId, 'url:', msg.url);
      } catch (e) {
        console.error('[Background] Failed to create WebSocket:', e);
        safePostMessage({ type: 'error', url: msg.url, error: e.message });
      }
    } else if (msg.action === 'send') {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(msg.data);
      } else {
        console.warn('[Background] WebSocket not open, cannot send');
      }
    } else if (msg.action === 'disconnect') {
      stopHeartbeat();
      if (ws) {
        try { ws.close(); } catch (e) {}
        ws = null;
      }
      wsConnections.delete(port);
      console.log('[Background] WebSocket disconnected for tab:', tabId);
    }
  });

  port.onDisconnect.addListener(() => {
    disconnected = true;
    stopHeartbeat();
    console.log('[Background] WS bridge port disconnected from tab:', tabId);
    if (ws) {
      try { ws.close(); } catch (e) {}
      ws = null;
    }
    wsConnections.delete(port);
  });
});