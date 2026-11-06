"""Đa ngôn ngữ đơn giản: chuỗi gốc tiếng Anh, bản dịch tiếng Việt trong vi.py."""
from .vi import VI

_lang = "vi"


def set_language(lang):
    global _lang
    _lang = lang


def language():
    return _lang


def tr(text):
    if _lang == "vi":
        return VI.get(text, text)
    return text
