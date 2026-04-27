(function () {
    'use strict';

    if (window.location.hostname !== 'skillsmp.com' && !window.location.hostname.includes('skillsmp.com')) {
        return;
    }
    const Endpoints = {
        domain: "https://skillsmp.com",
        api: "https://skillsmp.com/api/skills"
    }

    const Options = {
        timeout: 15000,
        bodyType: 'text'
    }

    function getSkills(params) {
        var { page = 1, limit = 12, sortBy = "stars", search, domain } = params || {};
        var requestData = {
            'page': page,
            'limit': limit,
            'sortBy': sortBy
        }
        if (search) {
            requestData.search = search;
        }
        if (domain) {
            requestData.domain = domain;
        }

        console.log('[getSkills] 发起请求:', Endpoints.api, requestData);

        return fetchGet(Endpoints.api, requestData, null, Options)
            .then(response => {
                console.log('[getSkills] 响应成功:', response);
                return response;
            })
            .catch(error => {
                console.error('[getSkills] 请求失败:', error);
                throw error;
            });
    }
    BaseClient.create({
        platform: 'skillsmp',
        hostnames: 'skillsmp.com',
        logPrefix: 'skillsmp Extractor',
        endpoints: Endpoints,

        // Action 配置 - 声明式定义，自动处理参数提取和错误处理
        actions: {
            getSkills: createAction(getSkills),
        }
    });

})();