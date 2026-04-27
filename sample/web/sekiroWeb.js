/**
 * Sekiro WebSocket RPC 客户端
 *
 * 通过 WebSocket 与 Sekiro 服务器通信，实现远程数据抓取和自动化操作。
 * 使用 IIFE 包裹以防止重复注入时 "Identifier has already been declared" 错误。
 */

(function () {
  'use strict';

  // 防止重复注入：如果 SekiroClient 已存在于 window 上，则跳过整个定义
  if (typeof window !== 'undefined' && window.SekiroClient) {
    return;
  }

/**
 * @typedef {Object} SekiroRequest
 * @property {string} action - Action 名称
 * @property {Object} [params] - 请求参数
 * @property {string} [__sekiro_seq__] - 请求序列号
 */

/**
 * @typedef {Object} SekiroResponse
 * @property {*} [data] - 响应数据
 * @property {number} [code] - 响应码
 * @property {number} [status] - 状态码
 * @property {string} [message] - 错误消息
 * @property {string} [__sekiro_seq__] - 请求序列号
 */

/**
 * @callback ActionHandler
 * @param {SekiroRequest} request - 请求对象
 * @param {Function} resolve - 成功回调
 * @param {Function} reject - 失败回调
 * @returns {void}
 */

class SekiroClient {
  /**
   * @param {string} wsURL - WebSocket 服务器地址
   */
  constructor(wsURL) {
    if (!wsURL) {
      throw new Error('wsURL 不能为空');
    }
    /** @type {string} */
    this.wsURL = wsURL;
    /** @type {WebSocket|null} */
    this.socket = null;
    /** @type {Map<string, ActionHandler>} */
    this.handlers = new Map();
    /** @type {boolean} */
    this.isManualDisconnect = false;
    /** @type {number|null} */
    this.reconnectTimer = null;
    /** @type {number} 重连次数 */
    this.reconnectAttempts = 0;
    /** @type {number} 最大重连次数 */
    this.maxReconnectAttempts = 50;
    /** @type {number} 基础重连延迟 (ms) */
    this.baseReconnectDelay = 1000;
    /** @type {number} 最大重连延迟 (ms) */
    this.maxReconnectDelay = 30000;
    /** @type {boolean} 是否正在重连中（防止 onerror/onclose 双重触发） */
    this.isReconnecting = false;

    // 注册默认的 _execjs handler
    this.handlers.set('_execjs', this._execjsHandler.bind(this));

    this.connect();
  }

  /**
   * 默认 _execjs handler - 执行 JavaScript 代码
   * @param {SekiroRequest} request - 请求对象
   * @param {Function} resolve - 成功回调
   * @param {Function} reject - 失败回调
   */
  _execjsHandler(request, resolve, reject) {
    // Sekiro 旧版本兼容：支持 param 和 code 字段
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
   * 日志输出
   * @param {string} message - 日志消息
   */
  log(message) {
    console.log(`[SekiroClient] ${message}`);
  }

  /**
   * 连接 WebSocket
   */
  connect() {
    this.log(`正在连接 wsURL: ${this.wsURL}`);
    this.isManualDisconnect = false;
    this.isReconnecting = false;

    // 清理旧 socket 的事件监听，防止延迟关闭触发多余重连
    this.cleanupSocket();

    try {
      this.socket = new WebSocket(this.wsURL);

      this.socket.onopen = (event) => {
        this.log(`成功建立连接`);
        // 连接成功后重置重连计数
        this.reconnectAttempts = 0;
      };

      this.socket.onmessage = (event) => {
        try {
          this.handleSekiroRequest(event.data);
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
        this.scheduleReconnect();
      };

      this.socket.onerror = (event) => {
        this.log(`WebSocket 连接错误`);
        // onerror 后必然触发 onclose，由 onclose 统一调度重连
        // 此处仅标记状态，避免双重重连
        this.isReconnecting = true;
      };

    } catch (e) {
      this.log(`创建连接失败：${e}`);
      this.scheduleReconnect();
    }
  }

  /**
   * 清理旧 socket，移除事件监听
   */
  cleanupSocket() {
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
   */
  scheduleReconnect() {
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
        this.connect();
      }
    }, delay);
  }

  /**
   * 断开连接
   */
  disconnect() {
    this.log('正在断开连接...');
    this.isManualDisconnect = true;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.cleanupSocket();
  }

  /**
   * 处理 Sekiro 请求
   * @param {string} requestJson - JSON 格式的请求
   */
  handleSekiroRequest(requestJson) {
    let request;
    try {
      request = JSON.parse(requestJson);
    } catch (e) {
      this.log(`JSON 解析失败：${e}`);
      return;
    }

    const seq = request.__sekiro_seq__ || '';

    if (!request.action) {
      this.sendFailed(seq, '缺少 request 参数 {action}');
      return;
    }

    const action = request.action;
    const handler = this.handlers.get(action);

    if (!handler) {
      this.sendFailed(seq, `未定义 action 处理函数：${action}`);
      return;
    }

    try {
      handler(request,
        (response) => {
          try {
            this.sendSuccess(seq, response);
          } catch (e) {
            this.sendFailed(seq, `响应异常：${e}`);
          }
        },
        (errorMessage) => {
          this.sendFailed(seq, errorMessage);
        }
      );
    } catch (e) {
      this.log(`执行 action 处理函数异常：${e}`);
      this.sendFailed(seq, String(e));
    }
  }

  /**
   * 发送成功响应
   * @param {string} seq - 请求序列号
   * @param {*} response - 响应数据
   */
  sendSuccess(seq, response) {
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
    responseJson.__sekiro_seq__ = seq;

    const responseText = JSON.stringify(responseJson);
    this.send(responseText);
  }

  /**
   * 发送失败响应
   * @param {string} seq - 请求序列号
   * @param {string} errorMessage - 错误消息
   */
  sendFailed(seq, errorMessage) {
    const responseJson = {
      message: errorMessage,
      status: -1,
      __sekiro_seq__: seq
    };

    const responseText = JSON.stringify(responseJson);
    this.log(`返回失败信息：${responseText}`);
    this.send(responseText);
  }

  /**
   * 发送 WebSocket 消息
   * @param {string} message - 消息内容
   */
  send(message) {
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
   * 注册 Action 处理器
   * @param {string} action - Action 名称
   * @param {ActionHandler} handler - 处理函数
   * @returns {SekiroClient} - 返回自身以支持链式调用
   */
  registerAction(action, handler) {
    if (typeof action !== 'string') {
      throw new Error('action 类型必须为字符串');
    }
    if (typeof handler !== 'function') {
      throw new Error('handler 必须为函数类型');
    }

    this.log(`注册 action: ${action}`);
    this.handlers.set(action, handler);
    return this;
  }

  /**
   * 移除 Action 处理器
   * @param {string} action - Action 名称
   * @returns {boolean} - 是否成功移除
   */
  unregisterAction(action) {
    return this.handlers.delete(action);
  }

  /**
   * 检查是否已注册某个 action
   * @param {string} action - Action 名称
   * @returns {boolean} - 是否已注册
   */
  hasAction(action) {
    return this.handlers.has(action);
  }

  /**
   * 获取所有已注册的 action 列表
   * @returns {string[]} - Action 名称列表
   */
  getActions() {
    return Array.from(this.handlers.keys());
  }

  /**
   * 检查连接状态
   * @returns {boolean} - 是否已连接
   */
  isConnected() {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
}

// 导出到 window 对象（用于 Content Script）
if (typeof window !== 'undefined') {
  window.SekiroClient = SekiroClient;
}

})();
