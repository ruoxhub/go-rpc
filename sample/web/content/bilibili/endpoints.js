/**
 * Bilibili API 端点定义
 */
window.__bilibili = window.__bilibili || {};

window.__bilibili.Endpoints = {
    // 主机地址
    apiHost: "https://api.bilibili.com",
    domain: "https://www.bilibili.com",

    // 用户认证相关
    nav: "/x/web-interface/nav",

    // 搜索相关
    search: "/search",
    searchVideo: "/x/web-interface/wbi/search/type",

    // 视频相关
    videoDetail: "/x/web-interface/view/detail",
    videoPlayurl: "/x/player/wbi/playurl",
    videoSubtitle: "/x/player/wbi/v2",
    videoInfo: "/x/web-interface/view",

    // 评论相关
    videoCommentMain: "/x/v2/reply/wbi/main",
    videoCommentReply: "/x/v2/reply/reply",

    // 首页推荐
    feedRcmd: "/x/web-interface/wbi/index/top/feed/rcmd",

    // 用户相关
    userInfo: "/x/space/wbi/acc/info",
    userVideos: "/x/space/wbi/arc/search",
    userFans: "/x/relation/fans",
    userFollowings: "/x/relation/followings",
    userDynamics: "/x/polymer/web-dynamic/v1/feed/space",
};

window.__bilibili.SearchOrderType = {
    DEFAULT: "",
    MOST_CLICK: "click",
    LAST_PUBLISH: "pubdate",
    MOST_DANMU: "dm",
    MOST_MARK: "stow"
};

window.__bilibili.CommentOrderType = {
    DEFAULT: 0,
    MIXED: 1,
    TIME: 2
};
