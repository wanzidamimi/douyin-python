/**
 * probe_sdk.js —— 在补环境里加载 bdms/secsdk/runtime，探查导出与初始化行为
 * 这是研究脚本，用于确定设备指纹生成链路。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildEnv, CDN_URL } = require('./env_core');

const V = path.join(__dirname, '..', 'vendor');

function makeSandbox() {
  const env = buildEnv();
  const winRaw = env.__raw || env;
  const ctx = {};
  ctx.window = winRaw;
  ctx.self = winRaw;
  ctx.globalThis = ctx;
  ctx.document = winRaw.document;
  ctx.navigator = winRaw.navigator;
  ctx.location = winRaw.location;
  ctx.screen = winRaw.screen;
  ctx.localStorage = winRaw.localStorage;
  ctx.sessionStorage = winRaw.sessionStorage;
  ctx.performance = winRaw.performance;
  ctx.crypto = winRaw.crypto;
  ctx.atob = winRaw.atob;
  ctx.btoa = winRaw.btoa;
  ctx.Image = winRaw.Image;
  ctx.XMLHttpRequest = winRaw.XMLHttpRequest;
  ctx.WebSocket = winRaw.WebSocket;
  ctx.requestAnimationFrame = winRaw.requestAnimationFrame;
  ctx.setTimeout = setTimeout;
  ctx.clearTimeout = clearTimeout;
  ctx.setInterval = setInterval;
  ctx.clearInterval = clearInterval;
  ctx.Promise = Promise;
  ctx.console = console;
  ctx.Buffer = Buffer;
  ctx.exports = {};   // secsdk UMD 的 CommonJS 出口
  ctx.module = { exports: ctx.exports };
  ctx.define = undefined;
  // 补齐 JS 全局算术/编码函数（SDK 直接引用）
  ['parseInt','parseFloat','isNaN','isFinite','encodeURIComponent','decodeURIComponent',
   'encodeURI','decodeURI','escape','unescape','Uint8Array','Uint16Array','Int32Array',
   'Float64Array','DataView','TextEncoder','TextDecoder','RegExp','Error','TypeError',
   'Symbol','Reflect','Proxy','WeakMap','WeakSet'].forEach(k => { try { ctx[k] = globalThis[k]; } catch(e){} });
  // 捕获脚本发出的网络请求
  ctx.__netCalls = [];
  ctx.fetch = function (url, init) {
    ctx.__netCalls.push({ type: 'fetch', url: String(url), init: init && { method: init.method, body: String(init.body || '').slice(0, 120) } });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}), text: () => Promise.resolve(''), headers: { get: () => null } });
  };
  winRaw.fetch = ctx.fetch;
  const sandbox = vm.createContext(ctx, { name: 'probe' });
  return { ctx, sandbox, winRaw };
}

function load(file, sandbox) {
  try {
    vm.runInContext(fs.readFileSync(path.join(V, file), 'utf8'), sandbox, { filename: 'https://lf-security.bytegoofy.com/obj/security-secsdk/' + file });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e && e.stack || e).slice(0, 400) };
  }
}

const { ctx, sandbox, winRaw } = makeSandbox();

// 1) runtime-stable（策略引擎）
let r = load('runtime-stable.js', sandbox);
console.log('runtime-stable:', JSON.stringify(r));

// 2) bdms
r = load('bdms.js', sandbox);
console.log('bdms:', JSON.stringify(r));
console.log('window.bdms keys:', ctx.window.bdms ? Object.keys(ctx.window.bdms) : null);
if (ctx.window.bdms && typeof ctx.window.bdms.init === 'function') {
  console.log('bdms.init.length =', ctx.window.bdms.init.length);
  console.log('bdms.init.toString().slice =', ctx.window.bdms.init.toString().slice(0, 300));
}

// 3) secsdk (UMD -> exports.csrf)
r = load('secsdk-lastest.umd.js', sandbox);
console.log('secsdk:', JSON.stringify(r));
// UMD 在 sandbox 顶层 exports
console.log('secsdk exports.csrf:', ctx.exports && ctx.exports.csrf ? Object.keys(ctx.exports.csrf) : 'N/A');
// 调 bdms.init() 触发生成指纹
console.log('--- calling bdms.init() ---');
const configs = [
  { aid: 6383 },
  { aid: '6383' },
  { aid: 6383, app_name: 'douyin_web', device_platform: 'web' },
];
for (const cfg of configs) {
  try {
    const ret = ctx.window.bdms.init && ctx.window.bdms.init(cfg);
    console.log('bdms.init(' + JSON.stringify(cfg) + ') ret:', String(ret).slice(0, 200));
  } catch (e) {
    console.log('bdms.init(' + JSON.stringify(cfg) + ') error:', String(e && e.message || e).slice(0, 160));
  }
}
setTimeout(() => {
  console.log('netCalls:', JSON.stringify(ctx.__netCalls).slice(0, 1500));
  console.log('cookies now:', String(winRaw.document.cookie).slice(0, 500));
  // 探查 bdms 对象全部属性（含不可枚举）
  console.log('bdms all props:', Object.getOwnPropertyNames(ctx.window.bdms || {}));
  console.log('window fp keys:', Object.keys(winRaw).filter(k => /fp|uifid|device|secsdk|bdms/i.test(k)));
}, 3000);
