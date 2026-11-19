"""抖音弹幕纯协议直连配置。"""
import os

# 官方 vendor 版本（对应 node_env/sign.js 里的 CDN filename）
SDK_VERSION = "1.0.0.53"

# 浏览器指纹基线（与补环境 env_core.js 保持一致；改为你真机值可进一步提高一致性）
DEVICE = {
    "aid": 6383,
    "app_name": "douyin_web",
    "version_code": "180800",
    "webcast_sdk_version": "1.0.15",
    "update_version_code": "1.0.15",
    "device_platform": "web",
    "cookie_enabled": "true",
    "screen_width": 2048,
    "screen_height": 1152,
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Mozilla",
    "tz_name": "Asia/Shanghai",
    "live_id": 1,
    "did_rule": 3,
    "endpoint": "live_pc",
    "identity": "audience",
    "im_path": "/webcast/im/fetch/",
    "support_wrds": 1,
    "need_persist_msg_count": 15,
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)

# Chrome 客户端提示（与 UA 版本一致，避免 sec-ch-ua 与 UA 冲突）
SEC_CH_UA = '"Google Chrome";v="157", "Chromium";v="157", "Not_A Brand";v="24"'
SEC_CH_UA_MOBILE = "?0"
SEC_CH_UA_PLATFORM = '"Windows"'

NODE_SIGN_CMD = [
    "node",
    os.path.join(os.path.dirname(__file__), "node_env", "sign.js"),
]

# WS 域名池（抓包实测两个）
WS_HOSTS = [
    "webcast100-ws-web-hl.douyin.com",
    "webcast100-ws-web-lq.douyin.com",
]
