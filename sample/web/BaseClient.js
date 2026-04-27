/**
 * BaseClient - 客户端基础框架类
 *
 * 用于统一管理所有平台客户端的通用逻辑，减少代码重复
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
 * @typedef {Object} ClientConfig
 * @property {string} platform - 平台名称
 * @property {string|string[]} hostnames - 支持的域名
 * @property {string} [group] - Sekiro group 名称
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
 * @property {string} [sekiroHost]
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
 * @param {Object} request - Sekiro 请求对象
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
    sekiroHost: 'ws://127.0.0.1:5612',
    startDelay: 2000,
    autoStart: true,
    logPrefix: 'Client',
    actionDelay: 0,
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
    this.client = null;
    this.isInitialized = false;
    this.actionDelay = config.actionDelay || 0;

    if (!this.isCorrectDomain()) {
      return;
    }

    this.log('正在初始化...');

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
        if (data.config.wsHost && data.config.wsHost !== this.config.sekiroHost) {
          this.log(`WebSocket 地址已变更：${this.config.sekiroHost} -> ${data.config.wsHost}`);
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
   * 启动 Sekiro 客户端
   */
  async start() {
    try {
      const storedConfig = await BaseClient.loadStoredConfig();
      if (storedConfig.wsHost) {
        this.config.sekiroHost = storedConfig.wsHost;
        this.log(`使用存储的 WebSocket 地址：${storedConfig.wsHost}`);
      }
      if (typeof storedConfig.actionDelay === 'number') {
        this.actionDelay = storedConfig.actionDelay;
        this.log(`使用存储的 Action 延迟：${this.actionDelay}ms`);
      }

      const wsURL = this.buildWebSocketURL();
      this.log(`连接 Sekiro: ${wsURL}`);

      this.client = new window.SekiroClient(wsURL);
      this.registerAllActions();
      this.isInitialized = true;

      // 延迟检查连接状态，给 WebSocket 握手留出时间
      setTimeout(() => {
        if (this.client && this.client.isConnected()) {
          this.log('Sekiro 客户端连接成功');
        } else {
          this.log('Sekiro 客户端已启动，但 WebSocket 尚未连接（将自动重连）', 'warn');
        }
      }, 3000);
    } catch (error) {
      this.log(`Sekiro 客户端初始化失败：${error instanceof Error ? error.message : error}`, 'error');
    }
  }

  /**
   * 使用新地址重新连接
   * @param {string} newWsHost
   */
  reconnect(newWsHost) {
    this.log('正在重新连接...');

    if (this.client) {
      try {
        this.client.disconnect();
      } catch (error) {
        this.log(`断开连接失败：${error instanceof Error ? error.message : error}`, 'warn');
      }
    }

    this.config.sekiroHost = newWsHost;

    const wsURL = this.buildWebSocketURL();
    this.log(`连接新地址：${wsURL}`);

    try {
      this.client = new window.SekiroClient(wsURL);
      this.registerAllActions();
      this.log('重新连接请求已发送（将自动重连）');
    } catch (error) {
      this.log(`重新连接失败：${error instanceof Error ? error.message : error}`, 'error');
    }
  }

  /**
   * 构建 WebSocket URL
   * @returns {string}
   */
  buildWebSocketURL() {
    let host = this.config.sekiroHost || 'ws://127.0.0.1:5612';
    // 自动协议适配：如果页面是 HTTPS，浏览器会阻止 ws:// 连接（混合内容策略）
    // 此处自动将 ws:// 升级为 wss://，需要服务端启用 HTTPS (端口 5643)
    if (window.location.protocol === 'https:' && host.startsWith('ws://')) {
      host = host.replace('ws://', 'wss://');
      // 默认 ws 端口 5612 -> wss 端口 5643
      host = host.replace(':5612/', ':5643/');
      this.log(`检测到 HTTPS 页面，自动升级为安全连接: ${host}`);
    }
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

    if (this.client) {
      this.client.registerAction(actionName, handler);
      this.log(`注册 Action: ${actionName}${this.actionDelay > 0 ? ` (延迟 ${this.actionDelay}ms)` : ''}`);
    }
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
      isConnected: this.client ? this.client.isConnected() : false,
      platform: this.platform
    };
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
