/**
 * Bilibili WBI 签名加密模块
 */
window.__bilibili = window.__bilibili || {};

/**
 * WBI 签名 key 混合算法
 * @param {string} e - img_key + sub_key 拼接字符串
 * @returns {string} 32 位混合后的 key
 */
window.__bilibili.jB = function(e) {
    var t = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52];
    var n = [];
    t.forEach(function(r) {
        if (e.charAt(r)) {
            n.push(e.charAt(r));
        }
    });
    return n.join("").slice(0, 32);
};

/**
 * 生成 WBI 签名参数 (w_rid + wts)
 * @param {Object} e - 原始请求参数对象
 * @returns {Object|null} { w_rid, wts } 或 null
 */
window.__bilibili.getwrid = function(e) {
    var img_key = window.__bilibili.img_key;
    var sub_key = window.__bilibili.sub_key;
    if (img_key && sub_key) {
        var o = window.__bilibili.jB(img_key + sub_key);
        var i = Math.round(Date.now() / 1e3);
        var a = Object.assign({}, e, { wts: i });
        var s = Object.keys(a).sort();
        var c = [];
        var l = /[!'()*]/g;
        for (var f = 0; f < s.length; f++) {
            var p = s[f];
            var h = a[p];
            if (h && typeof h === "string") {
                h = h.replace(l, "");
            }
            if (h != null) {
                c.push("".concat(encodeURIComponent(p), "=").concat(encodeURIComponent(h)));
            }
        }
        var u = c.join("&");
        return {
            w_rid: MD5(u + o),
            wts: i.toString()
        };
    }
    return null;
};
