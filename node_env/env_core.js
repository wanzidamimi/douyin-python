/**
 * env_core.js —— 浏览器环境补底（借鉴 JdApis 的 Proxy 引擎手法）
 *
 * 归属：项目自写。目的：让抖音官方 webmssdk.es5.js 在 Node 里可运行，
 * 不逆向其签名算法，只提供它读取的 window/document/navigator/canvas 等环境。
 *
 * 手法要点（与 skill 一致）：
 *  - 所有缺失属性用 Proxy 兜底返回 noop 函数 / 空对象，避免 SDK 读取即崩；
 *  - navigator / screen / document 等关键对象给出与真实 Chrome 一致的固定指纹；
 *  - setFuncNative 让补丁函数 toString() 返回 "function xxx() { [native code] }"，
 *    骗过 SDK 对原生函数的检测；
 *  - document.currentScript.src / filename 伪装成官方 CDN URL。
 */
'use strict';

const CDN_URL = 'https://lf-c-flwb.bytetos.com/obj/rc-client-security/c-webmssdk/1.0.0.53/webmssdk.es5.js';

function setFuncNative(fn, name) {
  Object.defineProperty(fn, 'toString', {
    value: function () {
      return 'function ' + (name || fn.name || '') + '() { [native code] }';
    },
    configurable: true,
  });
  return fn;
}

function noop() {}
setFuncNative(noop, 'noop');

/** 深度 Proxy：任何属性读取都返回可继续访问的兜底值 */
function deepProxy(target, label) {
  return new Proxy(target || {}, {
    get(t, p) {
      if (p in t) return t[p];
      if (p === Symbol.toPrimitive) return () => '';
      if (p === 'toString' || p === 'valueOf') return () => '';
      if (p === 'then') return undefined; // 避免被当成 thenable
      if (p === Symbol.iterator) return undefined;
      // 函数名带 getX / isX / hasX 的当布尔或字符串兜底
      const s = String(p);
      if (/^is|^has|^can/.test(s)) return false;
      if (/^get/.test(s)) return noop;
      return deepProxy({}, label + '.' + s);
    },
    set(t, p, v) { t[p] = v; return true; },
    has(t, p) { return p in t; }, // 不能恒 true：SDK 用 `if(!window.byted_acrawler)` 判断是否初始化
    apply() { return undefined; },
  });
}

function makeNavigator() {
  const nav = {
    appName: 'Netscape',
    appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
    platform: 'Win32',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh', 'en-US', 'en'],
    hardwareConcurrency: 16,
    deviceMemory: 32,
    vendor: 'WebKit',
    maxTouchPoints: 0,
    webdriver: false,
    vendor: 'WebKit',
    plugins: { length: 0, item: () => null, namedItem: () => null },
    mimeTypes: { length: 0, item: () => null, namedItem: () => null },
    cookieEnabled: true,
    onLine: true,
    doNotTrack: null,
    sendBeacon: setFuncNative(() => true, 'sendBeacon'),
    permissions: { query: () => Promise.resolve({ state: 'prompt' }) },
    javaEnabled: () => false,
  };
  return deepProxy(nav, 'navigator');
}

function makeScreen() {
  return deepProxy({
    width: 2048, height: 1152, availWidth: 2048, availHeight: 1152,
    colorDepth: 24, pixelDepth: 24, screenX: 0, screenY: 0,
  }, 'screen');
}

function makeLocation() {
  return deepProxy({
    href: 'https://live.douyin.com/',
    protocol: 'https:', host: 'live.douyin.com', hostname: 'live.douyin.com',
    origin: 'https://live.douyin.com', pathname: '/', search: '', hash: '', port: '',
  }, 'location');
}

function makeStorage() {
  const m = new Map();
  return deepProxy({
    getItem: setFuncNative((k) => (m.has(String(k)) ? m.get(String(k)) : null), 'getItem'),
    setItem: setFuncNative((k, v) => { m.set(String(k), String(v)); }, 'setItem'),
    removeItem: setFuncNative((k) => { m.delete(String(k)); }, 'removeItem'),
    clear: setFuncNative(() => m.clear(), 'clear'),
    key: setFuncNative((i) => Array.from(m.keys())[i] || null, 'key'),
    get length() { return m.size; },
  }, 'storage');
}

function makeCanvas() {
  const ctx2d = deepProxy({
    fillRect: noop, clearRect: noop, drawImage: noop, fillText: noop,
    getImageData: () => ({ data: new Uint8ClampedArray(4), width: 1, height: 1 }),
    measureText: () => ({ width: 10 }),
    createLinearGradient: () => ({ addColorStop: noop }),
    canvas: null,
  }, 'ctx2d');
  const canvas = deepProxy({
    width: 300, height: 150,
    getContext: setFuncNative((type) => (type === '2d' ? ctx2d : null), 'getContext'),
    toDataURL: setFuncNative(() => 'data:image/png;base64,iVBORw0KGgo=', 'toDataURL'),
  }, 'canvas');
  ctx2d.canvas = canvas;
  return canvas;
}

/** 构造一个足够可信的 window + document */
function buildEnv(options) {
  options = options || {};
  const ua = options.userAgent || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36';

  const win = {};
  win.window = win;
  win.self = win;
  win.globalThis = win;
  win.top = win;
  win.parent = win;
  win.frames = win;
  win.length = 1;

  const document = deepProxy({
    characterSet: 'UTF-8', charset: 'UTF-8',
    compatMode: 'CSS1Compat',
    contentType: 'text/html',
    readyState: 'complete',
    title: '',
    referrer: 'https://www.douyin.com/',
    URL: 'https://live.douyin.com/',
    documentElement: deepProxy({ clientWidth: 2048, clientHeight: 1152 }, 'html'),
    body: deepProxy({}, 'body'),
    head: deepProxy({}, 'head'),
    cookie: options.cookie || '',
    currentScript: { src: CDN_URL },
    createElement: setFuncNative((tag) => (String(tag).toLowerCase() === 'canvas' ? makeCanvas() : deepProxy({}, 'el:' + tag)), 'createElement'),
    getElementsByTagName: setFuncNative(() => [], 'getElementsByTagName'),
    getElementById: setFuncNative(() => null, 'getElementById'),
    addEventListener: setFuncNative(noop, 'addEventListener'),
    removeEventListener: setFuncNative(noop, 'removeEventListener'),
    querySelector: setFuncNative(() => null, 'querySelector'),
    querySelectorAll: setFuncNative(() => [], 'querySelectorAll'),
    hasFocus: setFuncNative(() => true, 'hasFocus'),
    visibilityState: 'visible',
    hidden: false,
  }, 'document');

  const nav = makeNavigator();
  nav.userAgent = ua;
  nav.appVersion = ua.replace('Mozilla/', '');

  Object.assign(win, {
    document,
    navigator: nav,
    location: makeLocation(),
    screen: makeScreen(),
    localStorage: makeStorage(),
    sessionStorage: makeStorage(),
    innerWidth: 2048, innerHeight: 1152,
    outerWidth: 2048, outerHeight: 1152,
    screenX: 0, screenY: 0,
    devicePixelRatio: 1.25,
    scrollX: 0, scrollY: 0,
    performance: { now: setFuncNative(() => Date.now(), 'now'), timing: deepProxy({}, 'timing'), getEntriesByType: () => [] },
    crypto: globalThis.crypto || { getRandomValues: (a) => { for (let i = 0; i < a.length; i++) a[i] = Math.floor(Math.random() * 256); return a; } },
    addEventListener: setFuncNative(noop, 'addEventListener'),
    removeEventListener: setFuncNative(noop, 'removeEventListener'),
    dispatchEvent: setFuncNative(() => true, 'dispatchEvent'),
    setTimeout, clearTimeout, setInterval, clearInterval,
    Promise, JSON, Math, Date, Map, Set, Array, Object, String, Number, Boolean,
    Uint8Array, Uint8ClampedArray, ArrayBuffer, TextEncoder, TextDecoder,
    atob: setFuncNative((s) => Buffer.from(s, 'base64').toString('binary'), 'atob'),
    btoa: setFuncNative((s) => Buffer.from(s, 'binary').toString('base64'), 'btoa'),
    XMLHttpRequest: function () {},
    WebSocket: function () {},
    fetch: () => Promise.reject(new Error('network disabled in env')),
    requestAnimationFrame: (cb) => setTimeout(cb, 16),
    Image: function () {},
  });

  // WebGL: 固定显卡型号，避免 SwiftShader 特征
  const gl = deepProxy({
    getParameter: setFuncNative((p) => {
      const VENDOR = 0x1F00, RENDERER = 0x1F01, VERSION = 0x1F02;
      if (p === VENDOR) return 'WebKit';
      if (p === RENDERER) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 (0x00002882) Direct3D11 vs_5_0 ps_5_0, D3D11)';
      if (p === VERSION) return 'WebGL 1.0 (OpenGL ES 2.0 Chromium)';
      return 1;
    }, 'getParameter'),
    getExtension: setFuncNative((n) => (String(n).indexOf('debug_renderer_info') > -1 ? { UNMASKED_VENDOR_WEBGL: 0x9245, UNMASKED_RENDERER_WEBGL: 0x9246 } : null), 'getExtension'),
    getSupportedExtensions: setFuncNative(() => [], 'getSupportedExtensions'),
  }, 'gl');
  const origGetContext = win.document.createElement('canvas').getContext;
  win.HTMLCanvasElement = function () {};
  win.WebGLRenderingContext = function () {};
  win.__GL = gl;

  // 让 getContext('webgl') 返回伪造 gl
  const canvasFactory = (tag) => {
    if (String(tag).toLowerCase() === 'canvas') {
      const c = makeCanvas();
      const orig = c.getContext;
      c.getContext = setFuncNative((type) => {
        if (type === '2d') return orig(type);
        return gl;
      }, 'getContext');
      return c;
    }
    return deepProxy({}, 'el:' + tag);
  };
  document.createElement = setFuncNative(canvasFactory, 'createElement');

  // 暴露真实裸对象：SDK 的 window.byted_acrawler 导出要写到裸对象上，
  // 经过 Proxy 的 get/has 会被兜底逻辑干扰（尤其 `if(!window.byted_acrawler)` 初始化判断）。
  win.__raw = win;
  return deepProxy(win, 'window');
}

module.exports = { buildEnv, setFuncNative, deepProxy, CDN_URL };
