/**
 * Bilibili API 操作：用户、视频、评论、字幕等
 */
window.__bilibili = window.__bilibili || {};

(function() {
    var Endpoints = window.__bilibili.Endpoints;
    var Options = window.__bilibili.Options;
    var get = window.__bilibili.get;
    var CommentOrderType = window.__bilibili.CommentOrderType;
    var dm_img_list = window.__bilibili.dm_img_list;
    var dm_img_str = window.__bilibili.dm_img_str;
    var dm_cover_img_str = window.__bilibili.dm_cover_img_str;
    var dm_img_inter = window.__bilibili.dm_img_inter;

    /**
     * 获取用户信息
     * @param {Object} params - 参数
     * @param {string} params.user_id - 用户 MID
     */
    async function getUserInfo(params) {
        var user_id = (params || {}).user_id;
        var requestParams = {
            "mid": user_id,
            "token": "",
            "platform": "web",
            "web_location": "1550101",
            "dm_img_list": dm_img_list,
            "dm_img_str": dm_img_str,
            "dm_cover_img_str": dm_cover_img_str,
            "dm_img_inter": dm_img_inter
        };
        return get(Endpoints.userInfo, requestParams);
    }

    /**
     * 获取用户视频列表
     * @param {Object} params - 参数
     * @param {string} params.user_id - 用户 MID
     * @param {string} [params.order=pubdate] - 排序方式
     * @param {string} [params.ps=25] - 每页数量
     * @param {string} [params.pn=1] - 页码
     */
    async function getUserVideos(params) {
        var p = params || {};
        var user_id = p.user_id;
        var order = p.order || "pubdate";
        var ps = p.ps || "25";
        var pn = p.pn || "1";
        var requestParams = {
            "mid": user_id,
            "order": order,
            "ps": ps,
            "pn": pn,
            "index": "1",
            "order_avoided": "true",
            "platform": "web",
            "web_location": "333.1387",
            "dm_img_list": dm_img_list,
            "dm_img_str": dm_img_str,
            "dm_cover_img_str": dm_cover_img_str,
            "dm_img_inter": dm_img_inter
        };
        return get(Endpoints.userVideos, requestParams);
    }

    /**
     * 获取视频评论
     * @param {Object} params - 参数
     * @param {string} params.video_id - 视频 OID
     * @param {number} [params.order_mode=0] - 评论排序模式
     * @param {number} [params.ps=20] - 每页数量
     * @param {number} [params.next=0] - 分页游标
     */
    async function getVideoComment(params) {
        var p = params || {};
        var video_id = p.video_id;
        var order_mode = p.order_mode || CommentOrderType.DEFAULT;
        var ps = p.ps || 20;
        var next = p.next || 0;
        var post_data = {
            "oid": video_id,
            "mode": order_mode,
            "type": 1,
            "ps": ps,
            "next": next
        };
        return get(Endpoints.videoCommentMain, post_data);
    }

    /**
     * 获取视频字幕
     * @param {Object} params - 参数
     * @param {string} params.aid - 视频 AID
     * @param {string} params.cid - 视频 CID
     * @returns {string|null} ai-zh 字幕 URL
     */
    async function getVideoSubtitle(params) {
        var p = params || {};
        var aid = p.aid;
        var cid = p.cid;
        var requestParams = {
            "aid": aid,
            "cid": cid,
            "isGaiaAvoided": false,
            "web_location": 1315873,
            "dm_img_list": dm_img_list,
            "dm_img_str": dm_img_str,
            "dm_cover_img_str": dm_cover_img_str,
            "dm_img_inter": dm_img_inter
        };
        var response = await get(Endpoints.videoSubtitle, requestParams);
        var subtitleURL;
        if (response && response.data && response.data.subtitle && response.data.subtitle.subtitles) {
            response.data.subtitle.subtitles.forEach(function(item) {
                if (item.lan === "ai-zh") {
                    subtitleURL = "https:" + item.subtitle_url;
                }
            });
        }
        return subtitleURL;
    }

    /**
     * 获取视频信息
     * @param {Object} params - 参数
     * @param {string} params.bvid - 视频 BVID
     */
    function getVideoInfo(params) {
        var bvid = (params || {}).bvid;
        var requestParams = {
            "bvid": bvid
        };
        return get(Endpoints.videoInfo, requestParams, false);
    }

    /**
     * 获取首页推荐视频流
     * @param {Object} params - 参数
     * @param {number} [params.ps=12] - 每页数量
     * @param {number} [params.fresh_idx=1] - 刷新索引
     * @param {number} [params.fresh_idx_1h=1] - 1小时内刷新索引
     * @param {number} [params.brush=1] - 刷新次数
     * @param {number} [params.fetch_row=4] - 拉取行数
     * @param {string} [params.fresh_type=4] - 刷新类型
     * @param {string} [params.feed_version=V8] - feed版本
     * @param {string} [params.last_showlist] - 上次展示的视频列表，用于去重
     * @param {number} [params.y_num=4] - y轴数量
     * @param {number} [params.last_y_num=5] - 上次y轴数量
     */
    async function getFeedRcmd(params) {
        var p = params || {};
        var requestParams = {
            "web_location": "1430650",
            "y_num": p.y_num || 4,
            "fresh_type": p.fresh_type || 4,
            "feed_version": p.feed_version || "V8",
            "fresh_idx_1h": p.fresh_idx_1h || 1,
            "fetch_row": p.fetch_row || 4,
            "fresh_idx": p.fresh_idx || 1,
            "brush": p.brush || 1,
            "homepage_ver": 1,
            "ps": p.ps || 12,
            "last_y_num": p.last_y_num || 5,
            "screen": p.screen || "",
            "seo_info": "",
            "last_showlist": p.last_showlist || "",
            "uniq_id": p.uniq_id || ""
        };
        return get(Endpoints.feedRcmd, requestParams);
    }

    /**
     * 获取用户内容（别名 getUserVideos）
     */
    function getContent(params) {
        return getUserVideos(params);
    }

    /**
     * 获取评论（别名 getVideoComment）
     * @param {Object} params - 参数
     * @param {string} params.content_id - 内容 ID
     */
    function getComment(params) {
        var content_id = (params || {}).content_id;
        return getVideoComment({ video_id: content_id });
    }

    // 暴露到 window.__bilibili
    window.__bilibili.getUserInfo = getUserInfo;
    window.__bilibili.getUserVideos = getUserVideos;
    window.__bilibili.getVideoComment = getVideoComment;
    window.__bilibili.getVideoSubtitle = getVideoSubtitle;
    window.__bilibili.getVideoInfo = getVideoInfo;
    window.__bilibili.getContent = getContent;
    window.__bilibili.getComment = getComment;
    window.__bilibili.getFeedRcmd = getFeedRcmd;
})();
