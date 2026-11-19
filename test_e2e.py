# -*- coding: utf-8 -*-
"""端到端实测：会话初始化 -> 签名 -> WS 直连 -> 收帧解码。限时 25 秒自动退出。"""
import collections
import sys
import time

import config
from danmu_client import DanmuClient

ROOM = sys.argv[1] if len(sys.argv) > 1 else "https://live.douyin.com/841042256134"
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0

msgs = []
count = {"danmu": 0, "system": 0, "error": 0}
type_count = collections.Counter()


def on_msg(m):
    kind = m.get("kind", "?")
    count[kind] = count.get(kind, 0) + 1
    if kind == "danmu":
        type_count[(m.get("category"), m.get("message_type"))] += 1
    print(f"[{kind}][{m.get('category_label','')}] {m.get('text','')[:160]}", flush=True)
    msgs.append(m)


client = DanmuClient(on_msg)
try:
    info = client.prepare(ROOM)
    print("[INFO] prepare:", info, flush=True)
    import asyncio
    asyncio.run(client.run(ROOM, duration=DURATION))
except Exception as e:
    print("[FATAL]", type(e).__name__, e, flush=True)
finally:
    print("\n[SUMMARY]", count, flush=True)
    print("[TYPES]", dict(type_count), flush=True)
    ok = count.get("danmu", 0) > 0
    print("E2E_RESULT:", "PASS" if ok else "NO_DANMU", flush=True)
