/**
 * sign_full.js —— 完整安全栈补环境签名器
 * 加载顺序按真机：runtime.js -> config/project/strategy -> bdms -> webmssdk
 * 目标是让 webmssdk 在与真机一致的策略配置下产出被服务端认可的签名。
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildEnv, CDN_URL } = require('./env_core');
const V = path.join(__dirname, '..', 'vendor');

function buildSandbox(options) {
  options = options || {};
  const env = buildEnv();
  const winRaw = env.__raw || env;
  // runtime.js 读取 document.currentScript.getAttribute('nonce'/'src')
  try {
    winRaw.document.currentScript = {
      src: 'https://lf-security.bytegoofy.com/obj/security-secsdk/runtime.js',
      getAttribute: function (k) { return k === 'nonce' ? '' : (k === 'src' ? this.src : null); },
      setAttribute: function () {},
    };
  } catch (e) {}
  const ctx = {};
  ctx.window = winRaw;
  ctx.self = winRaw;
  ctx.globalThis = ctx;
  // 策略模块注册系统（真机存在）
  const modules = {};
  ctx.__securityModules = modules;
  ctx.registToModule = function (name, data) { modules[name] = data; winRaw['__mod_' + name] = data; };
  ctx.registToGlobal = function (name, data) { winRaw[name] = data; };
  winRaw.registToModule = ctx.registToModule;
  winRaw.registToGlobal = ctx.registToGlobal;
  winRaw.securitySDK = winRaw.securitySDK || {};
  for (const k of ['document','navigator','location','screen','localStorage','sessionStorage',
                    'performance','crypto','atob','btoa','Image','XMLHttpRequest','WebSocket',
                    'requestAnimationFrame']) {
    ctx[k] = winRaw[k];
  }
  ctx.setTimeout = setTimeout; ctx.clearTimeout = clearTimeout;
  ctx.setInterval = setInterval; ctx.clearInterval = clearInterval;
  ctx.Promise = Promise; ctx.console = console; ctx.Buffer = Buffer;
  // 时区对齐真机（Asia/Hong_Kong），webmssdk 可能读 Intl 做环境 attestation
  const RealIntl = globalThis.Intl;
  ctx.Intl = {
    DateTimeFormat: function () {
      return { resolvedOptions: function () { return { timeZone: 'Asia/Hong_Kong', locale: 'zh-CN' }; } };
    },
    NumberFormat: RealIntl.NumberFormat,
    Collator: RealIntl.Collator,
    supportedValuesOf: RealIntl.supportedValuesOf && RealIntl.supportedValuesOf.bind(RealIntl),
  };
  ctx.exports = {}; ctx.module = { exports: ctx.exports }; ctx.define = undefined;
  ['parseInt','parseFloat','isNaN','isFinite','encodeURIComponent','decodeURIComponent',
   'encodeURI','decodeURI','escape','unescape','Uint8Array','Uint16Array','Int32Array',
   'Float64Array','DataView','TextEncoder','TextDecoder','RegExp','Error','TypeError',
   'Symbol','Reflect','Proxy','WeakMap','WeakSet'].forEach(k => { try { ctx[k] = globalThis[k]; } catch(e){} });
  ctx.fetch = function (url, init) { return Promise.resolve({ ok:true, status:200, headers:{get:()=>null}, json:()=>Promise.resolve({}), text:()=>Promise.resolve('') }); };
  winRaw.fetch = ctx.fetch;
  ctx.__netCalls = [];
  const sandbox = vm.createContext(ctx, { name: 'douyin-full' });
  return { ctx, sandbox, winRaw };
}

function load(file, sandbox, url) {
  try {
    vm.runInContext(fs.readFileSync(path.join(V, file), 'utf8'), sandbox,
      { filename: url || ('https://lf-security.bytegoofy.com/obj/security-secsdk/' + file) });
    return true;
  } catch (e) {
    console.error('LOAD_FAIL', file, String(e && e.message || e).slice(0, 160));
    return false;
  }
}

function loadAll(options) {
  options = options || {};
  const { ctx, sandbox, winRaw } = buildSandbox(options);
  // 在 SDK 加载前注入真机 localStorage（证书/设备 uid 等签名绑定值）
  if (options.localStorage) {
    for (const k of Object.keys(options.localStorage)) {
      try { winRaw.localStorage.setItem(k, String(options.localStorage[k])); } catch (e) {}
    }
  }
  // 1) webmssdk 先加载：临时移除 exports/module 迫使 UMD 走 global 分支导出 byted_acrawler
  const _ex = ctx.exports, _mo = ctx.module, _df = ctx.define;
  ctx.exports = undefined; ctx.module = undefined; ctx.define = undefined;
  load('webmssdk.es5.js', sandbox, CDN_URL);
  ctx.exports = _ex; ctx.module = _mo; ctx.define = _df;
  // 2) 策略引擎 + 配置（增强签名行为）
  load('runtime.js', sandbox);
  load('config_39.js', sandbox);
  load('project_39.js', sandbox);
  load('strategy_39.js', sandbox);
  // 3) bdms + secsdk
  load('bdms.js', sandbox);
  load('secsdk-lastest.umd.js', sandbox);
  const acrawler = ctx.byted_acrawler || ctx.window.byted_acrawler || {};
  if (typeof acrawler.frontierSign !== 'function') {
    console.error('DEBUG acrawler typeof:', typeof acrawler, 'keys:', typeof acrawler === 'object' ? Object.keys(acrawler) : acrawler);
    console.error('DEBUG ctx byted_acrawler:', typeof ctx.byted_acrawler, 'window:', typeof ctx.window.byted_acrawler);
  }
  return { ctx, sandbox, winRaw, acrawler };
}

if (require.main === module && !process.argv.includes('--rpc')) {
  const { ctx, acrawler, winRaw } = loadAll();
  console.log('modules registered:', Object.keys(ctx.__securityModules));
  console.log('acrawler methods:', typeof acrawler.frontierSign === 'function' ? Object.keys(acrawler) : 'NO frontierSign');
  if (typeof acrawler.frontierSign === 'function') {
    const stub = '3c9dd677b84ecbd279eeebe6c01da71a';
    const r = acrawler.frontierSign({ 'X-MS-STUB': stub });
    console.log('signature:', JSON.stringify(r));
  }
  console.log('cookies:', String(winRaw.document.cookie).slice(0, 200));
}

module.exports = { loadAll, buildSandbox };

// JSON-RPC 模式（与 sign.js 同协议），mode=full 用完整策略栈
if (process.argv.includes('--rpc')) {
  let stack = null;
  let acrawler = null;
  let seedLS = null;  // 首个请求带来的真机 localStorage，供加载前注入
  function ensure() {
    if (acrawler && typeof acrawler.frontierSign === 'function') return;
    stack = loadAll({ localStorage: seedLS });
    acrawler = stack.acrawler;
  }
  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line) continue;
      let req;
      try { req = JSON.parse(line); } catch (e) { continue; }
      try {
        // 首个请求携带真机 localStorage，必须在 SDK 加载前保存
        if (req.params && req.params.localStorage && !stack) seedLS = req.params.localStorage;
        ensure();
        let result;
        if (req.method === 'sign') {
          // 若提供 ttwid，先注入签名运行时（真机 setTTWid 把 ttwid 写入签名状态）
          // 完整对齐真机初始化顺序：init -> setTTWid -> setTTWebid -> setConfig
          if (req.params.webid && typeof acrawler.setTTWebid === 'function') {
            acrawler.setTTWebid(String(req.params.webid));
          }
          if (req.params.ttwid && typeof acrawler.setTTWid === 'function') {
            acrawler.setTTWid(String(req.params.ttwid));
          }
          if (req.params.init && typeof acrawler.init === 'function') {
            try { acrawler.init(req.params.init); } catch (e) {}
          }
          const r = acrawler.frontierSign({ 'X-MS-STUB': String(req.params.stub) });
          result = { 'X-Bogus': r['X-Bogus'], source: 'webmssdk-full-stack' };
        } else if (req.method === 'ping') result = { pong: true };
        else throw new Error('unknown method ' + req.method);
        process.stdout.write(JSON.stringify({ id: req.id, ok: true, result }) + '\n');
      } catch (e) {
        process.stdout.write(JSON.stringify({ id: req.id, ok: false, error: String(e && e.message || e) }) + '\n');
      }
    }
  });
}
