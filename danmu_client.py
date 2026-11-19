"""
danmu_client.py —— 弹幕 WS 客户端（纯协议直连）

流程：
  1) DouyinHttp 访问直播间页拿 room_id / webid / ttwid（curl_cffi chrome TLS）
  2) NodeSigner 用官方 webmssdk 对 13 参数串签名拿 X-Bogus
  3) 拼 WS URL，websockets 直连（Chrome 头），接收二进制帧
  4) dyproto 解码为可读弹幕，回调输出

归属：项目自写；依赖的官方 webmssdk 在 vendor/，不逆向其算法。
"""
import asyncio
import json
import time
from typing import Callable, Optional
from urllib.parse import urlencode

import websockets

import config
from category import classify
from dyproto.decoder import decode_frame
from http_client import DouyinHttp
from signer import NodeSigner


def parse_room(room_input: str) -> str:
    """从直播地址里提取 web_rid（/live.douyin.com/123456 或纯数字）"""
    s = room_input.strip()
    if s.isdigit():
        return s
    # 去掉 query / 尾斜杠，取最后一段数字
    s = s.split('?')[0].rstrip('/')
    parts = [p for p in s.split('/') if p]
    for p in reversed(parts):
        if p.isdigit():
            return p
    return ""


def build_ws_url(room_id, user_unique_id, signature, cursor=None, internal_ext=None):
    d = config.DEVICE
    now_ms = int(time.time() * 1000)
    params = {
        "app_name": d["app_name"],
        "version_code": d["version_code"],
        "webcast_sdk_version": d["webcast_sdk_version"],
        "update_version_code": d["update_version_code"],
        "compress": "gzip",
        "device_platform": d["device_platform"],
        "cookie_enabled": "true",
        "screen_width": d["screen_width"],
        "screen_height": d["screen_height"],
        "browser_language": d["browser_language"],
        "browser_platform": d["browser_platform"],
        "browser_name": d["browser_name"],
        "browser_version": config.USER_AGENT.split("Chrome/")[1].split(" ")[0] if "Chrome/" in config.USER_AGENT else "157.0.0.0",
        "browser_online": "true",
        "tz_name": d["tz_name"],
        "cursor": cursor or (f"t-{now_ms}_r-1_d-1_u-1"),
        "internal_ext": internal_ext or (
            f"internal_src:dim|wss_push_room_id:{room_id}|wss_push_did:{user_unique_id}|"
            f"first_req_ms:{now_ms - 150}|fetch_time:{now_ms}|seq:1|wss_info:0-{now_ms}-0-0|wrds_v:1"
        ),
        "host": "https://live.douyin.com",
        "aid": d["aid"],
        "live_id": d["live_id"],
        "did_rule": d["did_rule"],
        "endpoint": d["endpoint"],
        "support_wrds": d["support_wrds"],
        "user_unique_id": user_unique_id,
        "im_path": d["im_path"],
        "identity": d["identity"],
        "need_persist_msg_count": d["need_persist_msg_count"],
        "insert_task_id": "",
        "live_reason": "",
        "room_id": room_id,
        "heartbeatDuration": 0,
        "signature": signature,
    }
    host = config.WS_HOSTS[0]
    return f"wss://{host}/webcast/im/push/v2/?{urlencode(params)}"


class DanmuClient:
    def __init__(self, on_message: Callable[[dict], None]):
        self.on_message = on_message
        self.http = DouyinHttp()
        self.signer = NodeSigner()
        self.running = False
        self.ws = None
        self.room_id = None
        self.user_unique_id = None

    def prepare(self, room_url: str):
        """会话初始化：访问直播间页 + 生成 webid"""
        web_rid = parse_room(room_url)
        if not web_rid:
            raise ValueError("无法从输入里解析直播间 ID: " + room_url)
        full_url = room_url if room_url.startswith("http") else f"https://live.douyin.com/{web_rid}"
        info = self.http.open_room(full_url)
        self.room_id = info.get("room_id") or web_rid
        # 真机 did = 观众 webid，SSR 的 odin.user_unique_id 即该值（19 位），优先用它
        self.user_unique_id = (info.get("user_unique_id")
                               or self.http.ensure_webid()
                               or self.http.cookies.get("webid")
                               or str(int(time.time() * 1000)))
        return {"web_rid": web_rid, **info, "user_unique_id": self.user_unique_id,
                "ttwid": bool(self.http.ttwid)}

    async def run(self, room_url: str, duration: Optional[float] = None):
        info = self.prepare(room_url)
        signed = self.signer.sign_room(self.room_id, self.user_unique_id)
        ws_url = build_ws_url(self.room_id, self.user_unique_id, signed["signature"])
        self.on_message({"kind": "system", "text": f"已连接房间 {self.room_id} / did {self.user_unique_id}"})
        self.on_message({"kind": "system", "text": f"stub={signed['stub']} signature={signed['signature']}"})

        extra_headers = self.http.headers_for_ws()
        if self.http.ttwid:
            extra_headers["Cookie"] = f"ttwid={self.http.ttwid}"
        self.running = True
        start = time.time()
        try:
            async with websockets.connect(
                ws_url,
                additional_headers=extra_headers,
                subprotocols=[],
                compression=None,
                open_timeout=15,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                self.ws = ws
                self.on_message({"kind": "system", "text": "WebSocket 已握手 (101)"})
                async for raw in ws:
                    if not self.running:
                        break
                    if duration and time.time() - start > duration:
                        break
                    if isinstance(raw, bytes):
                        try:
                            frame = decode_frame(raw)
                            for m in frame.get("messages", []):
                                if "error" in m:
                                    continue
                                content = m.get("content")
                                texts = m.get("texts") or []
                                if not content and not texts:
                                    continue
                                user = m.get("user")
                                info = classify(m.get("message_type"), content or "", " ".join(texts))
                                label = info["category_label"]
                                head = f"[{label}]" + (f" {user}:" if user else "")
                                text = ((head + " " + content) if content
                                        else (head + " " + " | ".join(texts[:3])))
                                self.on_message({
                                    "kind": "danmu",
                                    "text": text.strip(),
                                    "category": info["category"],
                                    "category_label": label,
                                    "message_type": info["message_type"],
                                    "user": user,
                                    "content": content,
                                    "seq": frame.get("seq"),
                                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                })
                        except Exception as e:
                            self.on_message({"kind": "warn", "text": f"decode error: {e}"})
                    else:
                        self.on_message({"kind": "raw", "text": str(raw)[:200]})
        except Exception as e:
            self.on_message({"kind": "error", "text": f"WS 连接失败: {type(e).__name__}: {e}"})
        finally:
            self.running = False
            self.signer.stop()


def run_sync(room_url: str, on_message, duration=None, on_client=None):
    client = DanmuClient(on_message)
    if on_client:
        on_client(client)
    asyncio.run(client.run(room_url, duration))
    return client
