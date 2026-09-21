"""Matching-only text normalization.

Never write these strings back into subtitle ``text``. Final cues stay ASR/人工编辑真源。
"""

from __future__ import annotations

import unicodedata

# 粘贴/导出时常见的不可见或格式字符
_STRIP_CATEGORIES = frozenset({"P", "S", "Z", "C"})


def normalize_for_match(value: str | None) -> str:
    """Return a match key: NFKC + casefold + strip punct/space/invisible.

    数字经 NFKC 统一全角/半角；数字间空白与标点被剥掉，因此
    ``1,000`` / ``１０００`` / ``1 000`` 会落到同一 key（仅用于匹配）。
    """

    if not value:
        return ""
    chars: list[str] = []
    for char in unicodedata.normalize("NFKC", value).casefold():
        category = unicodedata.category(char)
        if category[0] in _STRIP_CATEGORIES or category.startswith("P"):
            continue
        if char.isspace():
            continue
        chars.append(char)
    return "".join(chars)


def display_units_key(text: str | None) -> str:
    """Alias kept for call sites that want manuscript-side keys."""

    return normalize_for_match(text)
