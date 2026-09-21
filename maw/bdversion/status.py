"""Initial proofread status rules and color mapping (existing MAW palette)."""

from __future__ import annotations

from maw.colors import COLOR_PALETTE

# status → existing color name from maw.colors.COLOR_PALETTE
STATUS_COLOR_NAMES: dict[str, str] = {
    "verified": "green",
    "improvised": "yellow",
    "uncertain": "red",
    # manual 不自动上色（用户已确认决策）
}

_COLOR_VALUES = dict(COLOR_PALETTE)

# 分数阈值（可配置，先给稳定默认）
EXACT_STATUS = "verified"
HIGH_SCORE = 0.86
LOW_SCORE = 0.55
LLM_SCORE = 0.72


def classify_status(
    *,
    asr_key: str,
    script_key: str | None,
    match_score: float,
    matched: bool,
) -> str:
    """Return initial status from local alignment only (no LLM).

    - 规范化后完全一致 → verified
    - 明显不同 / 无文稿匹配 → improvised
    - 其余（含高分小差异，留给 DeepSeek）→ uncertain
    """

    if not matched or script_key is None:
        if match_score <= LOW_SCORE:
            return "improvised"
        return "uncertain"
    if asr_key and script_key and asr_key == script_key:
        return EXACT_STATUS
    if match_score >= HIGH_SCORE:
        # 高分但非全同：Phase 4 交给 DeepSeek，本地先标 uncertain
        return "uncertain"
    if match_score <= LOW_SCORE:
        return "improvised"
    return "uncertain"


def should_call_llm(status: str, match_score: float) -> bool:
    """Routing helper for Phase 4 DeepSeek.

    verified / improvised 不调用；高分 uncertain 调用；低分 uncertain 保持 ASR。
    """

    if status == "verified":
        return False
    if status == "improvised":
        return False
    if status == "manual":
        return False
    return match_score >= LLM_SCORE


def status_color_name(status: str | None) -> str | None:
    if not status:
        return None
    return STATUS_COLOR_NAMES.get(status)


def status_color_value(status: str | None) -> str | None:
    name = status_color_name(status)
    if not name:
        return None
    return _COLOR_VALUES.get(name)
