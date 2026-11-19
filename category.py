# -*- coding: utf-8 -*-
"""弹幕消息分类：把 Webcast message_type 映射为可读类别，并识别勋章/等级文案。"""
import re

# (key, 中文标签, 颜色) —— 前端按此顺序渲染筛选器
CATEGORIES = [
    ("chat",     "弹幕",     "#e6e8eb"),
    ("badge",    "勋章/等级", "#ffd166"),
    ("gift",     "礼物",     "#ff8fab"),
    ("like",     "点赞",     "#8ecae6"),
    ("member",   "进场",     "#a0c4ff"),
    ("social",   "互动",     "#bde0fe"),
    ("fansclub", "粉丝团",   "#cdb4db"),
    ("stats",    "数据",     "#9aa3af"),
    ("rank",     "排行",     "#ffb703"),
    ("ecom",     "电商",     "#ff9f68"),
    ("system",   "系统",     "#63b3ff"),
    ("other",    "其他",     "#9aa3af"),
]
CATEGORY_LABELS = {k: lab for k, lab, _ in CATEGORIES}

# 常见 Webcast 消息类型 -> 类别
_TYPE_MAP = {
    "WebcastChatMessage": "chat",
    "WebcastEmojiChatMessage": "chat",
    "WebcastGiftMessage": "gift",
    "WebcastLikeMessage": "like",
    "WebcastMemberMessage": "member",
    "WebcastSocialMessage": "social",
    "WebcastFansclubMessage": "fansclub",
    "WebcastRoomUserSeqMessage": "stats",
    "WebcastRoomStatsMessage": "stats",
    "WebcastStatsMessage": "stats",
    "WebcastRoomRankMessage": "rank",
    "WebcastRanklistLatestTopUserMessage": "rank",
    "WebcastRanklistHourEntranceMessage": "rank",
    "WebcastControlMessage": "system",
    "WebcastCommonTextMessage": "system",
    "WebcastCaptionMessage": "system",
    "WebcastRoomMessage": "system",
    "WebcastRoomStreamAdaptationMessage": "system",
    "WebcastMsgDetectMessage": "other",
    # 电商通用消息：可能是点赞，也可能是商品弹窗信令（LivePopMessage），下面按内容细分
    "WebcastLiveEcomGeneralMessage": "ecom",
    "WebcastLiveShoppingMessage": "ecom",
}

# 【荣誉等级2级勋章】/ 荣誉等级5 / 勋章3级 / VIP8 / Lv12 等
_BADGE_PAT = re.compile(
    r'(【[^】]{0,20}(勋章|荣誉等级|等级)[^】]{0,20}】'
    r'|荣誉等级\s*\d+'
    r'|勋章\s*\d+\s*级'
    r'|VIP\s*\d+'
    r'|Lv\.?\s*\d+)',
    re.IGNORECASE,
)


# 通用/未知类型用内容关键词二次细分（不触碰明确的聊天弹幕，避免误判）
_CONTENT_HINT = [
    (re.compile(r'点赞|点了赞|赞一下'), "like"),
    (re.compile(r'关注了|关注主播|分享了直播间'), "social"),
]


def classify(message_type, *texts):
    """返回 {category, category_label, message_type}。"""
    mt = message_type or ""
    cat = _TYPE_MAP.get(mt, "other")
    joined = " ".join(str(t) for t in texts if t)
    main_content = str(texts[0]) if texts else ""
    if _BADGE_PAT.search(joined):
        cat = "badge"
    elif cat in ("other", "social", "ecom"):
        # 只用主 content 判断，避免 all_strings 里的噪声字段（如"小时榜"消息夹带"点赞"）误判
        for pat, hint in _CONTENT_HINT:
            if pat.search(main_content):
                cat = hint
                break
    return {
        "category": cat,
        "category_label": CATEGORY_LABELS.get(cat, "其他"),
        "message_type": mt or None,
    }
