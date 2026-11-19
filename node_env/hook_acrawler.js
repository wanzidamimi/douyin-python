// 拦截 byted_acrawler 的 init/setConfig/setTTWebid/setTTWid 调用，记录真实参数
const hookSrc = [
  '(function(){',
  '  var _a;',
  '  function pack(args){ return [].slice.call(args).map(function(x){',
  '    try{ return (typeof x === "object") ? JSON.stringify(x).slice(0,2000) : String(x); }catch(e){ return String(x); }',
  '  }); }',
  '  function wrap(name){',
  '    var f = _a[name];',
  '    if (typeof f !== "function") return;',
  '    _a[name] = function(){',
  '      try{',
  '        var arr = JSON.parse(sessionStorage.getItem("__acCalls")||"[]");',
  '        arr.push({m:name, args:pack(arguments)});',
  '        sessionStorage.setItem("__acCalls", JSON.stringify(arr));',
  '      }catch(e){}',
  '      return f.apply(this, arguments);',
  '    };',
  '  }',
  '  Object.defineProperty(window, "byted_acrawler", {',
  '    configurable:true,',
  '    get:function(){ return _a; },',
  '    set:function(v){',
  '      _a=v;',
  '      ["init","setConfig","setTTWebid","setTTWebidV2","setTTWid","setUserMode"].forEach(wrap);',
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
        expression: 'sessionStorage.getItem("__acCalls")', returnByValue: true,
      });
      console.log('ACCALLS=', v && v.result ? v.result.value : 'none');
      ws.close();
    }, 12000);
  };
})();
