class SekiroClient {
    constructor(wsURL) {
        if (!wsURL) {
            throw new Error('wsURL 不能为空！！');
        }
        this.wsURL = wsURL;
        this.handlers = {
            _execjs: function (request, resolve, reject) {
                var param = request.param || request.params || request.code || '';
                if (!param) {
                    reject('缺少执行参数 param');
                    return;
                }
                try {
                    var fn = new Function('return (async () => { return ' + param + ' })()');
                    var result = fn();
                    if (result && typeof result.then === 'function') {
                        result.then(function(res) {
                            resolve(res !== undefined ? res : "执行成功(无返回值)");
                        }).catch(function(err) {
                            reject("执行错误: " + (err.message || err));
                        });
                    } else {
                        resolve(result !== undefined ? result : "执行成功(无返回值)");
                    }
                } catch (err) {
                    reject("语法错误: " + (err.message || err));
                }
            }
        };
        this.socket = null;
        this.webSocketFactory = this.resolveWebSocketFactory();
        // 注册内置的 _execjs 处理器
        // this.registerAction('_execjs', this._execjs.bind(this));
        this.connect();
    }

    // /**
    //  * 内置的 JavaScript 代码执行处理器
    //  * @param {Object} request - 请求对象
    //  * @param {Function} resolve - 成功回调
    //  * @param {Function} reject - 失败回调
    //  */
    // _execjs(request, resolve, reject) {
    //     const param = request.param || request.code || '';
    //     if (!param) {
    //         reject('缺少执行参数 param 或 code');
    //         return;
    //     }
    //     try {
    //         const fn = new Function('return (async () => { ' + param + ' })()');
    //         const result = fn();
    //         if (result && typeof result.then === 'function') {
    //             result.then(function(res) {
    //                 resolve(res !== undefined ? res : "执行成功(无返回值)");
    //             }).catch(function(err) {
    //                 reject("执行错误: " + (err.message || err));
    //             });
    //         } else {
    //             resolve(result !== undefined ? result : "执行成功(无返回值)");
    //         }
    //     } catch (err) {
    //         reject("语法错误: " + (err.message || err));
    //     }
    // }

    /**
     * 日志输出方法
     * @param {string} message - 要输出的日志消息
     */
    logToConsole(message) {
        console.log("[SekiroClient] " + message);
    }

    resolveWebSocketFactory() {
        const self = this;
        if (typeof window === 'object') {
            const theWebSocket = window.WebSocket || window.WebSocket;
            return (wsURL) => {
                const wrapper = {
                    mSocket: new theWebSocket(wsURL),

                    close() {
                        try {
                            this.mSocket.close();
                        } catch (e) {
                            self.logToConsole("关闭连接异常：" + e);
                        }
                    },

                    onmessage(onMessageFunction) {
                        this.mSocket.onmessage = onMessageFunction;
                    },

                    onopen(onOpenFunction) {
                        this.mSocket.onopen = onOpenFunction;
                    },

                    onclose(onCloseFunction) {
                        this.mSocket.onclose = onCloseFunction;
                    },

                    send(message) {
                        try {
                            this.mSocket.send(message);
                        } catch (e) {
                            self.logToConsole("发送消息异常：" + e);
                        }
                    },

                    pong() {
                        if (typeof this.mSocket.pong === 'function') {
                            this.mSocket.pong();
                        } else {
                            self.logToConsole("当前 WebSocket 对象不支持 pong");
                        }
                    }
                };
                return wrapper;
            };
        }
        throw new Error("当前环境不支持 WebSocket");
    }

    connect() {
        this.logToConsole('正在连接 wsURL: ' + this.wsURL);
        this.isManualDisconnect = false; // 重置手动断开标志
        try {
            this.socket = this.webSocketFactory(this.wsURL);
            if (this.socket.onping === undefined) {
                this.socket.onping = (e) => {
                    this.logToConsole("收到 ping, 数据:" + e);
                    try {
                        if (typeof this.socket.pong === 'function') {
                            this.socket.pong();
                        }
                    } catch (err) {
                        this.logToConsole("pong 异常：" + err);
                    }
                };
            }
        } catch (e) {
            this.logToConsole("创建连接失败，2秒后重试，异常：" + e);
            setTimeout(() => {
                if (!this.isManualDisconnect) {
                    this.connect();
                }
            }, 2000);
            return;
        }

        try {
            this.socket.onmessage((event) => {
                try {
                    this.handleSekiroRequest(event.data);
                } catch (ex) {
                    this.logToConsole("处理消息异常：" + ex);
                }
            });
        } catch (e) {
            this.logToConsole("注册 onmessage 异常：" + e);
        }

        try {
            this.socket.onopen((event) => {
                this.logToConsole("成功建立连接, 事件：" + JSON.stringify(event));
            });
        } catch (e) {
            this.logToConsole("注册 onopen 异常：" + e);
        }

        try {
            this.socket.onclose((event) => {
                if (this.isManualDisconnect) {
                    this.logToConsole("连接已手动断开");
                    return;
                }
                this.logToConsole("连接断开, 2秒后重试, 事件：" + JSON.stringify(event));
                setTimeout(() => {
                    if (!this.isManualDisconnect) {
                        this.connect();
                    }
                }, 2000);
            });
        } catch (e) {
            this.logToConsole("注册 onclose 异常：" + e);
        }

        this.socket.onerror = (event) => {
            this.logToConsole("错误事件，详细信息：" + JSON.stringify(event));
        };
    }

    /**
     * 断开 WebSocket 连接
     */
    disconnect() {
        this.logToConsole('正在断开连接...');
        this.isManualDisconnect = true;
        if (this.socket) {
            try {
                this.socket.close();
            } catch (e) {
                this.logToConsole("断开连接异常：" + e);
            }
            this.socket = null;
        }
    }

    handleSekiroRequest(requestJson) {
        let request;
        try {
            request = JSON.parse(requestJson);
        } catch (e) {
            this.logToConsole("JSON 解析失败：" + e);
            return;
        }

        const seq = request['__sekiro_seq__'] || '';
        if (!request['action']) {
            this.sendFailed(seq, '缺少 request 参数 {action}');
            return;
        }
        const action = request['action'];
        if (!this.handlers[action]) {
            this.sendFailed(seq, '未定义 action 处理函数: ' + action);
            return;
        }

        const theHandler = this.handlers[action];
        try {
            theHandler(request, (response) => {
                try {
                    this.sendSuccess(seq, response);
                } catch (e) {
                    this.sendFailed(seq, "响应异常:" + e);
                }
            }, (errorMessage) => {
                this.sendFailed(seq, errorMessage);
            });
        } catch (e) {
            this.logToConsole("执行 action 处理函数异常：" + e);
            this.sendFailed(seq, e.toString());
        }
    }

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

        if (Array.isArray(responseJson) || typeof responseJson === 'string') {
            responseJson = {
                data: responseJson,
                code: 0
            };
        }

        responseJson.code = 0;
        responseJson.status = 0;
        responseJson['__sekiro_seq__'] = seq;
        const responseText = JSON.stringify(responseJson);
        try {
            this.socket.send(responseText);
        } catch (e) {
            this.logToConsole("发送成功消息失败：" + e);
        }
    }

    sendFailed(seq, errorMessage) {
        if (typeof errorMessage !== 'string') {
            try {
                errorMessage = JSON.stringify(errorMessage);
            } catch (e) {
                errorMessage = "未知错误";
            }
        }
        const responseJson = {
            message: errorMessage,
            status: -1,
            '__sekiro_seq__': seq
        };
        const responseText = JSON.stringify(responseJson);
        this.logToConsole("返回失败信息：" + responseText);
        try {
            this.socket.send(responseText);
        } catch (e) {
            this.logToConsole("发送失败消息异常：" + e);
        }
    }

    registerAction(action, handler) {
        if (typeof action !== 'string') {
            throw new Error("action 类型必须为字符串");
        }
        if (typeof handler !== 'function') {
            throw new Error("handler 必须为函数类型");
        }
        this.logToConsole("注册 action: " + action);
        this.handlers[action] = handler;
        return this;
    }
}