/**
 * sign.js —— 在补环境里加载抖音官方 webmssdk，对外提供 X-Bogus 签名
 *
 * 归属：项目自写的是「加载器 + RPC 协议」；webmssdk.es5.js 是官方 vendor 包，
 * 本工程不编写也不逆向其签名算法，只复用官方运行时（与 JdApis 的 h5st 手法一致）。
 *
 * 运行方式：
 *   node sign.js            -> JSON-RPC 模式：每行一个 JSON 请求，回一行 JSON
 *   node sign.js --selftest -> 自检
 *
 * RPC 请求：{"id":1,"method":"sign","params":{"stub":"<32位md5>"}}
 * RPC 响应：{"id":1,"ok":true,"result":{"X-Bogus":"...","source":"webmssdk"}}
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { buildEnv, CDN_URL } = require('./env_core');

const SDK_PATH = path.join(__dirname, '..', 'vendor', 'webmssdk.es5.js');
const vendorSource = fs.readFileSync(SDK_PATH, 'utf8');

let sandbox = null;
let acrawler = null;

function loadSdk() {
  if (acrawler && typeof acrawler.frontierSign === 'function') return;

  // 用真实的裸对象作为 window 底层，避免 Proxy 的 has/get 干扰 SDK 的初始化判断。
  // buildEnv() 内部已把各浏览器 API 补齐；这里取其底层 _raw 若在，否则用 env 本身。
  const env = buildEnv();
  const winRaw = env.__raw || env;

  // 构造沙箱：把浏览器全局平铺到 context 顶层，window 指向 winRaw
  const ctx = {};
  ctx.window = winRaw;
  ctx.self = winRaw;
  ctx.globalThis = ctx;          // SDK 内的 globalThis 指向沙箱顶层
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

  sandbox = vm.createContext(ctx, { name: 'douyin-webmssdk' });

  // filename 伪装成官方 CDN URL：骗过 wasm base-path 与 Error.stack 检测
  vm.runInContext(vendorSource, sandbox, { filename: CDN_URL, displayErrors: true });

  // UMD 头是 (globalThis)[key]={}，导出落在沙箱顶层 ctx 上（globalThis===ctx）
  acrawler = ctx.byted_acrawler || ctx.window.byted_acrawler || winRaw.byted_acrawler || {};
  if (!acrawler || typeof acrawler.frontierSign !== 'function') {
    const keys = acrawler ? Object.keys(acrawler) : [];
    throw new Error('webmssdk 已执行但未导出 frontierSign（keys=' + keys.join(',') + '）');
  }
}

function sign(stub) {
  loadSdk();
  const ret = acrawler.frontierSign({ 'X-MS-STUB': String(stub) });
  const xb = ret && ret['X-Bogus'];
  if (!xb) throw new Error('frontierSign 未返回 X-Bogus');
  return xb;
}

function call(method, params) {
  loadSdk();
  if (typeof acrawler[method] !== 'function') throw new Error('acrawler 无方法: ' + method);
  return acrawler[method].apply(acrawler, params || []);
}

function main() {
  if (process.argv.includes('--selftest')) {
    try {
      loadSdk();
      const x1 = sign('probe');
      const x2 = sign('probe');
      console.log(JSON.stringify({ ok: true, source: 'webmssdk', sample: x1, nondeterministic: x1 !== x2 }));
      process.exit(0);
    } catch (e) {
      console.log(JSON.stringify({ ok: false, error: String(e && e.stack || e) }));
      process.exit(1);
    }
  }

  let buf = '';
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', (chunk) => {
    buf += chunk;
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (line) handle(line);
    }
  });

  function handle(line) {
    let req;
    try { req = JSON.parse(line); } catch (e) {
      process.stdout.write(JSON.stringify({ id: null, ok: false, error: 'bad json' }) + '\n');
      return;
    }
    try {
      let result;
      if (req.method === 'sign') result = { 'X-Bogus': sign(req.params.stub), source: 'webmssdk' };
      else if (req.method === 'call') result = call(req.params.method, req.params.args);
      else if (req.method === 'ping') result = { pong: true };
      else throw new Error('unknown method: ' + req.method);
      process.stdout.write(JSON.stringify({ id: req.id, ok: true, result }) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({ id: req.id, ok: false, error: String(e && e.message || e) }) + '\n');
    }
  }
}

main();
