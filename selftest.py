# -*- coding: utf-8 -*-
"""douyin_python 自检：签名闭环 + 真实帧解码闭环。"""
import base64
import sys

from category import CATEGORIES, CATEGORY_LABELS, classify
from dyproto.decoder import decode_frame, decode_pb_payload, format_message
from recorder import SessionRecorder
from signer import NodeSigner, build_stub

REAL_FRAME_B64 = (
    "CAIQv9L/866fzKsnGLhFIAgqFQoNY29tcHJlc3NfdHlwZRIEZ3ppcCp1Cg9pbS1pbnRlcm5hbF9leHQSYmludGVybmFsX3NyYzpwdXNoc2VydmVyfGZpcnN0X3JlcV9tczoxNzk0ODI5OTUwMDkzfHNlcToxfHdzc19tc2dfdHlwZTpyfHdyZHNfdjo3NzA4NzM1OTE5OTUxNDQ5OTM1KjoKCWltLWN1cnNvchItdC0xNzk0ODI5OTUxODQ2X3ItNzcwODczNTk0MTQyNjI5OTk5Ml9kLTFfdS0xKhcKBmltLW5vdxINMTc5NDgyOTk1MTg0NioZCg5pbS1saXZlX2N1cnNvchIHZC0xX3UtMTICcGI6A21zZ0LNBh+LCAAAAAAAAP/EVE9oHFUc3rez3R2fGocRddgiDsltYf/M7GxmZw82m3Y3URMbjSFShGF29+3kbWZnJu/NTghNpeSgOfQQPKyIUGgPImpBVittimD3YpViL0KxiHpY26BQsCcVopL951/aS8B3mZnf9/H7fb/5+B58IwL5RVQqG9SbwctoFlFqmIj/OQx3mf9CuLdufPnDN9cu7daEk83Wqfav53drKTD5KQMfw7ZvWLiiL6M13bWMMlpyrAoi/MPHU7kGReSEeFzKUY9g2zwRHYH3jZWy1e4Rt5jR20H2fv4BGBnLHi6oxaK4xbwDbgTh9SD7aiccDX9/8cNYLPb0ZwDOLXmeS3PJpCtJ8dWevkTFaaxh28XlRNmpJ3HdTPaRJK0blqUfQdW8b3gGSbi2+bLnWn7cKdUSuG6YCB4ddkzvS0P+4F24schYsViYLEy2QGAbBNoAQnY0DENsgA+8zzBbIXA21N/289DU7LyyOlObPZZH1ed0ulJbXng+Tl5040edZ3WcmrFxfmqNFPJSMY+nGo2CU5IXn0GyPf/C9HRxYcVcXHkKTS/kzTuhSPQAz0AQODsRlrpn9FEWHOM7F7Y7Fy7dfO3crY2LO+dPd7ZfmQObAHwCdliOEd59E8T+bcB+/679d/SeBuQL40cO/88GTIZYwIFSSJQngjX44MHf/EOPXL751ZPCMGDwFIDRYQJ9NL/kuC62zUFGK1C9G8693bxy9fbfkyqeufzFmdMKFxRaG5tXvvul3VRaYITrVfvgHcDwILUZ7H0Jwy7wWwAf/8u4QtmpTyEbEcMaKPoAwMw9ONzHzdev/vTP+4Mf2WPPOW6fFX3CcF0Llw0PO3bStysJ03FMCyVc4nhOqVEVz3XVxUbY3ov4Ufchy38uNrq3RuwAC4SdiBxlh3Xu1sZm5+S1dlMRfv/6x+thYaiIP+TFJVVTsrKmZSRZHddJXFVTWTWd0RRJkcdlTdM0Wa8MqnJaTWWkcSWjZWS9EZfE99pdVS9h20PENiydknLObdAlioiPyHoVE+rpBK3odZrrj1KzclZNr69SqtepqXtrLsqR9VVSobqfG4yX9hQpiqalMxMPTYM/AAAA//8BAAD//51oPmW3BQAA"
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def test_signature():
    stub, raw = build_stub("7708701247901322022", "7708735529357067826")
    check("stub 与抓包实证一致", stub == "46e23ef2195237c92276d4a9d33b157e", stub)
    s = NodeSigner()
    try:
        x = s.sign_stub(stub)
        check("X-Bogus 为 16 位", len(x) == 16, repr(x))
        print("       X-Bogus sample:", x)
    except Exception as e:
        check("Node 签名可用", False, str(e))
    finally:
        s.stop()


def test_decode():
    f = decode_frame(base64.b64decode(REAL_FRAME_B64))
    check("外层 seq 解析", f["seq"] == 2, str(f["seq"]))
    check("compress_type=gzip", f["compress_type"] == "gzip", str(f["compress_type"]))
    check("pb 段 gunzip 成功", len(f["messages"]) == 1, str(len(f["messages"])))
    if f["messages"]:
        m = f["messages"][0]
        all_text = " ".join(m.get("all_strings", []))
        check("含 Webcast 消息类型", "Webcast" in str(m.get("message_type")), str(m.get("message_type")))
        check("中文内容正确还原", "为主播点赞了" in all_text, all_text[:120])
        check("真实帧昵称精确提取", m.get("user") == "年***", str(m.get("user")))
        print("       message_type:", m.get("message_type"))
        print("       user:", m.get("user"))
        print("       content:", m.get("content"))
    print("       formatted:")
    for line in format_message(f).splitlines():
        print("        ", line)


def test_category():
    check("聊天弹幕归类为 chat",
          classify("WebcastChatMessage", "你好")["category"] == "chat")
    check("点赞消息归类为 like",
          classify("WebcastLikeMessage", "为主播点赞了")["category"] == "like")
    c = classify("WebcastChatMessage", "【荣誉等级2级勋章】来了")
    check("勋章文案归类为 badge", c["category"] == "badge", str(c))
    check("未知类型归入 other",
          classify("WebcastSomethingNewMessage", "x")["category"] == "other")

    f = decode_frame(base64.b64decode(REAL_FRAME_B64))
    m = f["messages"][0]
    real = classify(m.get("message_type"), m.get("content") or "",
                    " ".join(m.get("texts") or []))
    check("真实帧按点赞内容归类为 like", real["category"] == "like", str(real))


def test_action_text():
    def payload_with(s):
        b = s.encode('utf-8')
        return bytes([0x5A, len(b)]) + b  # field 11 (action_description), wire type 2

    check("enterroom_normal 译为中文",
          decode_pb_payload(payload_with("enterroom_normal"))["content"] == "进入了直播间")
    check("降级聚合进场标识译为中文",
          "聚合进场" in (decode_pb_payload(
              payload_with("enter_room_downgrade_aggregate_message"))["content"] or ""))
    check("mime 技术串被过滤",
          decode_pb_payload(payload_with("application/vnd.google.protobuf"))["content"] is None)
    check("普通中文内容不受影响",
          decode_pb_payload(payload_with("你好呀"))["content"] == "你好呀")
    check("LivePopMessage 译为中文",
          decode_pb_payload(payload_with("LivePopMessage"))["content"] == "商品推广弹窗提示")
    from category import classify
    check("电商弹窗消息归为 ecom",
          classify("WebcastLiveEcomGeneralMessage", "商品推广弹窗提示")["category"] == "ecom")
    check("电商消息里的点赞仍细分 like",
          classify("WebcastLiveEcomGeneralMessage", "为主播点赞了")["category"] == "like")


def test_recorder():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        rec = SessionRecorder(export_dir=d)
        rec.begin("https://live.douyin.com/123")
        rec.add({"kind": "danmu", "category": "chat", "category_label": "弹幕",
                 "message_type": "WebcastChatMessage", "user": "张三", "content": "你好",
                 "text": "[弹幕] 张三: 你好", "seq": 1, "ts": "2026-01-01 00:00:00"})
        p = rec.save()
        check("CSV 已生成", p is not None and p.exists(), str(p))
        check("CSV 带 UTF-8 BOM", p.read_bytes()[:3] == b"\xef\xbb\xbf")
        text = p.read_text(encoding="utf-8-sig")
        check("CSV 含中文内容", "你好" in text and "弹幕" in text)
        files = SessionRecorder.list_files(export_dir=d)
        check("历史列表行数正确", len(files) == 1 and files[0]["rows"] == 1, str(files))
        check("拒绝路径穿越", SessionRecorder.path_for("../x.csv", export_dir=d) is None)
        check("拒绝非 CSV", SessionRecorder.path_for("x.txt", export_dir=d) is None)
        check("类别表非空", len(CATEGORIES) >= 10)


if __name__ == "__main__":
    test_signature()
    test_decode()
    test_category()
    test_action_text()
    test_recorder()
    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
