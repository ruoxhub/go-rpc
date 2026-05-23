/**
 * qwenai API 调用函数
 * 包括对话、绘图、文件上传等核心功能
 * 支持 V1 和 V2 两个 API 版本
 */
(function() {
    var { Endpoints, Options, MODEL_NAME } = window.__qwenai;
    var { buildHeaders, buildHeadersV2, buildQueryParams, generateNonce, getDeviceId } = window.__qwenai;

    

    // ===== API V2 函数 (chat2.qianwen.com) - 使用 Baxia 签名 =====

    /**
     * 对话补全（非流式）- V2
     * @param {Object} params
     * @param {Array<{role: string, content: string}>} params.messages - 消息列表
     * @param {string} params.ticket - 认证 ticket
     * @param {Object} [params.options] - 额外选项
     * @param {string} [params.options.model='Qwen3.5-Plus']
     * @param {string} [params.options.sessionId]
     * @param {string} [params.options.topicId]
     * @param {string} [params.options.requestId]
     * @param {boolean} [params.options.useBaxia=true]
     * @returns {Promise<any>}
     */
    window.__qwenai.chatV2 = async function(params) {
        var { messages, ticket, options } = params || {};
        options = options || {};

        if (!messages || !Array.isArray(messages)) {
            throw new Error('messages is required and must be an array');
        }

        var model = options.model || 'Qwen3.5-Plus';
        var sessionId = options.sessionId;
        var topicId = options.topicId;
        var requestId = options.requestId;
        var useBaxia = options.useBaxia !== undefined ? options.useBaxia : true;

        console.log('[qwenai] chatV2 called:', { messagesCount: messages.length, hasTicket: !!ticket, model: model, useBaxia: useBaxia });

        var chatId = requestId || generateNonce(32);
        var headers = await buildHeadersV2(ticket, chatId, useBaxia);

        var body = {
            deep_search: '0',
            req_id: requestId || generateNonce(32),
            model: model,
            scene: 'chat',
            session_id: sessionId || generateNonce(32),
            sub_scene: 'chat',
            temporary: false,
            messages: messages.map(function(m) {
                return {
                    content: m.content,
                    mime_type: 'text/plain',
                    meta_data: { ori_query: m.content },
                };
            }),
            from: 'default',
            topic_id: topicId || generateNonce(32),
            parent_req_id: '0',
            biz_data: '{"entryPoint":"tongyigw"}',
            scene_param: 'first_turn',
            chat_client: 'h5',
            client_tm: String(Date.now()),
            protocol_version: 'v2',
            biz_id: 'ai_qwen',
        };

        var queryParams = buildQueryParams();
        var url = Endpoints.chatV2 + '?' + queryParams;

        try {
            var response = await fetchPost(url, body, headers, Options);
            return response;
        } catch (error) {
            console.error('[qwenai] ChatV2 API error:', error);
            throw error;
        }
    };

    /**
     * 对话补全（流式）- V2
     * @param {Object} params
     * @param {Array<{role: string, content: string}>} params.messages - 消息列表
     * @param {string} params.ticket - 认证 ticket
     * @param {Function} params.onChunk - 流式数据回调
     * @param {Object} [params.options] - 额外选项
     * @param {string} [params.options.model='Qwen3.5-Plus']
     * @param {string} [params.options.sessionId]
     * @param {string} [params.options.topicId]
     * @param {string} [params.options.requestId]
     * @param {boolean} [params.options.useBaxia=true]
     * @returns {Promise<void>}
     */
    window.__qwenai.chatStreamV2 = async function(params) {
        var { messages, ticket, onChunk, options } = params || {};
        options = options || {};

        var model = options.model || 'Qwen3.5-Plus';
        var sessionId = options.sessionId;
        var topicId = options.topicId;
        var requestId = options.requestId;
        var useBaxia = options.useBaxia !== undefined ? options.useBaxia : true;

        var chatId = requestId || 'req_' + Date.now() + '_' + Math.random().toString(36).slice(2);
        var headers = await buildHeadersV2(ticket, chatId, useBaxia);

        var body = {
            deep_search: '0',
            req_id: chatId,
            model: model,
            scene: 'chat',
            session_id: sessionId || generateNonce(32),
            sub_scene: 'chat',
            temporary: false,
            messages: messages.map(function(m) {
                return {
                    content: m.content,
                    mime_type: 'text/plain',
                    meta_data: { ori_query: m.content },
                };
            }),
            from: 'default',
            topic_id: topicId || generateNonce(32),
            parent_req_id: '0',
            biz_data: '{"entryPoint":"tongyigw"}',
            scene_param: 'first_turn',
            chat_client: 'h5',
            client_tm: String(Date.now()),
            protocol_version: 'v2',
            biz_id: 'ai_qwen',
        };

        var queryParams = buildQueryParams();
        var url = Endpoints.chatV2 + '?' + queryParams;

        try {
            var controller = new AbortController();
            var timeoutId = setTimeout(function() { controller.abort(); }, Options.timeout);

            var response = await fetch(url, {
                method: 'POST',
                headers: new Headers(headers),
                body: JSON.stringify(body),
                credentials: Options.credentials,
                signal: controller.signal,
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error('HTTP ' + response.status + ' ' + response.statusText);
            }

            var reader = response.body && response.body.getReader();
            if (!reader) {
                throw new Error('Response body is not readable');
            }

            var decoder = new TextDecoder();
            var buffer = '';

            while (true) {
                var result = await reader.read();
                if (result.done) break;

                var chunk = decoder.decode(result.value, { stream: true });
                buffer += chunk;

                var lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (var i = 0; i < lines.length; i++) {
                    var trimmed = lines[i].trim();
                    if (trimmed.startsWith('data: ')) {
                        var data = trimmed.slice(6);
                        if (data === '[DONE]') {
                            return;
                        }
                        try {
                            var parsed = JSON.parse(data);
                            onChunk(parsed);
                        } catch (e) {
                            console.warn('[qwenai] Failed to parse SSE chunk:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('[qwenai] ChatStreamV2 API error:', error);
            throw error;
        }
    };

    /**
     * 获取会话列表 - V2
     * @param {Object} params
     * @param {string} params.ticket - 认证 ticket
     * @param {Object} [params.options] - 分页选项
     * @param {number} [params.options.limit=50]
     * @param {string} [params.options.nextToken='']
     * @param {string} [params.options.sortField='modifiedTime']
     * @param {boolean} [params.options.needFilterTag=true]
     * @returns {Promise<any>}
     */
    window.__qwenai.getSessionListV2 = async function(params) {
        var { ticket, options } = params || {};
        options = options || {};

        var limit = options.limit || 50;
        var nextToken = options.nextToken || '';
        var sortField = options.sortField || 'modifiedTime';
        var needFilterTag = options.needFilterTag !== undefined ? options.needFilterTag : true;

        var chatId = 'list_' + Date.now();
        var headers = await buildHeadersV2(ticket, chatId);

        var queryParams = buildQueryParams();
        var url = Endpoints.sessionListV2 + '?' + queryParams;

        var body = {
            limit: limit,
            next_token: nextToken,
            sort_field: sortField,
            need_filter_tag: needFilterTag,
        };

        try {
            var response = await fetchPost(url, body, headers, Options);
            return response;
        } catch (error) {
            console.error('[qwenai] GetSessionListV2 API error:', error);
            throw error;
        }
    };

    /**
     * 删除会话 - V2
     * @param {Object} params
     * @param {string} params.sessionId - 会话 ID
     * @param {string} params.ticket - 认证 ticket
     * @param {string} [params.requestId] - 请求 ID
     * @returns {Promise<any>}
     */
    window.__qwenai.deleteSessionV2 = async function(params) {
        var { sessionId, ticket, requestId } = params || {};

        var chatId = requestId || 'del_' + Date.now();
        var headers = await buildHeadersV2(ticket, chatId);

        var queryParams = buildQueryParams();
        var url = Endpoints.sessionDelete + '?' + queryParams;

        var body = {
            session_id: sessionId,
        };

        try {
            var response = await fetchPost(url, body, headers, Options);
            return response;
        } catch (error) {
            console.error('[qwenai] DeleteSessionV2 API error:', error);
            throw error;
        }
    };

    /**
     * AI 绘图 - V2
     * @param {Object} params
     * @param {string} params.prompt - 提示词
     * @param {string} params.ticket - 认证 ticket
     * @param {Object} [params.options] - 额外选项
     * @param {string} [params.options.model='wanx2.1']
     * @param {string} [params.options.size='1024x1024']
     * @param {number} [params.options.n=1]
     * @param {string} [params.options.requestId]
     * @returns {Promise<any>}
     */
    window.__qwenai.generateImagesV2 = async function(params) {
        var { prompt, ticket, options } = params || {};
        options = options || {};

        var model = options.model || 'wanx2.1';
        var size = options.size || '1024x1024';
        var n = options.n || 1;
        var requestId = options.requestId;

        var chatId = requestId || 'img_' + Date.now();
        var headers = await buildHeadersV2(ticket, chatId);

        var queryParams = buildQueryParams();
        var url = Endpoints.imagesV2 + '?' + queryParams;

        var body = {
            model: model,
            prompt: prompt,
            n: n,
            size: size,
            response_format: 'url',
        };

        try {
            var response = await fetchPost(url, body, headers, Options);
            return response;
        } catch (error) {
            console.error('[qwenai] GenerateImagesV2 API error:', error);
            throw error;
        }
    };

    /**
     * 检查 Token 状态 - V2
     * @param {Object} params
     * @param {string} params.ticket - 认证 ticket
     * @returns {Promise<any>}
     */
    window.__qwenai.checkTokenLiveV2 = async function(params) {
        var { ticket } = params || {};

        var chatId = 'check_' + Date.now();
        var headers = await buildHeadersV2(ticket, chatId);

        try {
            var response = await fetchGet(Endpoints.tokenCheckV2, {}, headers, Options);
            return response;
        } catch (error) {
            console.error('[qwenai] CheckTokenLiveV2 API error:', error);
            throw error;
        }
    };

    /**
     * 获取当前登录的 ticket（从 Cookie 自动获取）
     * @returns {Promise<{ ticket: string|null, ticketType: string|null, message?: string }>}
     */
    window.__qwenai.getTicket = async function() {
        var cookies = document.cookie.split('; ');
        var ticket = null;
        var ticketType = null;

        for (var i = 0; i < cookies.length; i++) {
            var parts = cookies[i].split('=');
            var name = parts[0];
            var value = parts.slice(1).join('=');
            if (name === 'login_aliyunid_ticket') {
                ticket = value;
                ticketType = 'aliyun';
                break;
            }
            if (name === 'tongyi_sso_ticket') {
                ticket = value;
                ticketType = 'sso';
            }
        }

        if (!ticket) {
            return {
                ticket: null,
                ticketType: null,
                message: '未找到 ticket，请先登录 https://www.qianwen.com'
            };
        }

        return {
            ticket: ticket,
            ticketType: ticketType,
            message: '成功获取 ticket'
        };
    };

    /**
     * 获取模型列表
     * @returns {Promise<any>}
     */
    window.__qwenai.getModel = async function() {
        var url = Endpoints.models || "https://chat.qwen.ai/api/models";
        var headers = {
            'Accept': 'application/json, text/plain, */*',
            'source': 'web'
        };
        try {
            var response = await fetchGet(url, {}, headers, Object.assign({}, Options, { responseType: 'json' }));
            return response;
        } catch (error) {
            console.error('[qwenai] GetModel API error:', error);
            throw error;
        }
    };
})();
