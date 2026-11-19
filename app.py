"""
app.py —— 抖音弹幕实时显示 GUI（独立 FastAPI 服务）

启动：uvicorn app:app --host 127.0.0.1 --port 8800
浏览器打开 http://127.0.0.1:8800 ，输入直播地址即可实时滚动显示弹幕。

后端用 danmu_client（纯协议直连），不依赖浏览器。
"""
import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from category import CATEGORIES, CATEGORY_LABELS
from danmu_client import DanmuClient, run_sync
from recorder import SessionRecorder

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="抖音弹幕实时显示（纯协议）")

# 全局会话状态：事件队列 + 当前 client
_queues = []
_state = {"room": "", "status": "idle", "client": None, "lock": threading.Lock()}
_recorder = SessionRecorder()


def _emit(event: dict):
    for q in list(_queues):
        try:
            q.put_nowait(event)
        except queue.Full:
            pass


def _on_message(msg: dict):
    if msg.get("kind") == "danmu":
        _recorder.add(msg)
    _emit(msg)


def _run_worker(room_url: str):
    with _state["lock"]:
        _state["status"] = "connecting"
    _recorder.begin(room_url)
    _emit({"kind": "system", "text": "会话初始化中…"})
    try:
        run_sync(room_url, _on_message, duration=None,
                 on_client=lambda c: _state.__setitem__("client", c))
    except Exception as e:
        _emit({"kind": "error", "text": f"worker 异常: {e}"})
    finally:
        path = _recorder.save()
        with _state["lock"]:
            _state["status"] = "idle"
            _state["client"] = None
        if path:
            _emit({"kind": "system", "text": f"本次弹幕已保存: {path.name}（{_recorder.count} 条）"})
        _emit({"kind": "system", "text": "会话已结束"})


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.post("/api/start")
async def start(request: Request):
    data = await request.json()
    room = (data.get("room") or "").strip()
    if not room:
        return {"ok": False, "error": "缺少直播地址"}
    with _state["lock"]:
        if _state["status"] != "idle":
            return {"ok": False, "error": "已有会话运行中，请先停止"}
        _state["room"] = room
    threading.Thread(target=_run_worker, args=(room,), daemon=True).start()
    return {"ok": True}


@app.post("/api/stop")
async def stop():
    with _state["lock"]:
        client = _state["client"]
    if client:
        client.running = False
    return {"ok": True}


@app.get("/api/events")
async def events():
    q = queue.Queue(maxsize=500)
    _queues.append(q)

    def gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = q.get(timeout=15)
                    yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            if q in _queues:
                _queues.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/status")
async def status():
    with _state["lock"]:
        return {"room": _state["room"], "status": _state["status"],
                "recorded": _recorder.count}


@app.get("/api/categories")
async def categories():
    return {"categories": [
        {"key": k, "label": lab, "color": col} for k, lab, col in CATEGORIES
    ]}


@app.post("/api/export")
async def export():
    path = _recorder.save()
    if not path:
        return {"ok": False, "error": "当前会话尚无弹幕可导出"}
    return {"ok": True, "name": path.name, "count": _recorder.count}


@app.get("/api/history")
async def history():
    return {"files": SessionRecorder.list_files()}


@app.get("/api/download/{name}")
async def download(name: str):
    path = SessionRecorder.path_for(name)
    if not path:
        return {"ok": False, "error": "文件不存在"}
    return FileResponse(str(path), filename=name, media_type="text/csv")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
