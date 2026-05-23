/**
 * Popup UI - Vanilla JavaScript Implementation
 *
 * Replicates all functionality from the original React popup.tsx component.
 * Manages state, config, platform detection, and UI interactions.
 */

/* global chrome */

/**
 * @typedef {Object} PlatformDef
 * @property {string} id
 * @property {string} name
 * @property {string[]} domains
 * @property {string} defaultUrl
 * @property {string} icon
 */

/**
 * @typedef {Object} StorageConfig
 * @property {string} [wsHost]
 * @property {number} [actionDelay]
 */

/** @type {PlatformDef[]} */
var PLATFORMS = [
    // --- 社交 ---
    { id: 'xhs', name: '小红书', domains: ['xiaohongshu.com'], defaultUrl: 'https://www.xiaohongshu.com', icon: '📕' },
    { id: 'creator-xhs', name: '小红书创作者', domains: ['creator.xiaohongshu.com'], defaultUrl: 'https://creator.xiaohongshu.com', icon: '✍️' },
    { id: 'weibo', name: '微博', domains: ['weibo.com'], defaultUrl: 'https://weibo.com', icon: '📣' },
    { id: 'twitter', name: 'Twitter', domains: ['x.com', 'twitter.com'], defaultUrl: 'https://x.com/home', icon: '🐦' },
    { id: 'facebook', name: 'Facebook', domains: ['facebook.com'], defaultUrl: 'https://www.facebook.com', icon: '👥' },
    { id: 'instagram', name: 'Instagram', domains: ['instagram.com'], defaultUrl: 'https://www.instagram.com', icon: '📸' },
    { id: 'threads', name: 'Threads', domains: ['threads.net'], defaultUrl: 'https://www.threads.net', icon: '🧵' },
    { id: 'reddit', name: 'Reddit', domains: ['reddit.com'], defaultUrl: 'https://www.reddit.com', icon: '👽' },
    { id: 'zhihu', name: '知乎', domains: ['zhihu.com'], defaultUrl: 'https://www.zhihu.com', icon: '💡' },
    { id: 'tieba', name: '百度贴吧', domains: ['tieba.baidu.com'], defaultUrl: 'https://tieba.baidu.com', icon: '📌' },
    { id: 'v2ex', name: 'V2EX', domains: ['v2ex.com'], defaultUrl: 'https://www.v2ex.com', icon: '💬' },
    { id: 'linuxdo', name: 'LinuxDo', domains: ['linux.do'], defaultUrl: 'https://linux.do', icon: '🐧' },
    { id: 'zsxq', name: '知识星球', domains: ['zsxq.com'], defaultUrl: 'https://wx.zsxq.com', icon: '🪐' },
    { id: 'kanxue', name: '看雪论坛', domains: ['bbs.kanxue.com', 'kanxue.com'], defaultUrl: 'https://bbs.kanxue.com', icon: '🔐' },
    { id: '52pojie', name: '52pojie', domains: ['52pojie.cn'], defaultUrl: 'https://www.52pojie.cn', icon: '🔓' },
    { id: 'devto', name: 'DEV Community', domains: ['dev.to'], defaultUrl: 'https://dev.to', icon: '👩‍💻' },
    // --- 工作 ---
    { id: 'zhipin', name: 'Boss 直聘', domains: ['zhipin.com'], defaultUrl: 'https://www.zhipin.com/web/geek/jobs', icon: '💼' },
    { id: 'zhaopin', name: '智联招聘', domains: ['zhaopin.com'], defaultUrl: 'https://www.zhaopin.com', icon: '💼' },
    { id: '51job', name: '51job', domains: ['51job.com'], defaultUrl: 'https://we.51job.com/pc/search', icon: '💼' },
    { id: 'liepin', name: '猎聘', domains: ['liepin.com'], defaultUrl: 'https://www.liepin.com', icon: '💼' },
    { id: 'lagou', name: '拉勾网', domains: ['lagou.com'], defaultUrl: 'https://www.lagou.com', icon: '💼' },
    { id: 'yingjiesheng', name: '应届生', domains: ['yingjiesheng.com'], defaultUrl: 'https://www.yingjiesheng.com', icon: '💼' },
    { id: 'upwork', name: 'Upwork', domains: ['upwork.com'], defaultUrl: 'https://www.upwork.com', icon: '💼' },
    { id: 'indeed', name: 'Indeed', domains: ['indeed.com'], defaultUrl: 'https://www.indeed.com', icon: '💼' },
    { id: 'nowcoder', name: '牛客网', domains: ['nowcoder.com'], defaultUrl: 'https://www.nowcoder.com', icon: '🐮' },
    { id: 'skillsmp', name: 'skillsmp', domains: ['skillsmp.com'], defaultUrl: 'https://skillsmp.com/zh', icon: '🎯' },
    { id: 'github', name: 'GitHub', domains: ['github.com'], defaultUrl: 'https://github.com', icon: '/static/icon/github.png' },
    { id: 'qizhidao', name: '企知道', domains: ['qizhidao.com'], defaultUrl: 'https://qiye.qizhidao.com/company/bbe40c81361b0493142e34501dcb999f.html', icon: '🏢' },
    { id: 'do22', name: 'DO22', domains: ['22.do'], defaultUrl: 'https://22.do', icon: '✅' },
    { id: 'tsgs12315', name: '12315', domains: ['12315.gov.cn'], defaultUrl: 'https://www.12315.gov.cn', icon: '🏛️' },
    // --- 媒体 ---
    { id: 'douyin', name: '抖音', domains: ['douyin.com'], defaultUrl: 'https://www.douyin.com', icon: '🎵' },
    { id: 'dyindex', name: '抖音创作者', domains: ['creator.douyin.com'], defaultUrl: 'https://creator.douyin.com', icon: '🎬' },
    { id: 'dycreator', name: '抖音创作', domains: ['creator.douyin.com'], defaultUrl: 'https://creator.douyin.com', icon: '🎬' },
    { id: 'tiktok', name: 'TikTok', domains: ['tiktok.com'], defaultUrl: 'https://www.tiktok.com', icon: '🎶' },
    { id: 'kuaishou', name: '快手', domains: ['kuaishou.com'], defaultUrl: 'https://www.kuaishou.com', icon: '✋' },
    { id: 'bilibili', name: '哔哩哔哩', domains: ['bilibili.com'], defaultUrl: 'https://space.bilibili.com/8047632', icon: '📺' },
    { id: 'youtube', name: 'YouTube', domains: ['youtube.com'], defaultUrl: 'https://www.youtube.com', icon: '▶️' },
    { id: 'haokan', name: '好看视频', domains: ['haokan.baidu.com'], defaultUrl: 'https://haokan.baidu.com', icon: '🎬' },
    { id: '36kr', name: '36氪', domains: ['36kr.com'], defaultUrl: 'https://www.36kr.com', icon: '📰' },
    { id: 'csdn', name: 'CSDN', domains: ['csdn.net'], defaultUrl: 'https://www.csdn.net', icon: '💻' },
    { id: 'juejin', name: '掘金', domains: ['juejin.cn'], defaultUrl: 'https://juejin.cn', icon: '⛏️' },
    { id: 'weread', name: '微信读书', domains: ['weread.qq.com'], defaultUrl: 'https://weread.qq.com', icon: '📚' },
    { id: 'zlibrary', name: 'Z-Library', domains: ['z-library.im'], defaultUrl: 'https://z-library.im', icon: '📚' },
    { id: 'dblp', name: 'DBLP', domains: ['dblp.org'], defaultUrl: 'https://dblp.org', icon: '📚' },
    { id: 'baidutrend', name: '百度指数', domains: ['index.baidu.com'], defaultUrl: 'https://index.baidu.com', icon: '📊' },
    { id: 'xueqiu', name: '雪球', domains: ['xueqiu.com'], defaultUrl: 'https://xueqiu.com', icon: '❄️' },
    { id: 'ths', name: '同花顺', domains: ['10jqka.com.cn'], defaultUrl: 'https://www.10jqka.com.cn', icon: '📈' },
    { id: 'eastmoney', name: '东方财富', domains: ['eastmoney.com'], defaultUrl: 'https://www.eastmoney.com', icon: '💰' },
    { id: 'polymarket', name: 'PolyMarket', domains: ['polymarket.com'], defaultUrl: 'https://www.polymarket.com', icon: '📈' },
    { id: 'coingecko', name: 'CoinGecko', domains: ['coingecko.com'], defaultUrl: 'https://www.coingecko.com', icon: '🦎' },
    { id: 'jd', name: '京东', domains: ['jd.com'], defaultUrl: 'https://www.jd.com', icon: '🛒' },
    { id: 'taobao', name: '淘宝', domains: ['taobao.com'], defaultUrl: 'https://www.taobao.com', icon: '🛍️' },
    { id: 'goofish', name: '闲鱼', domains: ['goofish.com'], defaultUrl: 'https://www.goofish.com', icon: '🐟' },
    { id: 'amazon', name: 'Amazon', domains: ['amazon.com', 'amazon.co.uk', 'amazon.de', 'amazon.fr', 'amazon.co.jp', 'amazon.ca', 'amazon.it', 'amazon.es', 'amazon.in', 'amazon.com.au', 'amazon.nl', 'amazon.sg', 'amazon.ae'], defaultUrl: 'https://www.amazon.com', icon: '📦' },
    { id: 'ctrip', name: '携程', domains: ['ctrip.com'], defaultUrl: 'https://www.ctrip.com', icon: '✈️' },
    { id: 'brave', name: 'Brave Search', domains: ['search.brave.com'], defaultUrl: 'https://search.brave.com', icon: '🦁' },
    { id: 'duckduckgo', name: 'DuckDuckGo', domains: ['duckduckgo.com'], defaultUrl: 'https://html.duckduckgo.com/html/', icon: '🦆' },
    // --- AI ---
    { id: 'openai', name: 'OpenAI', domains: ['openai.com', 'chatgpt.com'], defaultUrl: 'https://chatgpt.com', icon: '🤖' },
    { id: 'claude', name: 'Claude AI', domains: ['claude.ai'], defaultUrl: 'https://claude.ai/new', icon: '🤖' },
    { id: 'geminiai', name: 'Gemini AI', domains: ['gemini.google.com'], defaultUrl: 'https://gemini.google.com', icon: '🤖' },
    { id: 'notebooklm', name: 'NotebookLM', domains: ['notebooklm.google.com', 'notebooklm.cloud.google.com'], defaultUrl: 'https://notebooklm.google.com', icon: '📓' },
    { id: 'grok', name: 'Grok', domains: ['grok.com'], defaultUrl: 'https://grok.com', icon: '🤖' },
    { id: 'qwenai', name: '通义千问', domains: ['qianwen.com'], defaultUrl: 'https://www.qianwen.com', icon: '🤖' },
    { id: 'doubao', name: '豆包', domains: ['doubao.com'], defaultUrl: 'https://www.doubao.com/chat', icon: '🫘' },
    { id: 'yuanbao', name: '腾讯元宝', domains: ['yuanbao.tencent.com'], defaultUrl: 'https://yuanbao.tencent.com', icon: '🤖' },
    { id: 'kimiai', name: 'Kimi AI', domains: ['kimi.ai'], defaultUrl: 'https://kimi.ai', icon: '🤖' },
    { id: 'glmai', name: 'GLM AI', domains: ['chatglm.cn'], defaultUrl: 'https://chatglm.cn', icon: '🤖' },
    { id: 'minimaxai', name: 'MiniMax', domains: ['minimaxi.com'], defaultUrl: 'https://www.minimaxi.com', icon: '🤖' },
    { id: 'jimeng', name: '即梦AI', domains: ['jimeng.jianying.com'], defaultUrl: 'https://jimeng.jianying.com/ai-tool/generate?type=image&workspace=0', icon: '🎨' },
    { id: 'modelscope', name: '魔搭社区', domains: ['modelscope.cn'], defaultUrl: 'https://modelscope.cn', icon: '🤖' },
    { id: 'huggingface', name: 'HuggingFace', domains: ['huggingface.co'], defaultUrl: 'https://huggingface.co/models', icon: '🤗' },
    // 依赖源
    { id: 'dockerhub', name: 'Docker Hub', domains: ['hub.docker.com'], defaultUrl: 'https://hub.docker.com', icon: '🐳' },
    { id: 'npm', name: 'NPM Registry', domains: ['npmjs.com'], defaultUrl: 'https://www.npmjs.com', icon: '📦' },
    { id: 'pypi', name: 'PyPI', domains: ['pypi.org', 'pypistats.org'], defaultUrl: 'https://pypi.org', icon: '🐍' },
    { id: 'crates', name: 'Crates.io', domains: ['crates.io'], defaultUrl: 'https://crates.io', icon: '📦' },
];

var DEFAULT_WS_HOST = 'ws://127.0.0.1:5612';
var STORAGE_KEY = 'crawler_rpc_config';

// State variables
var status = 'loading'; // 'loading' | 'active' | 'inactive'
var currentPlatform = null; // PlatformDef | null
var wsHost = DEFAULT_WS_HOST;
var actionDelay = 0;
var isSaving = false;
var toastTimer = null;

/**
 * Load config from browser.storage.local
 * @returns {Promise<void>}
 */
function loadConfig() {
    try {
        chrome.storage.local.get([STORAGE_KEY], function (result) {
            if (chrome.runtime && chrome.runtime.lastError) {
                console.error('Failed to load config:', chrome.runtime.lastError);
                return;
            }
            var config = (result && result[STORAGE_KEY]) || {};
            if (config.wsHost) {
                wsHost = config.wsHost;
                var input = document.getElementById('wsHostInput');
                if (input) input.value = wsHost;
            }
            if (typeof config.actionDelay === 'number') {
                actionDelay = config.actionDelay;
                updateDelayUI();
            }
        });
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

/**
 * Save config to browser.storage.local
 * @param {StorageConfig} config
 * @returns {Promise<boolean>}
 */
function saveConfig(config) {
    try {
        var data = {};
        data[STORAGE_KEY] = config;
        chrome.storage.local.set(data, function () {
            if (chrome.runtime && chrome.runtime.lastError) {
                console.error('Failed to save config:', chrome.runtime.lastError);
            }
        });
        return Promise.resolve(true);
    } catch (error) {
        console.error('Failed to save config:', error);
        return Promise.resolve(false);
    }
}

/**
 * Detect platform from URL
 * @param {string|undefined} url
 * @returns {PlatformDef|null}
 */
function detectPlatform(url) {
    if (!url) return null;
    // Firefox 内部页面（about:, moz-extension:）不匹配
    if (url.indexOf('about:') === 0 || url.indexOf('moz-extension:') === 0 || url.indexOf('chrome:') === 0) return null;
    var urlLower = url.toLowerCase();
    for (var i = 0; i < PLATFORMS.length; i++) {
        var p = PLATFORMS[i];
        for (var j = 0; j < p.domains.length; j++) {
            if (urlLower.indexOf(p.domains[j]) !== -1) {
                return p;
            }
        }
    }
    return null;
}

/**
 * Update platform status based on current active tab
 */
function updatePlatformStatus() {
    try {
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            var tab = tabs && tabs[0];
            if (tab && tab.url) {
                var detected = detectPlatform(tab.url);
                currentPlatform = detected;
                status = detected ? 'active' : 'inactive';
                renderStatus();
            } else {
                status = 'inactive';
                renderStatus();
            }
        });
    } catch (error) {
        console.error('Failed to get current tab:', error);
        status = 'inactive';
        renderStatus();
    }
}

/**
 * Render status indicator in the DOM
 */
function renderStatus() {
    var dot = document.querySelector('.status-dot');
    var text = document.querySelector('.status-text');
    var platformTag = document.querySelector('.platform-tag');

    if (dot) {
        dot.className = 'status-dot ' + status;
    }

    if (text) {
        if (status === 'loading') text.textContent = '检测中...';
        else if (status === 'active') text.textContent = '已激活';
        else text.textContent = '未检测到支持的平台';
    }

    if (platformTag) {
        if (currentPlatform) {
            platformTag.style.display = '';
            // Check if icon is an image path or emoji
            if (currentPlatform.icon.indexOf('/') === 0) {
                platformTag.innerHTML = '<span><img src="' + currentPlatform.icon + '" alt="" /></span><span>' + currentPlatform.name + '</span>';
            } else {
                platformTag.innerHTML = '<span>' + currentPlatform.icon + '</span><span>' + currentPlatform.name + '</span>';
            }
        } else {
            platformTag.style.display = 'none';
        }
    }
}

/**
 * Show toast notification
 * @param {string} message
 * @param {'success'|'error'} type
 */
function showToast(message, type) {
    var toastEl = document.getElementById('toastNotification');
    if (!toastEl) return;

    toastEl.textContent = message;
    toastEl.className = 'toast ' + type;
    toastEl.classList.add('show');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
        toastEl.classList.remove('show');
    }, 2500);
}

/**
 * Update delay slider and number input UI
 */
function updateDelayUI() {
    var slider = document.getElementById('actionDelaySlider');
    var numberInput = document.getElementById('delayNumberInput');
    if (slider) slider.value = actionDelay;
    if (numberInput) numberInput.value = actionDelay;

    // Update preset button active states
    var presets = document.querySelectorAll('.delay-preset-btn');
    for (var i = 0; i < presets.length; i++) {
        var val = parseInt(presets[i].getAttribute('data-value'), 10);
        if (val === actionDelay) {
            presets[i].classList.add('active');
        } else {
            presets[i].classList.remove('active');
        }
    }
}

/**
 * Handle save config button click
 */
function handleSaveConfig() {
    if (wsHost.indexOf('ws://') !== 0 && wsHost.indexOf('wss://') !== 0) {
        showToast('地址必须以 ws:// 或 wss:// 开头', 'error');
        return;
    }

    isSaving = true;
    var btn = document.getElementById('saveConfigBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '保存中...';
    }

    saveConfig({ wsHost: wsHost, actionDelay: actionDelay }).then(function (success) {
        isSaving = false;
        if (btn) {
            btn.disabled = false;
            btn.textContent = '保存';
        }

        if (success) {
            showToast('配置已保存 (延迟：' + actionDelay + 'ms)', 'success');
        } else {
            showToast('保存失败，请重试', 'error');
        }
    });
}

/**
 * Handle platform button click
 * @param {string} platformUrl
 */
function handlePlatformClick(platformUrl) {
    try {
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            var tab = tabs && tabs[0];
            if (tab && tab.id) {
                chrome.tabs.update(tab.id, { url: platformUrl }, function () {
                    window.close();
                });
            }
        });
    } catch (error) {
        console.error('Failed to navigate:', error);
        showToast('打开失败，请重试', 'error');
    }
}

/**
 * Handle refresh button click
 */
function handleRefresh() {
    try {
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
            var tab = tabs && tabs[0];
            if (tab && tab.id) {
                chrome.tabs.reload(tab.id, {}, function () {
                    window.close();
                });
            }
        });
    } catch (error) {
        console.error('Failed to refresh:', error);
        showToast('刷新失败，请重试', 'error');
    }
}

/**
 * Handle open platform button click
 */
function handleOpenPlatform() {
    var url = currentPlatform ? currentPlatform.defaultUrl : PLATFORMS[0].defaultUrl;
    handlePlatformClick(url);
}

/**
 * Build platform grid buttons dynamically
 */
function buildPlatformGrid() {
    var grid = document.getElementById('platformGrid');
    if (!grid) return;

    grid.innerHTML = '';
    for (var i = 0; i < PLATFORMS.length; i++) {
        var p = PLATFORMS[i];
        var btn = document.createElement('button');
        btn.className = 'platform-btn';
        if (currentPlatform && currentPlatform.id === p.id) {
            btn.classList.add('active');
        }
        btn.setAttribute('data-platform-url', p.defaultUrl);
        btn.setAttribute('data-platform-id', p.id);
        
        // Check if icon is an image path or emoji
        if (p.icon.indexOf('/') === 0) {
            btn.innerHTML = '<span><img src="' + p.icon + '" alt="" /></span><small>' + p.name + '</small>';
        } else {
            btn.innerHTML = '<span>' + p.icon + '</span><small>' + p.name + '</small>';
        }
        grid.appendChild(btn);
    }
}

/**
 * Initialize all event listeners
 */
function initEventListeners() {
    // Save config button
    var saveBtn = document.getElementById('saveConfigBtn');
    if (saveBtn) saveBtn.addEventListener('click', handleSaveConfig);

    // WebSocket host input
    var wsInput = document.getElementById('wsHostInput');
    if (wsInput) {
        wsInput.addEventListener('input', function (e) {
            wsHost = e.target.value;
        });
    }

    // Delay slider
    var slider = document.getElementById('actionDelaySlider');
    if (slider) {
        slider.addEventListener('input', function (e) {
            actionDelay = parseInt(e.target.value, 10);
            updateDelayUI();
        });
    }

    // Delay number input
    var delayInput = document.getElementById('delayNumberInput');
    if (delayInput) {
        delayInput.addEventListener('input', function (e) {
            var val = parseInt(e.target.value, 10);
            if (!isNaN(val) && val >= 0) {
                actionDelay = val;
                updateDelayUI();
            }
        });
    }

    // Delay preset buttons
    var presetBtns = document.querySelectorAll('.delay-preset-btn');
    for (var i = 0; i < presetBtns.length; i++) {
        presetBtns[i].addEventListener('click', function () {
            var val = parseInt(this.getAttribute('data-value'), 10);
            actionDelay = val;
            updateDelayUI();
        });
    }

    // Platform grid (event delegation)
    var grid = document.getElementById('platformGrid');
    if (grid) {
        grid.addEventListener('click', function (e) {
            var btn = e.target.closest('.platform-btn');
            if (btn) {
                var url = btn.getAttribute('data-platform-url');
                if (url) handlePlatformClick(url);
            }
        });
    }

    // Refresh button
    var refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', handleRefresh);

    // Open platform button
    var openBtn = document.getElementById('openBtn');
    if (openBtn) openBtn.addEventListener('click', handleOpenPlatform);
}

/**
 * Initialize popup on DOM ready
 */
function init() {
    loadConfig();
    buildPlatformGrid();
    initEventListeners();
    updatePlatformStatus();
}

// Run when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
