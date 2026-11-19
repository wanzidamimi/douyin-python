/**
 * sign_stripped.js —— 借鉴 saermart/DouyinLiveWebFetcher 的签名方案
 *
 * 关键差异（对比本工程原 sign.js 的完整补环境）：
 *  - 官方 webmssdk 在初始化时会跑一组环境检测（setTimeout(...) 里的 _0x18a9f7 等），
 *    依赖真实浏览器；项目版把这些检测调用注释掉，只保留纯签名的 crawler(_0x5c2014)。
 *  - 因此只需要极简 document/navigator stub 即可产出服务端认可的签名，
 *    无需 canvas/WebGL/策略栈/证书等"补得过多反而错误"的指纹。
 *
 * 运行：node sign_stripped.js --selftest | JSON-RPC(stdin 每行一个请求)
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'vendor', 'webmssdk_stripped.js'), 'utf8');

function buildCtx() {
  const ctx = {
    window: {},
    document: {
      cookie: '', referrer: 'https://www.douyin.com/',
      createElement: () => ({ getContext: () => null, style: {} }),
      getElementsByTagName: () => [], addEventListener: () => {},
    },
    navigator: {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36',
      language: 'zh-CN', languages: ['zh-CN', 'zh'], plugins: {}, webdriver: false,
    },
    location: { href: 'https://live.douyin.com/' },
    screen: {}, localStorage: { getItem: () => null, setItem: () => {} },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    setTimeout: setTimeout, clearTimeout: clearTimeout, console: console,
  };
  ctx.globalThis = ctx; ctx.self = ctx; ctx.window = ctx.window;
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx, { filename: 'https://lf-c-flwb.bytetos.com/obj/rc-client-security/c-webmssdk/1.0.0.53/webmssdk.es5.js' });
  return ctx;
}

let ctx = null;
function sign(stub) {
  if (!ctx) ctx = buildCtx();
  const sig = ctx.get_sign(String(stub));
  if (!sig) throw new Error('get_sign 返回空');
  return sig;
}

if (require.main === module) {
  if (process.argv.includes('--selftest')) {
    try { console.log(JSON.stringify({ ok: true, sample: sign('probe') })); }
    catch (e) { console.log(JSON.stringify({ ok: false, error: String(e) })); process.exit(1); }
  } else {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line) continue;
        let req; try { req = JSON.parse(line); } catch (e) { continue; }
        try {
          const r = req.method === 'sign'
            ? { 'X-Bogus': sign(req.params.stub), source: 'stripped-webmssdk' }
            : (req.method === 'ping' ? { pong: true } : (() => { throw new Error('unknown'); })());
          process.stdout.write(JSON.stringify({ id: req.id, ok: true, result: r }) + '\n');
        } catch (e) {
          process.stdout.write(JSON.stringify({ id: req.id, ok: false, error: String(e && e.message || e) }) + '\n');
        }
      }
    });
  }
}

module.exports = { sign };
