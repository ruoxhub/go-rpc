/**
 * BaseClient - 客户端基础框架类
 *
 * 用于统一管理所有平台客户端的通用逻辑，减少代码重复。
 * 已将 RpcClient 的 WebSocket 连接、JSON-RPC 协议、Action 调度与重连逻辑融合至此，
 * 不再依赖外部 window.RpcClient。
 *
 * 使用 IIFE 包裹以防止重复注入时声明冲突
 *
 * 使用方法:
 * 1. 创建平台配置对象
 * 2. 定义平台特定的 API 方法
 * 3. 配置 actions 映射
 * 4. 调用 BaseClient.create() 创建客户端
 */

(function () {
  'use strict';

  // 防止重复注入
  if (typeof window !== 'undefined' && window.__crawler_baseclient_loaded) {
    return;
  }

/**
 * Background WebSocket 代理类
 * 通过 window.postMessage 与 ISOLATED world 的 bridge.js 通信，
 * 由 bridge.js 经 chrome.runtime.connect() Port 转发到 Background Service Worker，
 * 最终由 Background 建立真实的 WebSocket 连接。
 * 解决 HTTPS 公共页面无法直连 localhost 的 Private Network Access 限制。
 */
class BackgroundWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    this._messageHandler = this._handleMessage.bind(this);
    window.addEventListener('message', this._messageHandler);
    this._connect();
  }

  _connect() {
    window.postMessage({
      source: 'crawler_rpc_main',
      action: 'wsConnect',
      url: this.url
    }, '*');
  }

  send(data) {
    window.postMessage({
      source: 'crawler_rpc_main',
      action: 'wsSend',
      data: data
    }, '*');
  }

  close() {
    window.removeEventListener('message', this._messageHandler);
    window.postMessage({
      source: 'crawler_rpc_main',
      action: 'wsDisconnect'
    }, '*');
    this.readyState = WebSocket.CLOSING;
  }

  _handleMessage(event) {
    if (event.source !== window) return;
    const msg = event.data;
    if (!msg || msg.source !== 'crawler_rpc_bridge' || msg.action !== 'wsEvent') return;
    if (msg.url && msg.url !== this.url) return;

    switch (msg.eventType) {
      case 'open':
        this.readyState = WebSocket.OPEN;
        if (this.onopen) this.onopen(msg);
        break;
      case 'message':
        if (this.onmessage) this.onmessage({ data: msg.data });
        break;
      case 'close':
        this.readyState = WebSocket.CLOSED;
        window.removeEventListener('message', this._messageHandler);
        if (this.onclose) this.onclose({ code: msg.code, reason: msg.reason });
        break;
      case 'error':
        if (this.onerror) this.onerror(msg);
        break;
    }
  }
}

/**
 * @typedef {Object} ClientConfig
 * @property {string} platform - 平台名称
 * @property {string|string[]} hostnames - 支持的域名
 * @property {string} [group] - rpc group 名称
 * @property {string} [logPrefix] - 日志前缀
 * @property {Object} [endpoints] - API 端点映射
 * @property {Object} [actions] - Action 配置
 * @property {Object} [params] - 默认参数
 * @property {boolean} [autoStart] - 是否自动启动
 * @property {number} [startDelay] - 启动延迟 (ms)
 * @property {number} [actionDelay] - Action 执行延迟 (ms)
 * @property {Function} [onInit] - 初始化回调
 */

/**
 * @typedef {Object} ResolvedConfig
 * @property {string} platform
 * @property {string|string[]} hostnames
 * @property {string} [group]
 * @property {string} [logPrefix]
 * @property {Object} [endpoints]
 * @property {Object} [actions]
 * @property {Object} [params]
 * @property {boolean} [autoStart]
 * @property {number} [startDelay]
 * @property {number} [actionDelay]
 * @property {string} [rpcHost]
 * @property {Function} [onInit]
 */

/**
 * @callback SimpleActionHandler
 * @param {Object} params - 请求参数
 * @returns {Promise<any>}
 */

/**
 * @typedef {Object} ActionConfig
 * @property {Function} method - 处理方法
 * @property {Function|null} [transform] - 响应转换函数
 */

/**
 * @callback ActionHandler
 * @param {Object} request - rpc 请求对象
 * @param {Function} resolve - 成功回调
 * @param {Function} reject - 失败回调
 */

class BaseClient {
  /**
   * 存储配置的键名
   */
  static STORAGE_KEY = 'crawler_rpc_config';

  /**
   * 默认配置
   */
  static defaultConfig = {
    rpcHost: 'ws://127.0.0.1:5612',
    startDelay: 2000,
    autoStart: true,
    logPrefix: 'Client',
    actionDelay: 0,
    antiDetect: true,
  };

  /**
   * @param {ResolvedConfig} config
   */
  constructor(config) {
    this.config = config;
    this.platform = config.platform;
    this.group = config.group || config.platform;
    this.hostnames = Array.isArray(config.hostnames) ? config.hostnames : [config.hostnames];
    this.actions = config.actions || {};
    this.endpoints = config.endpoints || {};
    this.params = config.params || {};
    this.isInitialized = false;
    this.actionDelay = config.actionDelay || 0;

    // WebSocket / RPC 内部状态（原 RpcClient 逻辑）
    this.socket = null;
    this.handlers = new Map();
    this.isManualDisconnect = false;
    this.reconnectTimer = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 50;
    this.baseReconnectDelay = 1000;
    this.maxReconnectDelay = 30000;
    this.isReconnecting = false;

    // 注册默认的 _execjs handler
    this.handlers.set('_execjs', this._execjsHandler.bind(this));

    if (!this.isCorrectDomain()) {
      return;
    }

    this.log('正在初始化...');

    // 反检测状态报告
    if (this.config.antiDetect !== false) {
      if (window.__crawler_anti_detect_loaded) {
        this.log('反检测模块已激活 (WebSocket 端口探测拦截 + Chrome 扩展检测拦截)');
      } else {
        this.log('反检测模块未加载，建议在站点 content_scripts 中添加 lib/anti-detect.js', 'warn');
      }
      if (window.__OriginalWebSocket__) {
        this.log('检测到原始 WebSocket 引用已保存，rpc 连接将使用原始构造函数');
      }
    }

    if (typeof config.onInit === 'function') {
      config.onInit.call(this);
    }

    this.setupConfigChangeListener();

    if (config.autoStart !== false) {
      setTimeout(() => this.start(), config.startDelay || 2000);
    }
  }

  /**
   * 从 Chrome Storage 加载配置 (通过桥接脚本)
   * @returns {Promise<Object>}
   */
  static async loadStoredConfig() {
    return new Promise((resolve) => {
      const requestId = 'config_' + Math.random().toString(36).substr(2, 9);
      const timeout = 3000;
      let resolved = false;

      const timeoutId = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          console.log('[BaseClient] Config load timeout, using defaults');
          window.removeEventListener('message', messageHandler);
          resolve({});
        }
      }, timeout);

      function messageHandler(event) {
        if (event.source !== window) return;

        const data = event.data;
        if (!data || data.source !== 'crawler_rpc_bridge') return;
        if (data.requestId !== requestId) return;

        resolved = true;
        clearTimeout(timeoutId);
        window.removeEventListener('message', messageHandler);

        if (data.success) {
          console.log('[BaseClient] Loaded stored config:', data.config);
          resolve(data.config || {});
        } else {
          console.log('[BaseClient] Failed to load config:', data.error);
          resolve({});
        }
      }

      window.addEventListener('message', messageHandler);

      console.log('[BaseClient] Requesting config from bridge...');
      window.postMessage({
        source: 'crawler_rpc_main',
        action: 'getConfig',
        requestId: requestId
      }, '*');
    });
  }

  /**
   * 创建客户端实例
   * @param {ClientConfig} config
   * @returns {BaseClient}
   */
  static create(config) {
    const mergedConfig = { ...this.defaultConfig, ...config };
    return new BaseClient(mergedConfig);
  }

  /**
   * 设置配置变更监听器
   */
  setupConfigChangeListener() {
    window.addEventListener('message', (event) => {
      if (event.source !== window) return;

      const data = event.data;
      if (!data || data.source !== 'crawler_rpc_bridge') return;

      if (data.action === 'configUpdated' && data.config) {
        this.log('收到配置更新通知');
        if (data.config.wsHost && data.config.wsHost !== this.config.rpcHost) {
          this.log(`WebSocket 地址已变更：${this.config.rpcHost} -> ${data.config.wsHost}`);
          this.reconnect(data.config.wsHost);
        }
        if (typeof data.config.actionDelay === 'number') {
          this.actionDelay = data.config.actionDelay;
          this.log(`Action 延迟已更新：${this.actionDelay}ms`);
        }
      }
    });
  }

  /**
   * 检查当前页面是否在正确的域名
   * @returns {boolean}
   */
  isCorrectDomain() {
    const hostname = window.location.hostname;
    return this.hostnames.some(h => hostname.includes(h));
  }

  /**
   * 统一日志输出
   * @param {string} message
   * @param {'log'|'warn'|'error'} [level='log']
   */
  log(message, level = 'log') {
    const prefix = `[${this.config.logPrefix || this.platform}]`;
    const timestamp = new Date().toISOString();
    const fullMessage = `${timestamp} ${prefix} ${message}`;

    const globalLogToConsole = window.logToConsole;
    if (typeof globalLogToConsole === 'function') {
      globalLogToConsole(fullMessage);
    } else {
      console[level](fullMessage);
    }
  }

  /**
   * 启动 rpc 客户端
   */
  async start() {
    try {
      const storedConfig = await BaseClient.loadStoredConfig();
      if (storedConfig.wsHost) {
        this.config.rpcHost = storedConfig.wsHost;
        this.log(`使用存储的 WebSocket 地址：${storedConfig.wsHost}`);
      }
      if (typeof storedConfig.actionDelay === 'number') {
        this.actionDelay = storedConfig.actionDelay;
        this.log(`使用存储的 Action 延迟：${this.actionDelay}ms`);
      }

      const wsURL = this.buildWebSocketURL();
      this.log(`连接 rpc: ${wsURL}`);

      this._connect(wsURL);
      this.registerAllActions();
      this.isInitialized = true;

      this.log('rpc 客户端初始化成功');
    } catch (error) {
      this.log(`rpc 客户端初始化失败：${error instanceof Error ? error.message : error}`, 'error');
    }
  }

  /**
   * 使用新地址重新连接
   * @param {string} newWsHost
   */
  reconnect(newWsHost) {
    this.log('正在重新连接...');

    this._disconnect();

    this.config.rpcHost = newWsHost;

    const wsURL = this.buildWebSocketURL();
    this.log(`连接新地址：${wsURL}`);

    try {
      this._connect(wsURL);
      this.registerAllActions();
      this.log('重新连接成功');
    } catch (error) {
      this.log(`重新连接失败：${error instanceof Error ? error.message : error}`, 'error');
    }
  }

  /**
   * 构建 WebSocket URL
   * @returns {string}
   */
  buildWebSocketURL() {
    const host = this.config.rpcHost || 'ws://127.0.0.1:5612';
    const clientId = Math.random().toString(36).substr(2, 9);
    return `${host}/business/register?group=${this.group}&clientId=${clientId}`;
  }

  /**
   * 注册所有 actions
   */
  registerAllActions() {
    for (const [actionName, actionConfig] of Object.entries(this.actions)) {
      this.registerAction(actionName, actionConfig);
    }
  }

  /**
   * 注册单个 action
   * @param {string} actionName
   * @param {SimpleActionHandler|ActionConfig} actionConfig
   */
  registerAction(actionName, actionConfig) {
    let handler;

    if (typeof actionConfig === 'function') {
      handler = this.wrapHandler(actionConfig);
    } else if (typeof actionConfig === 'object') {
      const { method, transform } = actionConfig;

      if (typeof method !== 'function') {
        this.log(`Action ${actionName} 缺少有效的 method`, 'warn');
        return;
      }

      handler = (request, resolve, reject) => {
        const executeAction = () => {
          const params = request.params || {};
          method(params)
            .then(response => {
              const result = typeof transform === 'function'
                ? transform(response)
                : response;
              resolve(result);
            })
            .catch(error => {
              reject(error.message || String(error));
            });
        };

        const delay = this.actionDelay;
        if (delay > 0) {
          this.log(`Action ${actionName} 延迟 ${delay}ms 执行`);
          setTimeout(executeAction, delay);
        } else {
          executeAction();
        }
      };
    } else {
      this.log(`Action ${actionName} 配置无效`, 'warn');
      return;
    }

    this.handlers.set(actionName, handler);
    this.log(`注册 Action: ${actionName}${this.actionDelay > 0 ? ` (延迟 ${this.actionDelay}ms)` : ''}`);
  }

  /**
   * 包装处理函数，添加错误处理
   * @param {Function} handler
   * @returns {ActionHandler}
   */
  wrapHandler(handler) {
    return async (request, resolve, reject) => {
      try {
        const delay = this.actionDelay;
        if (delay > 0) {
          this.log(`Handler 延迟 ${delay}ms 执行`);
          await new Promise(r => setTimeout(r, delay));
        }
        const params = request.params || {};
        const result = await handler.call(this, params);
        resolve(result);
      } catch (error) {
        reject(error instanceof Error ? error.message : String(error));
      }
    };
  }

  /**
   * 获取客户端状态
   * @returns {{isInitialized: boolean, isConnected: boolean, platform: string}}
   */
  getStatus() {
    return {
      isInitialized: this.isInitialized,
      isConnected: this._isConnected(),
      platform: this.platform
    };
  }

  // ==================== 以下为融合进来的 RpcClient 核心逻辑 ====================

  /**
   * 建立 WebSocket 连接
   * @param {string} wsURL
   */
  _connect(wsURL) {
    this.log(`正在连接 wsURL: ${wsURL}`);
    this.isManualDisconnect = false;
    this.isReconnecting = false;

    // 清理旧 socket 的事件监听，防止延迟关闭触发多余重连
    this._cleanupSocket();

    try {
      // 使用 BackgroundWebSocket 代理，通过 Bridge -> Background -> 真实 WS 连接
      // 绕过 HTTPS 页面无法直连 localhost 的 Private Network Access 限制
      this.socket = new BackgroundWebSocket(wsURL);

      this.socket.onopen = (event) => {
        this.log(`成功建立连接`);
        // 连接成功后重置重连计数
        this.reconnectAttempts = 0;
      };

      this.socket.onmessage = (event) => {
        try {
          this._handleRpcRequest(event.data);
        } catch (ex) {
          this.log(`处理消息异常：${ex}`);
        }
      };

      this.socket.onclose = (event) => {
        this.socket = null;
        if (this.isManualDisconnect) {
          this.log('连接已手动断开');
          this.isReconnecting = false;
          return;
        }
        // 如果 onerror 已标记正在重连，仍由 onclose 统一调度，但重置标记
        this.isReconnecting = false;
        this.log(`连接断开 (code=${event.code}, reason=${event.reason || '无'})`);
        this._scheduleReconnect(wsURL);
      };

      this.socket.onerror = (event) => {
        this.log(`WebSocket 连接错误`);
        // onerror 后必然触发 onclose，由 onclose 统一调度重连
        // 此处仅标记状态，避免双重重连
        this.isReconnecting = true;
      };

    } catch (e) {
      this.log(`创建连接失败：${e}`);
      this._scheduleReconnect(wsURL);
    }
  }

  /**
   * 清理旧 socket，移除事件监听
   */
  _cleanupSocket() {
    if (this.socket) {
      try {
        this.socket.onopen = null;
        this.socket.onmessage = null;
        this.socket.onclose = null;
        this.socket.onerror = null;
        if (this.socket.readyState === WebSocket.OPEN ||
            this.socket.readyState === WebSocket.CONNECTING) {
          this.socket.close();
        }
      } catch (e) {
        // 忽略关闭异常
      }
      this.socket = null;
    }
  }

  /**
   * 调度重连（指数退避策略）
   * @param {string} wsURL
   */
  _scheduleReconnect(wsURL) {
    if (this.isManualDisconnect) {
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.log(`已达到最大重连次数 (${this.maxReconnectAttempts})，停止重连`);
      return;
    }

    if (this.reconnectTimer) {
      return; // 已有待执行的重连，避免重复调度
    }

    this.reconnectAttempts++;
    // 指数退避：1s, 2s, 4s, 8s, 16s, 30s, 30s, ...
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    this.log(`第 ${this.reconnectAttempts} 次重连，${Math.round(delay / 1000)} 秒后重试`);

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.isManualDisconnect) {
        this._connect(wsURL);
      }
    }, delay);
  }

  /**
   * 断开连接
   */
  _disconnect() {
    this.log('正在断开连接...');
    this.isManualDisconnect = true;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this._cleanupSocket();
  }

  /**
   * 处理 Rpc 请求
   * @param {string} requestJson - JSON 格式的请求
   */
  _handleRpcRequest(requestJson) {
    let request;
    try {
      request = JSON.parse(requestJson);
    } catch (e) {
      this.log(`JSON 解析失败：${e}`);
      return;
    }

    const seq = request.__Rpc_seq__ || '';

    if (!request.action) {
      this._sendFailed(seq, '缺少 request 参数 {action}');
      return;
    }

    const action = request.action;
    const handler = this.handlers.get(action);

    if (!handler) {
      this._sendFailed(seq, `未定义 action 处理函数：${action}`);
      return;
    }

    try {
      handler(request,
        (response) => {
          try {
            this._sendSuccess(seq, response);
          } catch (e) {
            this._sendFailed(seq, `响应异常：${e}`);
          }
        },
        (errorMessage) => {
          this._sendFailed(seq, errorMessage);
        }
      );
    } catch (e) {
      this.log(`执行 action 处理函数异常：${e}`);
      this._sendFailed(seq, String(e));
    }
  }

  /**
   * 发送成功响应
   * @param {string} seq - 请求序列号
   * @param {*} response - 响应数据
   */
  _sendSuccess(seq, response) {
    let responseJson;

    if (typeof response === 'string') {
      try {
        responseJson = JSON.parse(response);
      } catch (e) {
        responseJson = { data: response };
      }
    } else if (typeof response === 'object' && response !== null) {
      responseJson = response;
    } else {
      responseJson = { data: response };
    }

    // 确保是数组或字符串时包装为对象
    if (Array.isArray(responseJson) || typeof responseJson === 'string') {
      responseJson = { data: responseJson, code: 0 };
    }

    responseJson.code = 0;
    responseJson.status = 0;
    responseJson.__Rpc_seq__ = seq;

    const responseText = JSON.stringify(responseJson);
    this._send(responseText);
  }

  /**
   * 发送失败响应
   * @param {string} seq - 请求序列号
   * @param {string} errorMessage - 错误消息
   */
  _sendFailed(seq, errorMessage) {
    const responseJson = {
      message: errorMessage,
      status: -1,
      __Rpc_seq__: seq
    };

    const responseText = JSON.stringify(responseJson);
    this.log(`返回失败信息：${responseText}`);
    this._send(responseText);
  }

  /**
   * 发送 WebSocket 消息
   * @param {string} message - 消息内容
   */
  _send(message) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(message);
      } catch (e) {
        this.log(`发送消息异常：${e}`);
      }
    } else {
      this.log('WebSocket 未连接，无法发送消息');
    }
  }

  /**
   * 默认 _execjs handler - 执行 JavaScript 代码
   * @param {Object} request - 请求对象
   * @param {Function} resolve - 成功回调
   * @param {Function} reject - 失败回调
   */
  _execjsHandler(request, resolve, reject) {
    // Rpc 旧版本兼容：支持 param 和 code 字段
    const param = request.param || request.params || request.code || '';
    if (!param) {
      reject('缺少执行参数 param');
      return;
    }

    try {
      // 使用受限的 eval 执行，禁止访问外部作用域的敏感对象
      const fn = new Function(
        'request', 'resolve', 'reject',
        '"use strict"; return (async () => { return (' + param + ') })()'
      );
      const result = fn(request, resolve, reject);

      if (result && typeof result.then === 'function') {
        result
          .then(res => resolve(res !== undefined ? res : '执行成功 (无返回值)'))
          .catch(err => reject('执行错误：' + (err.message || err)));
      } else {
        resolve(result !== undefined ? result : '执行成功 (无返回值)');
      }
    } catch (err) {
      reject('语法错误：' + (err.message || err));
    }
  }

  /**
   * 检查连接状态
   * @returns {boolean} - 是否已连接
   */
  _isConnected() {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
}

/**
 * 辅助函数：创建标准 Action 配置
 * @param {Function} method
 * @param {Function|null} [transform]
 * @returns {ActionConfig}
 */
function createAction(method, transform = null) {
  return { method, transform };
}

/**
 * 辅助函数：创建带默认值的参数配置
 * @param {string} name
 * @param {*} [defaultValue]
 * @returns {{name: string, default: *}}
 */
function param(name, defaultValue = undefined) {
  return { name, default: defaultValue };
}

// 导出到 window 对象（用于 Content Script）
if (typeof window !== 'undefined') {
  window.__crawler_baseclient_loaded = true;
  window.BaseClient = BaseClient;
  window.createAction = createAction;
  window.param = param;
}

})();
