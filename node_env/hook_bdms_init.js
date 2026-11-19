// 用 window.bdms 的 setter 拦截，在 SDK 赋值后立即包装 init，抓取真实调用参数
const hookSrc = [
  '(function(){',
  '  var _bdms;',
  '  Object.defineProperty(window, "bdms", {',
  '    configurable: true,',
  '    get: function(){ return _bdms; },',
  '    set: function(v){',
  '      _bdms = v;',
  '      try{',
  '        if (v && typeof v.init === "function") {',
  '          var f = v.init;',
  '          v.init = function(){',
  '            try{ sessionStorage.setItem("__bdmsInitArgs", JSON.stringify([].slice.call(arguments))); }catch(e){}',
  '            return f.apply(this, arguments);',
  '          };',
  '        }',
  '      }catch(e){}',
  '    }',
  '  });',
  '})()',
].join('\n');

(async () => {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const t = list.find(x => x.type === 'page');
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const p = new Map();
  const send = (m, q) => new Promise(res => {
    const i = ++id; p.set(i, res); ws.send(JSON.stringify({ id: i, method: m, params: q }));
  });
  ws.onmessage = e => {
    const d = JSON.parse(e.data);
    if (d.id && p.has(d.id)) { p.get(d.id)(d.result); p.delete(d.id); }
  };
  ws.onopen = async () => {
    await send('Page.enable');
    await send('Page.addScriptToEvaluateOnNewDocument', { source: hookSrc });
    await send('Page.reload', { ignoreCache: true });
    setTimeout(async () => {
      const v = await send('Runtime.evaluate', {
        expression: 'sessionStorage.getItem("__bdmsInitArgs")', returnByValue: true,
      });
      console.log('INITARGS=', v && v.result ? v.result.value : 'none');
      ws.close();
    }, 12000);
  };
})();
