"""Sequential monotonic manuscript ↔ subtitle alignment.

Rules:
- Manuscript cursor never moves backward.
- Local matching only — LLM never searches manuscript positions.
- Does NOT rewrite subtitle text or timestamps.
- Supports cross-cue consumption of a single manuscript line (character cursor).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from maw.bdversion.manuscript import ManuscriptDocument
from maw.bdversion.metrics import composite_similarity
from maw.bdversion.normalize import normalize_for_match
from maw.bdversion.status import classify_status

DEFAULT_MAX_SPAN_CHARS = 120
DEFAULT_WINDOW = 24
MATCH_ACCEPT = 0.55


@dataclass(frozen=True, slots=True)
class CueAlignment:
    cue_index: int
    cue_id: str
    asr_text: str
    asr_key: str
    script_text: str | None
    match_score: float
    match_range: dict[str, int] | None
    status: str
    matched: bool


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    cues: tuple[CueAlignment, ...]
    cursor_end: int
    unmatched_script_units: tuple[int, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cue in self.cues:
            counts[cue.status] = counts.get(cue.status, 0) + 1
        return counts


@dataclass(frozen=True, slots=True)
class _ManuscriptIndex:
    key: str
    # key_index → (unit_index, char_start_in_display, char_end_slice_not_needed)
    unit_at: tuple[int, ...]
    unit_display: tuple[str, ...]
    unit_key: tuple[str, ...]
    unit_char_start: tuple[int, ...]
    unit_char_end: tuple[int, ...]


def _build_index(manuscript: ManuscriptDocument) -> _ManuscriptIndex:
    key_parts: list[str] = []
    unit_at: list[int] = []
    for unit in manuscript.units:
        for _ in unit.match_key:
            unit_at.append(unit.index)
        key_parts.append(unit.match_key)
    return _ManuscriptIndex(
        key="".join(key_parts),
        unit_at=tuple(unit_at),
        unit_display=tuple(u.display_text for u in manuscript.units),
        unit_key=tuple(u.match_key for u in manuscript.units),
        unit_char_start=tuple(u.char_span[0] for u in manuscript.units),
        unit_char_end=tuple(u.char_span[1] for u in manuscript.units),
    )


def _segment_text(segment: Mapping[str, Any]) -> str:
    text = segment.get("text")
    return text if isinstance(text, str) else ""


def _segment_id(segment: Mapping[str, Any], index: int) -> str:
    value = segment.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"main-{index + 1:03d}"


def _is_disabled(segment: Mapping[str, Any]) -> bool:
    return segment.get("disabled") is True


def _script_text_for_key_span(
    index: _ManuscriptIndex,
    key_start: int,
    key_end: int,
) -> tuple[str, dict[str, int]]:
    """Recover display text + unit range covering key span [key_start, key_end)."""

    if key_start < 0 or key_end > len(index.key) or key_start >= key_end:
        return "", {}
    first_unit = index.unit_at[key_start]
    last_unit = index.unit_at[key_end - 1]
    # Partial first/last units: slice display by proportional key progress inside unit.
    unit_start_key = 0
    for i in range(first_unit):
        unit_start_key += len(index.unit_key[i])
    # offset inside first unit
    offset_in_first = key_start - unit_start_key
    # Map key offsets to display is imperfect after punct strip; use full units
    # when span covers whole units, else take whole involved units (conservative).
    _ = offset_in_first
    if first_unit == last_unit:
        display = index.unit_display[first_unit]
        # If partial, still show the full unit line for human reference
        script_text = display
        char_start = index.unit_char_start[first_unit]
        char_end = index.unit_char_end[first_unit]
    else:
        script_text = "".join(index.unit_display[i] for i in range(first_unit, last_unit + 1))
        char_start = index.unit_char_start[first_unit]
        char_end = index.unit_char_end[last_unit]
        _ = offset_in_first
    match_range = {
        "unit_start": first_unit,
        "unit_end": last_unit + 1,
        "char_start": char_start,
        "char_end": char_end,
        "key_start": key_start,
        "key_end": key_end,
    }
    return script_text, match_range


def _best_window(
    asr_key: str,
    index: _ManuscriptIndex,
    cursor: int,
    *,
    max_span_chars: int,
    window: int,
) -> tuple[float, int, int]:
    """Find best forward substring match. Returns (score, key_start, key_end)."""

    if not asr_key or cursor >= len(index.key):
        return 0.0, cursor, cursor
    haystack = index.key
    n = len(asr_key)
    # candidate lengths: allow cue shorter/longer than script slice
    min_len = max(1, n - max(4, n // 3))
    max_len = min(max_span_chars, n + max(6, n // 2), len(haystack) - cursor)
    # also expand search horizon by window units worth of chars (~ window * avg)
    search_limit = min(len(haystack), cursor + max(max_len, n + window * 4))
    best_score = 0.0
    best_start = cursor
    best_end = cursor
    # Prefer lengths closest to n on score ties
    candidates: list[tuple[float, int, int, int]] = []
    for start in range(cursor, search_limit):
        # early stop if remaining shorter than min_len
        if len(haystack) - start < min_len:
            break
        end_limit = min(search_limit, start + max_len)
        for end in range(start + min_len, end_limit + 1):
            piece = haystack[start:end]
            score = composite_similarity(asr_key, piece)
            candidates.append((score, -abs(end - start - n), start, end))
    if not candidates:
        return 0.0, cursor, cursor
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, _, best_start, best_end = candidates[0]
    return best_score, best_start, best_end


def align_segments_to_manuscript(
    segments: Sequence[Mapping[str, Any]],
    manuscript: ManuscriptDocument,
    *,
    max_span_chars: int = DEFAULT_MAX_SPAN_CHARS,
    window: int = DEFAULT_WINDOW,
    include_disabled: bool = False,
    max_span: int | None = None,
) -> AlignmentResult:
    """Align ASR segments to manuscript with a monotonic key-cursor.

    ``max_span`` is accepted as a deprecated alias for max character span hints.
    Disabled segments are skipped by default and do not consume manuscript text.
    """

    if max_span is not None:
        # keep API compatible with unit-span tests; convert roughly
        max_span_chars = max(max_span_chars, max_span * 20)
    if max_span_chars < 1:
        raise ValueError("max_span_chars must be >= 1")
    if window < 1:
        raise ValueError("window must be >= 1")

    index = _build_index(manuscript)
    cues: list[CueAlignment] = []
    cursor = 0
    consumed_units: set[int] = set()
    warnings: list[str] = []

    for seg_index, segment in enumerate(segments):
        if _is_disabled(segment) and not include_disabled:
            cues.append(
                CueAlignment(
                    cue_index=seg_index,
                    cue_id=_segment_id(segment, seg_index),
                    asr_text=_segment_text(segment),
                    asr_key="",
                    script_text=None,
                    match_score=0.0,
                    match_range=None,
                    status="uncertain",
                    matched=False,
                )
            )
            continue

        text = _segment_text(segment)
        asr_key = normalize_for_match(text)
        score, key_start, key_end = _best_window(
            asr_key,
            index,
            cursor,
            max_span_chars=max_span_chars,
            window=window,
        )

        matched = bool(asr_key) and key_end > key_start and score >= MATCH_ACCEPT
        if matched:
            script_key = index.key[key_start:key_end]
            script_text, match_range = _script_text_for_key_span(index, key_start, key_end)
            status = classify_status(
                asr_key=asr_key,
                script_key=script_key,
                match_score=score,
                matched=True,
            )
            cursor = key_end
            first_u = match_range["unit_start"]
            last_u = match_range["unit_end"] - 1
            for u in range(first_u, last_u + 1):
                consumed_units.add(u)
        else:
            script_text = None
            match_range = None
            status = classify_status(
                asr_key=asr_key,
                script_key=None,
                match_score=score,
                matched=False,
            )

        cues.append(
            CueAlignment(
                cue_index=seg_index,
                cue_id=_segment_id(segment, seg_index),
                asr_text=text,
                asr_key=asr_key,
                script_text=script_text,
                match_score=round(score, 6) if asr_key else 0.0,
                match_range=match_range,
                status=status,
                matched=matched,
            )
        )

    unmatched = tuple(
        unit.index for unit in manuscript.units if unit.index not in consumed_units
    )
    if unmatched:
        warnings.append(
            f"文稿中有 {len(unmatched)} 个单元未被字幕匹配（可能是未讲内容或匹配阈值未过）"
        )

    return AlignmentResult(
        cues=tuple(cues),
        cursor_end=cursor,
        unmatched_script_units=unmatched,
        warnings=tuple(warnings),
    )


def proofread_payload(cue: CueAlignment) -> dict[str, Any]:
    """Map alignment result to planned ``segments[*].proofread`` shape."""

    return {
        "status": cue.status,
        "match_score": cue.match_score,
        "match_range": cue.match_range,
        "script_text": cue.script_text,
        "asr_original": cue.asr_text,
        "secondary_asr": None,
        "corrected": None,
        "reason": None,
    }
