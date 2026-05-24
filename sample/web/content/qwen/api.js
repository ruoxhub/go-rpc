/**
 * qwenai API 调用函数
 * 包括对话、绘图、文件上传等核心功能
 * 支持 V1 和 V2 两个 API 版本
 */
(function() {
    var { Endpoints, Options } = window.__qwenai;
    var { buildHeadersV2,  generateNonce} = window.__qwenai;

    

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
    // window.__qwenai.chatV2 = async function(params) {
    //     var { messages, ticket, options } = params || {};
    //     options = options || {};

    //     if (!messages || !Array.isArray(messages)) {
    //         throw new Error('messages is required and must be an array');
    //     }

    //     var model = options.model || 'Qwen3.5-Plus';
    //     var sessionId = options.sessionId;
    //     var topicId = options.topicId;
    //     var requestId = options.requestId;
    //     var useBaxia = options.useBaxia !== undefined ? options.useBaxia : true;

    //     console.log('[qwenai] chatV2 called:', { messagesCount: messages.length, hasTicket: !!ticket, model: model, useBaxia: useBaxia });

    //     var chatId = requestId || generateNonce(32);
    //     var headers = await buildHeadersV2(ticket, chatId, useBaxia);

    //     var body = {
    //         deep_search: '0',
    //         req_id: requestId || generateNonce(32),
    //         model: model,
    //         scene: 'chat',
    //         session_id: sessionId || generateNonce(32),
    //         sub_scene: 'chat',
    //         temporary: false,
    //         messages: messages.map(function(m) {
    //             return {
    //                 content: m.content,
    //                 mime_type: 'text/plain',
    //                 meta_data: { ori_query: m.content },
    //             };
    //         }),
    //         from: 'default',
    //         topic_id: topicId || generateNonce(32),
    //         parent_req_id: '0',
    //         biz_data: '{"entryPoint":"tongyigw"}',
    //         scene_param: 'first_turn',
    //         chat_client: 'h5',
    //         client_tm: String(Date.now()),
    //         protocol_version: 'v2',
    //         biz_id: 'ai_qwen',
    //     };

    //     var queryParams = buildQueryParams();
    //     var url = Endpoints.chatV2 + '?' + queryParams;

    //     try {
    //         var response = await fetchPost(url, body, headers, Options);
    //         return response;
    //     } catch (error) {
    //         console.error('[qwenai] ChatV2 API error:', error);
    //         throw error;
    //     }
    // };

    /**
     * 对话补全（流式）- V2
     *
     * 返回原始 fetch Response 对象（通过 isParseResponse:false 拿到），
     * 由 BaseClient 的 createStream handler 用 response.body.getReader() 逐 chunk
     * 透传到服务端 invoke_stream 帧，最终走 SSE 输出给调用方。
     *
     * @param {Object} params
     * @param {string} params.messages - 用户输入文本
     * @param {string} [params.model='Qwen3.5-Plus']
     * @param {string} params.chatId - 由 createChat 创建的 chat_id
     * @returns {Promise<Response>}
     */
    window.__qwenai.chatCompletions = async function(params) {
        var { messages, model, chatId} = params || {};
        var model = model || 'qwen3.7-max';
        var headers = await buildHeadersV2();

        var body = {
            stream: true,
            version: '2.1',
            incremental_output: true,
            chat_id: chatId,
            chat_mode: 'normal',
            model: model,
            parent_id: null,
            messages: [{
                fid: generateNonce(32),
                parentId: null,
                childrenIds:[],
                role: 'user',
                content: messages,
                user_action: 'chat',
                files: [],
                timestamp: Math.floor(Date.now() / 1000),
                models: [model],
                chat_type: 't2t',
                feature_config: {
                    thinking_enabled: false,
                    output_schema: 'phase',
                    research_mode: 'normal',
                    auto_thinking: false,
                    thinking_mode: 'Fast',
                },
                extra: { meta: { subChatType: 't2t' } },
                sub_chat_type: 't2t',
                parent_id: null,
            }],
            timestamp: Math.floor(Date.now() / 1000),
        };


        var url = Endpoints.chatsChat + '?' + 'chat_id=' + chatId;

        try {
            // 关键：isParseResponse:false 让 fetchPost 返回原始 Response
            // 而不是 await response.text()，否则流式优势完全消失
            var response = await fetchPost(url, body, headers, Object.assign({}, Options, {
                isParseResponse: false,
            }));
            return response;
        } catch (error) {
            console.error('[qwenai] ChatCompletions stream error:', error);
            throw error;
        }
    };


    /**
     * 新建对话（chat.qwen.ai 站点）
     * @param {Object} params
     * @param {string} params.modelId - 模型 ID（例如 qwen3-max-2025-09-23）
     * @param {string} [params.title='New Chat'] - 对话标题
     * @param {Object} [params.options] - 额外选项
     * @param {string} [params.options.chatMode='normal']
     * @param {string} [params.options.chatType='t2t']
     * @param {string} [params.options.projectId='']
     * @returns {Promise<any>}
     */
    window.__qwenai.createChat = async function(params) {
        var { modelId } = params || {};
        modelId = modelId || "qwen3.6-plus";

        var url = Endpoints.chatsNew || 'https://chat.qwen.ai/api/v2/chats/new';
        var headers = {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'source': 'web'
        };
        var body = {
            title: "新建对话",
            models: [modelId],
            chat_mode: 'normal',
            chat_type: 't2t',
            timestamp: Date.now(),
            project_id: '',
        };

        try {
            var response = await fetchPost(url, body, headers, Options);
            console.log('[qwenai] CreateChat response:', response);
            return response;
        } catch (error) {
            console.error('[qwenai] CreateChat API error:', error);
            throw error;
        }
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
