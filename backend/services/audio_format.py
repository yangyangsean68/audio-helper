from __future__ import annotations

import re

_FORBIDDEN = ("出行时间相同", "路上一样久", "耗时相同", "一样久")
_ADMIN_PREFIX = re.compile(
    r"^(?:[\u4e00-\u9fff]{1,8}(?:省|自治区|特别行政区|地区)|[\u4e00-\u9fff]{1,3}市|[\u4e00-\u9fff]{1,6}(?:区|县|旗))"
)


def sniff_audio(data: bytes) -> tuple[str, str]:
    """按文件头识别真实音频格式，不用 URL 或声明的后缀。"""
    if len(data) < 12:
        raise ValueError("audio too short")
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav", "audio/wav"
    if data.startswith(b"ID3") or data[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "mp3", "audio/mpeg"
    if data.startswith(b"OggS"):
        return "ogg", "audio/ogg"
    if data[4:8] == b"ftyp":
        return "m4a", "audio/mp4"
    raise ValueError("unrecognized audio format")


def compact_text(value: str) -> str:
    text = re.sub(r"\s+", "", value)
    return text.replace("（", "(").replace("）", ")").replace("，", ",")


def address_core(address: str) -> str:
    text = compact_text(address)
    previous = None
    while text != previous:
        previous = text
        text = _ADMIN_PREFIX.sub("", text, count=1)
    return text


def _address_mentioned(shop_address: str, compact_reply: str) -> bool:
    compact_addr = compact_text(shop_address)
    if compact_addr and compact_addr in compact_reply:
        return True
    core = address_core(shop_address)
    return len(core) >= 4 and core in compact_reply


def validate_reply_text(reply_text: str, shop_name: str, shop_address: str) -> str:
    text = reply_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    if not text:
        raise ValueError("empty")
    compact_reply = compact_text(text)
    if compact_text(shop_name) not in compact_reply:
        raise ValueError("missing shop name")
    if not _address_mentioned(shop_address, compact_reply):
        text = text.rstrip("。.!！ ") + f"。地址是{shop_address}。"
    if any(phrase in text for phrase in _FORBIDDEN):
        raise ValueError("forbidden travel-time claim")
    return text
