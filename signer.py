"""
signer.py —— Python 侧签名桥（等价 skill 里的 http_bridge，这里用 stdio JSON-RPC）

流程：13 参数固定串 -> md5 -> X-MS-STUB -> Node 官方 webmssdk -> X-Bogus = signature
不逆向签名算法，只复用官方运行时；与 JdApis 的 h5st 桥接手法一致。
"""
import hashlib
import json
import subprocess
import threading
from typing import Optional

import config

# 签名参数串的固定顺序（jshook 抓包实证，见 artifacts/jshook-phase3）
SIGN_PARAM_ORDER = [
    "live_id", "aid", "version_code", "webcast_sdk_version",
    "room_id", "sub_room_id", "sub_channel_id", "did_rule",
    "user_unique_id", "device_platform", "device_type", "ac", "identity",
]


def build_stub(room_id: str, user_unique_id: str) -> str:
    """构造 X-MS-STUB（= md5 的明文输入串）"""
    values = {
        "live_id": "1",
        "aid": "6383",
        "version_code": "180800",
        "webcast_sdk_version": "1.0.15",
        "room_id": str(room_id),
        "sub_room_id": "",
        "sub_channel_id": "",
        "did_rule": "3",
        "user_unique_id": str(user_unique_id),
        "device_platform": "web",
        "device_type": "",
        "ac": "",
        "identity": "audience",
    }
    parts = [f"{k}={values.get(k, '')}" for k in SIGN_PARAM_ORDER]
    raw = ",".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest(), raw


class NodeSigner:
    """常驻 Node 进程，通过 stdio JSON-RPC 调用官方 webmssdk。

    mode='stripped'（默认）：借鉴 saermart/DouyinLiveWebFetcher —— 裁剪掉 webmssdk 的
      浏览器环境检测，只保留纯签名 crawler，极简 stub 即可产出服务端认可的签名（实测闭环）。
    mode='full'：本工程早前的完整补环境（canvas/WebGL/策略栈/证书），实测签名被服务端拒。
    """

    def __init__(self, cmd=None, mode="stripped"):
        if cmd is None:
            if mode == "stripped":
                cmd = ["node", config.os.path.join(
                    config.os.path.dirname(__file__), "node_env", "sign_stripped.js")]
            elif mode == "full":
                cmd = ["node", config.os.path.join(
                    config.os.path.dirname(__file__), "node_env", "sign_full.js"), "--rpc"]
            else:
                cmd = config.NODE_SIGN_CMD
        self.cmd = cmd
        self.mode = mode
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self._id = 0

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=config.os.path.dirname(__file__),
        )

    def _rpc(self, method, params):
        self.start()
        with self.lock:
            self._id += 1
            rid = self._id
            req = json.dumps({"id": rid, "method": method, "params": params}, ensure_ascii=False)
            self.proc.stdin.write(req + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read()
                raise RuntimeError(f"Node 签名进程无响应: {err}")
            resp = json.loads(line)
            if not resp.get("ok"):
                raise RuntimeError(f"Node 签名失败: {resp.get('error')}")
            return resp["result"]

    def sign_stub(self, stub: str) -> str:
        return self._rpc("sign", {"stub": stub})["X-Bogus"]

    def sign_room(self, room_id: str, user_unique_id: str):
        stub, raw = build_stub(room_id, user_unique_id)
        xbogus = self.sign_stub(stub)
        return {"stub": stub, "raw": raw, "signature": xbogus}

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None


if __name__ == "__main__":
    s = NodeSigner()
    # 用抓包实证的那组参数验证 stub 是否一致
    stub, raw = build_stub("7708701247901322022", "7708735529357067826")
    print("raw   =", raw)
    print("stub  =", stub)
    print("expect= 46e23ef2195237c92276d4a9d33b157e")
    print("match =", stub == "46e23ef2195237c92276d4a9d33b157e")
    print("X-Bogus =", s.sign_stub(stub))
    s.stop()
