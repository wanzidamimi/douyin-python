"""
decoder.py —— 抖音 Webcast IM 帧解码（无 schema 的 protobuf wire 解析）

归属：项目自写。数据侧无加密（已实证），只需：
  1) 解析外层 envelope（protobuf）: seq/compress_type/internal_ext/cursor/pb/...
  2) pb 字段是 gzip 压缩的内层 protobuf，gunzip 后递归解析所有嵌套层级
  3) 从可读字符串里按语义提取 message type / user / content
不依赖官方 schema chunk，避免其 webpack 模块格式随版本变化。
"""
import gzip
import re
import struct
from typing import Any, Dict, List, Tuple


def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    shift = 0
    val = 0
    while pos < len(buf) and shift < 70:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, pos


def wire_decode(buf: bytes) -> List[Tuple[int, int, Any]]:
    """通用 protobuf wire 解码，返回 [(field_no, wire_type, value), ...]"""
    out = []
    pos = 0
    n = len(buf)
    while pos < n:
        try:
            key, pos = _read_varint(buf, pos)
        except Exception:
            break
        if key == 0:
            break
        field = key >> 3
        wt = key & 0x07
        if field == 0 or wt > 5:
            break
        try:
            if wt == 0:  # varint
                v, pos = _read_varint(buf, pos)
                out.append((field, wt, v))
            elif wt == 1:  # 64-bit
                if pos + 8 > n:
                    break
                v = struct.unpack_from('<Q', buf, pos)[0]
                pos += 8
                out.append((field, wt, v))
            elif wt == 2:  # length-delimited
                ln, pos = _read_varint(buf, pos)
                if ln < 0 or pos + ln > n:
                    break
                v = buf[pos:pos + ln]
                pos += ln
                out.append((field, wt, v))
            elif wt == 5:  # 32-bit
                if pos + 4 > n:
                    break
                v = struct.unpack_from('<I', buf, pos)[0]
                pos += 4
                out.append((field, wt, v))
            else:
                break
        except Exception:
            break
    return out


# 技术字段噪声：游标 / internal_ext / 头像 CDN / base64 id 等，不作为弹幕内容
_NOISE_PAT = re.compile(
    r'^(t-\d+|internal_src|wss_msg_type|wrds_v|MS4wLj|https?://|'
    r'\{\d+:[a-z]|invalid_key_placeholder|#?[0-9A-Fa-f]{6}$)'
)

# 服务端下发的内部枚举标识（action_description / biz_scene），前端不直接显示，
# 而是用它决定展示方式（如进场消息降级聚合）。无 schema 解码会误当成正文，这里翻译成中文。
_ACTION_TEXT = {
    "enterroom_normal": "进入了直播间",
    "enter_room_downgrade_aggregate_message": "进入了直播间（聚合进场）",
    "enter_room_aggregate_message": "进入了直播间（聚合进场）",
    "follow_anchor": "关注了主播",
    "unfollow_anchor": "取消关注了主播",
    "share_room": "分享了直播",
    "honor_live_room_enter_effect": "荣耀进场",
    "is_group_member_support_msg_list": "粉丝团应援",
    "live_doodle_gift_send_message_to_anchor": "发送了涂鸦礼物",
    # 电商弹窗信令：前端用来控制商品推广卡的出现/消失，不进聊天列表
    "LivePopMessage": "商品推广弹窗提示",
    "WebcastLiveEcomGeneralMessage": "电商互动消息",
    "WebcastLiveShoppingMessage": "电商购物消息",
}
# 纯技术串：mime type / 图片路径 / 内部下划线标识，不当正文
_TECH_NOISE_PAT = re.compile(
    r'^(application/[\w.+-]+|[\w/.-]+\.(png|jpe?g|gif|webp)|[a-z][a-z0-9]*_[a-z0-9_]+)$',
    re.IGNORECASE,
)


def _humanize_content(s: str):
    """内部标识 -> 中文文案；纯技术串返回 None（表示应过滤）。"""
    if not s:
        return s
    if s in _ACTION_TEXT:
        return _ACTION_TEXT[s]
    if _TECH_NOISE_PAT.match(s):
        return None
    return s


def _fix_mojibake(s: str) -> str:
    """修复 UTF-8 中文被 latin1 解读形成的乱码（如 '为主播点赞了' -> 'Ϊ...'）"""
    if not s:
        return s
    # UTF-8 中文字节被 latin1 解读后，会落到 U+0080..U+07FF（含 'Ϊ'=U+03AA 等希腊/拉丁扩展区）
    high = sum(1 for ch in s if 0x80 <= ord(ch) <= 0x7FF)
    if high >= 2 or '\ufffd' in s:
        try:
            fixed = s.encode('latin1').decode('utf-8')
            # 只有当还原后含 CJK 或明显更"正常"时才采用
            if fixed and any('\u4e00' <= c <= '\u9fff' for c in fixed):
                return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def _clean_text(b: bytes):
    """bytes -> 可读文本；过滤掉非文本二进制"""
    try:
        s = b.decode('utf-8')
    except UnicodeDecodeError:
        return None
    if not s:
        return None
    # 控制字符占比过高视为二进制
    bad = sum(1 for ch in s if ord(ch) < 32 and ch not in '\n\r\t')
    if bad / len(s) > 0.1:
        return None
    return _fix_mojibake(s)


def collect_strings(buf: bytes, depth: int = 0, max_depth: int = 12) -> List[Tuple[int, str]]:
    """递归遍历 protobuf 所有嵌套层级，收集 (field_no, text)。"""
    result: List[Tuple[int, str]] = []
    if depth > max_depth or len(buf) > 200000:
        return result
    for f, wt, v in wire_decode(buf):
        if wt != 2 or not isinstance(v, bytes):
            continue
        txt = _clean_text(v)
        # 先判纯文本：能解码且不含 protobuf wire 特征时直接收，不再递归（避免中文被二次切错）
        is_text = False
        if txt is not None:
            raw_fields = wire_decode(v)
            # 文本串通常解不出合法的多字段 message；若解出则认为更像嵌套结构
            looks_like_msg = (len(raw_fields) >= 2 and all(0 < nf < 1000 for nf, _, _ in raw_fields)
                              and sum(1 for _, w, _ in raw_fields if w == 2) >= 2)
            if not looks_like_msg:
                result.append((f, txt))
                is_text = True
        if not is_text:
            nested = wire_decode(v)
            if nested and all(0 < nf < 1000 for nf, _, _ in nested):
                result.extend(collect_strings(v, depth + 1, max_depth))
            elif txt is not None:
                result.append((f, txt))
    return result


def _is_avatar_field(v: bytes) -> bool:
    """User.AvatarThumb（field 9）的子消息里是否含图床 URL。"""
    return (b'douyinpic' in v or b'webcast' in v) and b'http' in v


def find_users(buf: bytes, depth: int = 0, max_depth: int = 12) -> List[str]:
    """递归找 User 子消息：field3=nickName + field9=AvatarThumb，返回脱敏昵称。"""
    out: List[str] = []
    if depth > max_depth or len(buf) > 200000:
        return out
    fields = wire_decode(buf)
    grouped: Dict[int, list] = {}
    for f, wt, v in fields:
        grouped.setdefault(f, []).append((wt, v))

    nick = []
    for wt, v in grouped.get(3, []):
        if wt == 2 and isinstance(v, bytes):
            txt = _clean_text(v)
            if txt and not txt.startswith('http') and len(txt) <= 40:
                nick.append(txt)
    if any(wt == 2 and isinstance(v, bytes) and _is_avatar_field(v)
           for wt, v in grouped.get(9, [])):
        out.extend(nick)

    for f, wt, v in fields:
        if wt == 2 and isinstance(v, bytes):
            out.extend(find_users(v, depth + 1, max_depth))
    return out


def decode_pb_payload(raw: bytes) -> Dict[str, Any]:
    """gunzip 后解析内层消息体，递归提取可读字段。"""
    strings = collect_strings(raw)
    result: Dict[str, Any] = {
        "message_type": None, "user": None, "content": None,
        "sec_user_id": None, "texts": [], "all_strings": [],
    }
    seen = set()
    for f, s in strings:
        s = s.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        result["all_strings"].append(s)

        if re.match(r'^Webcast\w+Message$', s):
            result["message_type"] = s
            continue
        if _NOISE_PAT.search(s):
            continue
        result["texts"].append(s)

    # 内容：优先包含中文的句子；否则取最长的非技术文本
    cjk = re.compile(r'[\u4e00-\u9fff]')
    cn = [t for t in result["texts"] if cjk.search(t) and '{' not in t]
    if cn:
        result["content"] = max(cn, key=len)
    else:
        cands = [t for t in result["texts"] if len(t) > 1 and '|' not in t]
        # 过滤 mime/图片路径等纯技术串，避免误当正文
        cands = [t for t in cands if _humanize_content(t) is not None]
        if cands:
            result["content"] = max(cands, key=len)
    # 内部枚举标识翻译成中文（进场/关注/分享等）
    if result["content"]:
        result["content"] = _humanize_content(result["content"]) or result["content"]

    # 用户：优先按 User 消息结构（nickName field3 + AvatarThumb field9）精确提取，
    # 避免把 #b8ffffff 颜色码、room_follow_msg 等噪声字段当成昵称。
    found = find_users(raw)
    if found:
        result["user"] = found[0]
    else:
        users = [t for t in result["texts"]
                 if t != result["content"] and len(t) <= 20 and not t.startswith('http')
                 and '|' not in t and not re.fullmatch(r'#[0-9A-Fa-f]{3,8}', t)]
        if users:
            result["user"] = users[0]
    return result


def decode_frame(data: bytes) -> Dict[str, Any]:
    """解码一个 WS 接收帧（外层 envelope）。"""
    fields = wire_decode(data)
    frame: Dict[str, Any] = {
        "seq": None, "compress_type": None, "internal_ext": None,
        "cursor": None, "now": None, "live_cursor": None,
        "server_time": None, "pb_compressed": None, "messages": [],
        "raw_fields": [],
    }
    for f, wt, v in fields:
        if wt == 2 and isinstance(v, bytes):
            nested = wire_decode(v)
            kv = {}
            for nf, nwt, nv in nested:
                nt = _clean_text(nv) if nwt == 2 else nv
                if nf == 1 and nt:
                    kv['key'] = nt
                elif nf == 2:
                    kv['value'] = nt if nt is not None else nv
            key = kv.get('key')
            if key == 'compress_type':
                frame['compress_type'] = kv.get('value')
            elif key == 'server_time':
                frame['server_time'] = kv.get('value')
            elif key == 'im-internal_ext':
                frame['internal_ext'] = kv.get('value')
            elif key == 'im-cursor':
                frame['cursor'] = kv.get('value')
            elif key == 'im-now':
                frame['now'] = kv.get('value')
            elif key == 'im-live_cursor':
                frame['live_cursor'] = kv.get('value')
            if f == 8:  # pb 压缩段
                if len(v) > 2 and v[0] == 0x1f and v[1] == 0x8b:
                    frame['pb_compressed'] = v
                    try:
                        plain = gzip.decompress(v)
                        frame['messages'].append(decode_pb_payload(plain))
                    except Exception as e:
                        frame['messages'].append({"error": "gunzip failed: " + str(e)})
                else:
                    frame['messages'].append(decode_pb_payload(v))
        elif wt == 0 and f == 1:
            frame['seq'] = v
        frame['raw_fields'].append({"field": f, "wt": wt,
                                    "len": len(v) if isinstance(v, bytes) else v})
    return frame


def format_message(frame: Dict[str, Any]) -> str:
    """把解码帧格式化成可读弹幕文本。"""
    parts = []
    for m in frame.get('messages', []):
        if 'error' in m:
            continue
        mt = m.get('message_type') or 'IM'
        user = m.get('user')
        content = m.get('content')
        if content:
            parts.append(f"[{mt}] {user + ': ' if user else ''}{content}")
        elif m.get('texts'):
            parts.append(f"[{mt}] " + ' | '.join(m['texts'][:3]))
    return '\n'.join(parts)
