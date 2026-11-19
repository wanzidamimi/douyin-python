# -*- coding: utf-8 -*-
"""纯独立验证：不用真浏览器导出的 cookie，只用 curl_cffi 自己访问拿的 ttwid + 裁剪签名，能否握手。"""
import asyncio
import re

import websockets

from http_client import DouyinHttp
from signer import NodeSigner, build_stub
from danmu_client import build_ws_url

h = DouyinHttp()
info = h.open_room("https://live.douyin.com/331574794813")
room = info["room_id"]
did = "7708735529357067826"  # 用一个合法的 webid（真机 SSR/odin）
print("curl_cffi 拿到 room:", room, "ttwid:", bool(h.ttwid), flush=True)

signer = NodeSigner(mode="stripped")
signed = signer.sign_room(room, did)
import time
now = int(time.time() * 1000)
ie = (f"internal_src:dim|wss_push_room_id:{room}|wss_push_did:{did}|"
      f"first_req_ms:{now-150}|fetch_time:{now}|seq:1|wss_info:0-{now}-0-0|wrds_v:1")
url = build_ws_url(room, did, signed["signature"],
                   cursor=f"t-{now}_r-1_d-1_u-1", internal_ext=ie)
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36",
           "Origin": "https://live.douyin.com", "Cookie": f"ttwid={h.ttwid}"}
print("签名:", signed["signature"], flush=True)


async def main():
    try:
        async with websockets.connect(url, additional_headers=headers, open_timeout=12) as ws:
            n = 0
            async for raw in ws:
                if isinstance(raw, bytes):
                    n += 1
                if n >= 2:
                    break
            print(f"[独立客户端] 101 握手成功 frames={n}", flush=True)
    except Exception as e:
        print(f"[独立客户端] FAIL {type(e).__name__}: {str(e)[:100]}", flush=True)


asyncio.run(main())
signer.stop()
