/**
 * BaseClient - 客户端基础框架类
 * 
 * 用于统一管理所有平台客户端的通用逻辑，减少代码重复
 * 
 * 使用方法:
 * 1. 创建平台配置对象
 * 2. 定义平台特定的 API 方法
 * 3. 配置 actions 映射
 * 4. 调用 BaseClient.create() 创建客户端
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
        // Sekiro 服务器地址 (默认值，可被存储配置覆盖)
        sekiroHost: 'ws://127.0.0.1:5612',
        // 延迟启动时间 (ms)
        startDelay: 2000,
        // 是否自动启动
        autoStart: true,
        // 日志前缀
        logPrefix: 'Client',
        // Action 延迟时间 (ms)，0 表示不延迟
        actionDelay: 0,
    };

    /**
     * 从 Chrome Storage 加载配置 (通过桥接脚本)
     * @returns {Promise<Object>} 存储的配置
     */
    static async loadStoredConfig() {
        return new Promise((resolve) => {
            const requestId = 'config_' + Math.random().toString(36).substr(2, 9);
            const timeout = 3000; // 3秒超时
            let resolved = false;

            // 设置超时
            const timeoutId = setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    console.log('[BaseClient] Config load timeout, using defaults');
                    window.removeEventListener('message', messageHandler);
                    resolve({});
                }
            }, timeout);

            // 消息处理函数
            function messageHandler(event) {
                if (event.source !== window) return;

                const data = event.data;
                if (!data || data.source !== 'crawler_rpc_bridge') return;
                if (data.requestId !== requestId) return;

                // 找到匹配的响应
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

            // 监听响应
            window.addEventListener('message', messageHandler);

            // 发送请求到桥接脚本
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
     * @param {Object} config - 客户端配置
     * @param {string} config.platform - 平台名称 (e.g., 'douyin', 'tiktok')
     * @param {string|string[]} config.hostnames - 匹配的域名 (e.g., 'douyin.com' 或 ['douyin.com', 'iesdouyin.com'])
     * @param {string} config.group - Sekiro 分组名称 (默认使用 platform)
     * @param {Object} config.actions - Action 配置对象
     * @param {Object} [config.endpoints] - API 端点配置 (可选)
     * @param {Object} [config.params] - 默认参数配置 (可选)
     * @param {Function} [config.onInit] - 初始化回调 (可选)
     * @param {Object} [config.options] - 其他选项
     * @returns {BaseClient} 客户端实例
     */
    static create(config) {
        const mergedConfig = { ...this.defaultConfig, ...config };
        return new BaseClient(mergedConfig);
    }

    /**
     * 构造函数
     * @param {Object} config - 客户端配置
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
        // Action 延迟时间 (可动态更新)
        this.actionDelay = config.actionDelay || 0;

        // 检查是否在正确的域名
        if (!this.isCorrectDomain()) {
            return;
        }

        this.log('正在初始化...');

        // 监听配置变更
        this.setupConfigChangeListener();

        // 执行初始化回调
        if (typeof config.onInit === 'function') {
            config.onInit.call(this);
        }

        // 自动启动
        if (config.autoStart !== false) {
            setTimeout(() => this.start(), config.startDelay || 2000);
        }
    }

    /**
     * 设置配置变更监听器
     */
    setupConfigChangeListener() {
        window.addEventListener('message', (event) => {
            if (event.source !== window) return;

            const data = event.data;
            if (!data || data.source !== 'crawler_rpc_bridge') return;

            // 监听配置更新广播
            if (data.action === 'configUpdated' && data.config) {
                this.log('收到配置更新通知');
                if (data.config.wsHost && data.config.wsHost !== this.config.sekiroHost) {
                    this.log(`WebSocket 地址已变更: ${this.config.sekiroHost} -> ${data.config.wsHost}`);
                    this.reconnect(data.config.wsHost);
                }
                // 更新 Action 延迟配置
                if (typeof data.config.actionDelay === 'number') {
                    this.actionDelay = data.config.actionDelay;
                    this.log(`Action 延迟已更新: ${this.actionDelay}ms`);
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
     * @param {string} message - 日志消息
     * @param {string} [level='log'] - 日志级别 (log, warn, error)
     */
    log(message, level = 'log') {
        const prefix = `[${this.config.logPrefix || this.platform}]`;
        const timestamp = new Date().toISOString();
        const fullMessage = `${timestamp} ${prefix} ${message}`;

        if (typeof logToConsole === 'function') {
            logToConsole(fullMessage);
        } else {
            console[level](fullMessage);
        }
    }

    /**
     * 启动 Sekiro 客户端
     */
    async start() {
        try {
            // 在启动前加载存储的配置
            const storedConfig = await BaseClient.loadStoredConfig();
            if (storedConfig.wsHost) {
                this.config.sekiroHost = storedConfig.wsHost;
                this.log(`使用存储的WebSocket地址: ${storedConfig.wsHost}`);
            }
            // 加载 Action 延迟配置
            if (typeof storedConfig.actionDelay === 'number') {
                this.actionDelay = storedConfig.actionDelay;
                this.log(`使用存储的Action延迟: ${this.actionDelay}ms`);
            }

            const wsURL = this.buildWebSocketURL();
            this.log(`连接 Sekiro: ${wsURL}`);

            this.client = new SekiroClient(wsURL);
            this.registerAllActions();
            this.isInitialized = true;

            this.log('Sekiro 客户端初始化成功');
        } catch (error) {
            this.log(`Sekiro 客户端初始化失败: ${error.message}`, 'error');
        }
    }

    /**
     * 使用新地址重新连接
     * @param {string} newWsHost - 新的 WebSocket 地址
     */
    reconnect(newWsHost) {
        this.log('正在重新连接...');

        // 断开当前连接
        if (this.client) {
            try {
                this.client.disconnect();
            } catch (error) {
                this.log(`断开连接失败: ${error.message}`, 'warn');
            }
        }

        // 更新配置
        this.config.sekiroHost = newWsHost;

        // 建立新连接
        const wsURL = this.buildWebSocketURL();
        this.log(`连接新地址: ${wsURL}`);

        try {
            this.client = new SekiroClient(wsURL);
            this.registerAllActions();
            this.log('重新连接成功');
        } catch (error) {
            this.log(`重新连接失败: ${error.message}`, 'error');
        }
    }

    /**
     * 构建 WebSocket URL
     * @returns {string}
     */
    buildWebSocketURL() {
        const host = this.config.sekiroHost || 'ws://127.0.0.1:5612';
        const clientId = Math.random();
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
     * @param {string} actionName - Action 名称
     * @param {Object|Function} actionConfig - Action 配置或处理函数
     */
    registerAction(actionName, actionConfig) {
        let handler;

        if (typeof actionConfig === 'function') {
            // 直接传入处理函数
            handler = this.wrapHandler(actionConfig);
        } else if (typeof actionConfig === 'object') {
            // 配置对象形式
            const { method, transform } = actionConfig;

            if (typeof method !== 'function') {
                this.log(`Action ${actionName} 缺少有效的 method`, 'warn');
                return;
            }

            handler = (request, resolve, reject) => {
                // 执行 action 的核心逻辑
                const executeAction = () => {
                    // 提取 params 对象传入方法
                    const params = request.params || {};
                    method(params)
                        .then(response => {
                            // 可选的响应转换
                            const result = typeof transform === 'function'
                                ? transform(response)
                                : response;
                            resolve(result);
                        })
                        .catch(error => {
                            reject(error.message || error.toString());
                        });
                };

                // 应用延迟（如果配置了延迟）
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

        this.client.registerAction(actionName, handler);
        this.log(`注册 Action: ${actionName}${this.actionDelay > 0 ? ` (延迟 ${this.actionDelay}ms)` : ''}`);
    }

    /**
     * 包装处理函数，添加错误处理
     * @param {Function} handler - 原始处理函数
     * @returns {Function} 包装后的处理函数
     */
    wrapHandler(handler) {
        return async (request, resolve, reject) => {
            try {
                // 应用延迟（如果配置了延迟）
                const delay = this.actionDelay;
                if (delay > 0) {
                    this.log(`Handler 延迟 ${delay}ms 执行`);
                    await new Promise(r => setTimeout(r, delay));
                }
                // 提取 params 对象传入方法
                const params = request.params || {};
                const result = await handler.call(this, params);
                resolve(result);
            } catch (error) {
                reject(error.message || error.toString());
            }
        };
    }

    /**
     * 创建带延迟的 API 调用
     * @param {Function} apiFunc - API 函数
     * @param {number} delay - 延迟时间 (ms)
     * @returns {Function}
     */
    withDelay(apiFunc, delay = 1000) {
        return (...args) => {
            return new Promise((resolve, reject) => {
                setTimeout(() => {
                    apiFunc(...args).then(resolve).catch(reject);
                }, delay);
            });
        };
    }

    /**
     * 合并默认参数
     * @param {Object} customParams - 自定义参数
     * @returns {Object} 合并后的参数
     */
    mergeParams(customParams = {}) {
        return { ...this.params, ...customParams };
    }

    /**
     * 获取 API 端点 URL
     * @param {string} endpointName - 端点名称
     * @returns {string} 完整 URL
     */
    getEndpoint(endpointName) {
        const endpoint = this.endpoints[endpointName];
        if (!endpoint) {
            this.log(`未找到端点: ${endpointName}`, 'warn');
            return '';
        }
        return endpoint;
    }
}

/**
 * 辅助函数：创建标准 Action 配置
 * 用于简化 action 配置的创建
 */
function createAction(method, params = [], transform = null) {
    return { method, params, transform };
}

/**
 * 辅助函数：创建带默认值的参数配置
 */
function param(name, defaultValue = undefined) {
    return { name, default: defaultValue };
}

// 导出到全局作用域
if (typeof window !== 'undefined') {
    window.BaseClient = BaseClient;
    window.createAction = createAction;
    window.param = param;
}
