# -*- coding: utf-8 -*-
"""通过 CDP 导出真机 localStorage 到文件，供补环境对齐状态。"""
import asyncio
import json
import urllib.request

import websockets

tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json"))
t = [x for x in tabs if x.get("type") == "page" and "live.douyin.com" in x.get("url", "")][0]


async def main():
    ws = await websockets.connect(t["webSocketDebuggerUrl"])
    expr = "JSON.stringify((function(){var o={};for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);o[k]=localStorage.getItem(k);}return o;})())"
    await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == 1:
            raw = m["result"]["result"]["value"]
            data = json.loads(raw)
            json.dump(data, open("_real_localstorage.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("exported", len(data), "keys")
            # 同时导出 cookie
            await ws.send(json.dumps({"id": 2, "method": "Network.getAllCookies"}))
            while True:
                m2 = json.loads(await ws.recv())
                if m2.get("id") == 2:
                    dy = [c for c in m2["result"]["cookies"] if "douyin" in c["domain"]]
                    json.dump(dy, open("_real_cookies.json", "w", encoding="utf-8"), ensure_ascii=False)
                    print("exported cookies", len(dy))
                    await ws.close()
                    return


asyncio.run(main())
