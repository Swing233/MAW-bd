"""Compatibility facade for MAW's single ASR segmentation implementation.

Cloud ASR, local ASR and manual re-segmentation all delegate to the natural
splitter in generate_subtitle_qwen_api. Keeping this facade preserves older
imports without maintaining a second algorithm.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from generate_subtitle_qwen_api import (
    QWEN_AUDIO_NATURAL_MAX_LEN,
    QWEN_AUDIO_NATURAL_MIN_LEN,
    QWEN_AUDIO_STRONG_GAP_MS,
    is_cjk_dominant,
    split_coarse_segment,
    split_segments_auto,
)

DEFAULT_MAX_LEN = QWEN_AUDIO_NATURAL_MAX_LEN
DEFAULT_MIN_LEN = QWEN_AUDIO_NATURAL_MIN_LEN
DEFAULT_GAP_SPLIT_MS = QWEN_AUDIO_STRONG_GAP_MS


def split_items_sentence_aware(
    items: Sequence[Mapping[str, Any]],
    *,
    max_len: int = DEFAULT_MAX_LEN,
    min_len: int = DEFAULT_MIN_LEN,
    gap_split_ms: int = DEFAULT_GAP_SPLIT_MS,
) -> list[list[dict[str, Any]]]:
    """Return natural CJK groups while preserving supplied item timestamps."""

    source = [dict(item) for item in items if str(item.get("text") or "")]
    if not source:
        return []
    split_mode = "continuous" if is_cjk_dominant(source) else "word"
    if any(len(str(item.get("text") or "")) > max_len for item in source):
        text = "".join(str(item.get("text") or "") for item in source)
        start = int(source[0].get("start") or 0)
        end = int(source[-1].get("end") or start)
        pieces = split_coarse_segment(
            {"start": start, "end": max(start + 1, end), "text": text},
            max_len=max(1, int(max_len)),
            min_len=max(1, int(min_len)),
            gap_split_ms=0,
            split_mode=split_mode,
        )
        return [[{
            "text": str(piece.get("text") or ""),
            "start": int(piece.get("start") or start),
            "end": int(piece.get("end") or end),
            "timing_estimated": True,
        }] for piece in pieces]
    segments = split_segments_auto(
        source,
        max_len=max(1, int(max_len)),
        min_len=max(1, int(min_len)),
        gap_split_ms=max(0, int(gap_split_ms)),
        natural_cjk=split_mode == "continuous",
        split_mode=split_mode,
    )
    return [list(segment.get("items") or []) for segment in segments if segment.get("items")]


def split_coarse_segments_sentence_aware(
    segments: Sequence[Mapping[str, Any]],
    *,
    max_len: int = DEFAULT_MAX_LEN,
    min_len: int = DEFAULT_MIN_LEN,
    gap_split_ms: int = DEFAULT_GAP_SPLIT_MS,
) -> list[dict[str, Any]]:
    """Split only inside existing cues, preferring real item timestamps.

    Itemless or stale-item cues use semantic text boundaries and proportional,
    contiguous segment times. Those pieces omit items and carry
    timing_estimated=true so estimates cannot masquerade as word timing.
    """

    out: list[dict[str, Any]] = []
    for raw in segments:
        original = dict(raw)
        text = str(original.get("text") or "").replace("\r", " ").replace("\n", " ")
        original["text"] = text
        raw_items = original.get("items")
        valid_items = raw_items if isinstance(raw_items, list) else []
        items_text = "".join(
            str(item.get("text") or "")
            for item in valid_items
            if isinstance(item, Mapping)
        )
        if items_text != text:
            original.pop("items", None)

        pieces = split_coarse_segment(
            original,
            max_len=max(1, int(max_len)),
            min_len=max(1, int(min_len)),
            gap_split_ms=max(0, int(gap_split_ms)),
            split_mode="continuous",
        )
        for piece in pieces:
            merged = dict(original)
            merged.update(piece)
            if len(pieces) > 1:
                merged.pop("id", None)
            out.append(merged)
    return out


def resegment_segments(
    segments: Sequence[Mapping[str, Any]],
    *,
    max_len: int = DEFAULT_MAX_LEN,
    min_len: int = DEFAULT_MIN_LEN,
    gap_split_ms: int = DEFAULT_GAP_SPLIT_MS,
) -> list[dict[str, Any]]:
    """Manual re-segmentation; never merges across existing ASR cue bounds."""

    return split_coarse_segments_sentence_aware(
        segments,
        max_len=max_len,
        min_len=min_len,
        gap_split_ms=gap_split_ms,
    )
