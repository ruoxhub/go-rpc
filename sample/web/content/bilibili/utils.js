/**
 * Bilibili 工具函数与配置
 */
window.__bilibili = window.__bilibili || {};

// 从 localStorage 提取 WBI key
window.__bilibili.img_key = localStorage.wbi_img_url ? localStorage.wbi_img_url.split('/').pop().split('.')[0] : '';
window.__bilibili.sub_key = localStorage.wbi_sub_url ? localStorage.wbi_sub_url.split('/').pop().split('.')[0] : '';

// 从 __biliUserFp__ 提取设备指纹参数
var fpResult = null;
if (window.__biliUserFp__) {
    fpResult = window.__biliUserFp__.queryUserLog({
        target: undefined
    });
}
window.__bilibili.dm_img_list = fpResult ? fpResult[0] : '';
window.__bilibili.dm_img_str = fpResult ? fpResult[1] : '';
window.__bilibili.dm_cover_img_str = fpResult ? fpResult[2] : '';
window.__bilibili.dm_img_inter = fpResult ? fpResult[3] : '';

// 默认请求选项
window.__bilibili.Options = {
    timeout: 15000,
    bodyType: 'text',
    responseType: 'json'
};

/**
 * 通用 GET 请求封装
 * @param {string} uri - 相对路径
 * @param {Object|null} params - 查询参数
 * @param {boolean} enable_params_sign - 是否启用 WBI 签名，默认 true
 * @returns {Promise} fetchGet 返回值
 */
window.__bilibili.get = function(uri, params, enable_params_sign) {
    params = params || null;
    if (enable_params_sign === undefined) enable_params_sign = true;
    var Endpoints = window.__bilibili.Endpoints;
    var Options = window.__bilibili.Options;
    var getwrid = window.__bilibili.getwrid;

    var final_uri = uri;
    if (enable_params_sign && params) {
        var signResult = getwrid(params);
        if (signResult) {
            Object.assign(params, signResult);
        }
    }
    if (params instanceof Object) {
        final_uri = uri + "?" + Object.keys(params).map(function(key) {
            return key + "=" + params[key];
        }).join("&");
    }
    return fetchGet(Endpoints.apiHost + final_uri, null, null, Options);
};
