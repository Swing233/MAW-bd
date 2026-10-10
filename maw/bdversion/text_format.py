"""Keep subtitle spacing while applying textual corrections, without touching timing."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


def preserve_subtitle_spacing(original: str, corrected: str) -> str:
    """Restore original spaces; retain necessary Latin word separators only.

    Compare non-whitespace characters so Chinese formatting added by a model
    cannot create visual gaps. Replacements (including numbers) map original
    spaces onto the corrected text. Never alter the original project/items.
    """
    corrected = re.sub(r"<br\s*/?>", "", corrected, flags=re.IGNORECASE)
    before = "".join(original.split())
    after = "".join(corrected.split())
    if not after:
        return original
    spaces: dict[int, str] = {}
    offset = 0
    for part in re.split(r"(\s+)", corrected):
        if part.isspace():
            if 0 < offset < len(after) and after[offset - 1].isascii() and after[offset].isascii():
                if after[offset - 1].isalnum() and after[offset].isalnum():
                    spaces[offset] = " "
        else:
            offset += len(part)
    opcodes = SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
    offset = 0
    for part in re.split(r"(\s+)", original):
        if not part.isspace():
            offset += len(part)
            continue
        if offset == 0 or offset == len(before):
            continue
        for tag, i1, i2, j1, j2 in opcodes:
            if i1 <= offset <= i2:
                target = j1 + offset - i1 if tag == "equal" else j2 if offset == i2 else j1
                if 0 < target < len(after):
                    spaces[target] = part if "\n" not in part and "\r" not in part else " "
                break
    return "".join(spaces.get(i, "") + char for i, char in enumerate(after))


def normalize_asr_spacing(project: dict) -> int:
    """Use one separator for ASR commas/spaces, preserving all timing fields."""
    def clean(text: str, context: str | None = None, offset: int = 0) -> str:
        source = text if context is None else context
        def comma(match: re.Match) -> str:
            # A comma between digits without spaces may be a thousands separator.
            start, end = (position + offset for position in match.span())
            if (match.group() == "," and start > 0 and end < len(source)
                    and source[start - 1].isdigit() and source[end].isdigit()):
                return ","
            return " "
        result = re.sub(r"[ \t\u3000]*[,，][ \t\u3000]*", comma, text)
        return re.sub(r"[ \t\u3000]+", " ", result)

    changed = 0
    for segment in project.get("segments", []):
        if not isinstance(segment, dict):
            continue
        before = segment.get("text")
        if isinstance(before, str):
            after = clean(before).strip()
            if after != before:
                segment["text"] = after
                changed += 1
        items = segment.get("items")
        if not isinstance(items, list):
            continue
        previous = ""
        context = "".join(item.get("text", "") for item in items if isinstance(item, dict) and isinstance(item.get("text"), str))
        offset = 0
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            text = clean(item["text"], context, offset)
            offset += len(item["text"])
            if previous.endswith(" ") and text.startswith(" "):
                text = text[1:]
            item["text"] = text
            previous += text
        if items and isinstance(items[0], dict) and isinstance(items[0].get("text"), str):
            items[0]["text"] = items[0]["text"].lstrip()
        if items and isinstance(items[-1], dict) and isinstance(items[-1].get("text"), str):
            items[-1]["text"] = items[-1]["text"].rstrip()
    return changed
