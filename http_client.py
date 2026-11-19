"""
http_client.py —— 传输层：curl_cffi(impersonate=chrome) 复刻真 Chrome TLS/H2 指纹

归属：项目自写。手法来自 skill（JdApis 的 utils/http_client.py）：
  - impersonate="chrome" 拿与真 Chrome 一致的 JA4/H2 指纹；
  - default_headers=False + 逐字段照抄 Chrome 实抓头，避免 Python 特征；
  - 负责会话初始化：从直播间页拿 ttwid（Set-Cookie）、走 webid 接口拿 web_id。
"""
import random
import re
import time
from urllib.parse import urlencode

from curl_cffi import requests as creq

import config


class DouyinHttp:
    def __init__(self, user_agent=None):
        self.ua = user_agent or config.USER_AGENT
        # impersonate 用 chrome，与补环境 UA(157) 对应的指纹族一致
        self.s = creq.Session(impersonate="chrome")
        self.s.headers.update({
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": config.SEC_CH_UA,
            "sec-ch-ua-mobile": config.SEC_CH_UA_MOBILE,
            "sec-ch-ua-platform": config.SEC_CH_UA_PLATFORM,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })
        self.webid = None
        self.ttwid = None
        self.cookies = {}

    def _ms_token(self):
        # 真机是 SDK 生成的 128 位随机串；这里生成同形态占位（服务端会在 x-ms-token 回执校验松紧取决于路径）
        import string
        alphabet = string.ascii_letters + string.digits + '-_'
        return ''.join(random.choice(alphabet) for _ in range(128))

    def open_room(self, room_url: str):
        """访问直播间页，拿到 ttwid 等 Set-Cookie，并从 HTML 里提取真实 room_id / user_unique_id。"""
        r = self.s.get(room_url, timeout=20)
        # 合并 cookie
        self.cookies.update(r.cookies.get_dict())
        self.ttwid = self.cookies.get("ttwid")
        text = r.text
        info = {"room_id": None, "user_unique_id": None, "title": None, "raw_len": len(text)}
        # SSR JSON 里的引号被转义成 \"，先做一份反转义副本再匹配
        unescaped = text.replace('\\"', '"').replace('\\u002F', '/')
        candidates = [text, unescaped]
        for buf in candidates:
            for pat, key in [
                (r'"roomId"\s*:\s*"(\d{15,})', "room_id"),
                (r'"room"\s*:\s*\{"id_str"\s*:\s*"(\d{15,})', "room_id"),
                (r'"room_id"\s*:\s*"?(\d{15,})', "room_id"),
                (r'"room_id_str"\s*:\s*"(\d{15,})"', "room_id"),
                (r'"user_unique_id"\s*:\s*"?(\d{15,})', "user_unique_id"),
                (r'"web_id"\s*:\s*"?(\d{15,})', "user_unique_id"),
            ]:
                m = re.search(pat, buf)
                if m and not info[key]:
                    info[key] = m.group(1)
            if info["room_id"] and info["user_unique_id"]:
                break
        return info

    def ensure_webid(self):
        """走 webid 接口生成设备 ID（真机同样走这个接口）。"""
        if self.webid:
            return self.webid
        params = {
            "aid": 6383,
            "sdk_version": "5.1.24_dy",
            "device_platform": "webapp",
            "msToken": self._ms_token(),
        }
        url = "https://mcs.zijieapi.com/webid?" + urlencode(params)
        r = self.s.get(url, timeout=15)
        try:
            data = r.json()
            self.webid = str(data.get("web_id") or data.get("webid") or "")
        except Exception:
            self.webid = ""
        if not self.webid:
            # 保留 cookie 里可能出现的 webid
            self.webid = self.cookies.get("webid") or ""
        return self.webid

    def headers_for_ws(self):
        """WS 握手用的头（Chrome 风格）。"""
        return {
            "User-Agent": self.ua,
            "Origin": "https://live.douyin.com",
        }
