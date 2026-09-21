"""Dual Qwen ASR cross-check.

Primary model owns the timeline (start/end/items/text).
Secondary model is aligned for disagreement only — never rewrites times.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from maw.bdversion.alignment import align_segments_to_manuscript
from maw.bdversion.manuscript import ManuscriptDocument, build_manuscript
from maw.bdversion.metrics import composite_similarity
from maw.bdversion.normalize import normalize_for_match
from maw.project_preview import JsonDict

PRIMARY_MODEL = "qwen-audio-3.0-asr-flash-filetrans"
SECONDARY_MODEL = "qwen3-asr-flash-filetrans"
DISAGREE_THRESHOLD = 0.75


@dataclass(frozen=True, slots=True)
class DualAsrConfig:
    primary_model: str = PRIMARY_MODEL
    secondary_model: str = SECONDARY_MODEL
    mode: str = "dual"  # single | dual
    disagree_threshold: float = DISAGREE_THRESHOLD


@dataclass(frozen=True, slots=True)
class SecondaryMatch:
    cue_index: int
    cue_id: str
    primary_text: str
    secondary_text: str | None
    similarity: float
    disagreement: bool


@dataclass(frozen=True, slots=True)
class DualMergeResult:
    segments: tuple[JsonDict, ...]
    matches: tuple[SecondaryMatch, ...]
    config: DualAsrConfig
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def disagreement_count(self) -> int:
        return sum(1 for m in self.matches if m.disagreement)

    def secondary_texts_by_index(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for match in self.matches:
            if match.secondary_text:
                out[match.cue_index] = match.secondary_text
        return out


def _seg_text(segment: Mapping[str, Any]) -> str:
    text = segment.get("text")
    return text if isinstance(text, str) else ""


def _seg_id(segment: Mapping[str, Any], index: int) -> str:
    value = segment.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"main-{index + 1:03d}"


def _enabled_segments(segments: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [s for s in segments if s.get("disabled") is not True]


def secondary_as_manuscript(secondary_segments: Sequence[Mapping[str, Any]]) -> ManuscriptDocument:
    """Treat secondary ASR cues as a sequential 'script' for monotonic alignment."""

    lines = [_seg_text(seg) for seg in _enabled_segments(secondary_segments)]
    raw = "\n".join(line for line in lines if line.strip())
    return build_manuscript(
        "paste",
        raw,
        path=None,
    )


def _time_overlap_secondary(
    primary_segment: Mapping[str, Any],
    secondary_segments: Sequence[Mapping[str, Any]],
) -> str | None:
    """Fallback: pick secondary cue(s) overlapping primary time range (evidence only)."""

    p_start = primary_segment.get("start")
    p_end = primary_segment.get("end")
    if not isinstance(p_start, int) or not isinstance(p_end, int):
        return None
    parts: list[str] = []
    for seg in secondary_segments:
        if seg.get("disabled") is True:
            continue
        s_start = seg.get("start")
        s_end = seg.get("end")
        if not isinstance(s_start, int) or not isinstance(s_end, int):
            continue
        if s_end <= p_start or s_start >= p_end:
            continue
        text = _seg_text(seg)
        if text:
            parts.append(text)
    return "".join(parts) if parts else None


def align_secondary_to_primary(
    primary_segments: Sequence[Mapping[str, Any]],
    secondary_segments: Sequence[Mapping[str, Any]],
    *,
    threshold: float = DISAGREE_THRESHOLD,
) -> tuple[list[SecondaryMatch], list[str]]:
    """Monotonic align secondary text onto primary cues. Times ignored for merge."""

    warnings: list[str] = []
    if not secondary_segments:
        warnings.append("副 ASR 无结果，跳过交叉验证")
        return [], warnings
    try:
        doc = secondary_as_manuscript(secondary_segments)
    except Exception as error:  # empty secondary
        warnings.append(f"副 ASR 文稿为空或不可用：{error}")
        return [], warnings

    alignment = align_segments_to_manuscript(primary_segments, doc)
    enabled_secondary = _enabled_segments(secondary_segments)
    matches: list[SecondaryMatch] = []
    for cue in alignment.cues:
        primary_segment = primary_segments[cue.cue_index] if cue.cue_index < len(primary_segments) else {}
        secondary_text = cue.script_text if cue.matched else None
        if not cue.matched:
            secondary_text = _time_overlap_secondary(primary_segment, enabled_secondary)
        similarity = 0.0
        if cue.matched and secondary_text:
            similarity = max(
                cue.match_score,
                composite_similarity(cue.asr_key, normalize_for_match(secondary_text)),
            )
        elif secondary_text:
            similarity = composite_similarity(cue.asr_key, normalize_for_match(secondary_text))
        disagreement = bool(cue.asr_key) and (
            secondary_text is None
            or similarity < threshold
            or normalize_for_match(secondary_text) != cue.asr_key
        )
        if secondary_text and normalize_for_match(secondary_text) == cue.asr_key:
            disagreement = False
            similarity = max(similarity, 1.0)
        matches.append(
            SecondaryMatch(
                cue_index=cue.cue_index,
                cue_id=cue.cue_id,
                primary_text=cue.asr_text,
                secondary_text=secondary_text,
                similarity=round(similarity, 6),
                disagreement=disagreement,
            )
        )
    return matches, warnings


def merge_dual_asr(
    primary_segments: Sequence[Mapping[str, Any]],
    secondary_segments: Sequence[Mapping[str, Any]] | None,
    *,
    config: DualAsrConfig | None = None,
) -> DualMergeResult:
    """Return primary-timeline segments with secondary_asr + disagreement metadata.

    **Invariant:** start/end/items/text come only from primary.
    """

    cfg = config or DualAsrConfig()
    warnings: list[str] = []
    out: list[JsonDict] = [copy.deepcopy(dict(seg)) for seg in primary_segments]

    if cfg.mode != "dual" or not secondary_segments:
        if cfg.mode == "dual" and not secondary_segments:
            warnings.append("dual 模式缺少副 ASR 结果")
        for index, segment in enumerate(out):
            proofread = segment.get("proofread")
            if not isinstance(proofread, dict):
                proofread = {}
            else:
                proofread = dict(proofread)
            proofread.setdefault("secondary_asr", None)
            proofread.setdefault("asr_original", _seg_text(segment))
            segment["proofread"] = proofread
        return DualMergeResult(
            segments=tuple(out),
            matches=(),
            config=cfg,
            warnings=tuple(warnings),
        )

    matches, align_warnings = align_secondary_to_primary(
        primary_segments,
        secondary_segments,
        threshold=cfg.disagree_threshold,
    )
    warnings.extend(align_warnings)
    by_index = {m.cue_index: m for m in matches}

    for index, segment in enumerate(out):
        proofread = segment.get("proofread")
        if not isinstance(proofread, dict):
            proofread = {}
        else:
            proofread = dict(proofread)
        if proofread.get("asr_original") is None:
            proofread["asr_original"] = _seg_text(segment)
        match = by_index.get(index)
        if match is None:
            proofread["secondary_asr"] = None
            proofread["disagreement"] = None
        else:
            proofread["secondary_asr"] = match.secondary_text
            proofread["disagreement"] = {
                "score": match.similarity,
                "flag": match.disagreement,
                "primary_model": cfg.primary_model,
                "secondary_model": cfg.secondary_model,
            }
        # never touch start/end/text/items from secondary
        segment["proofread"] = proofread
        segment.setdefault("id", _seg_id(segment, index))

    return DualMergeResult(
        segments=tuple(out),
        matches=tuple(matches),
        config=cfg,
        warnings=tuple(warnings),
    )


def project_with_dual_asr(
    project: Mapping[str, Any],
    secondary_segments: Sequence[Mapping[str, Any]] | None,
    *,
    config: DualAsrConfig | None = None,
) -> JsonDict:
    """Deep-copy project; attach dual proofread metadata; preserve primary timeline."""

    cfg = config or DualAsrConfig()
    base = copy.deepcopy(dict(project))
    segments = base.get("segments")
    if not isinstance(segments, list):
        segments = []
    merged = merge_dual_asr(segments, secondary_segments, config=cfg)
    base["segments"] = list(merged.segments)
    base["model"] = cfg.primary_model
    run = base.get("proofread_run")
    if not isinstance(run, dict):
        run = {"schema": "moy.asr.proofread.v1"}
    else:
        run = dict(run)
    run.update(
        {
            "asr_mode": cfg.mode,
            "primary_model": cfg.primary_model,
            "secondary_model": cfg.secondary_model if cfg.mode == "dual" else None,
            "disagreement_count": merged.disagreement_count,
        }
    )
    if merged.warnings:
        existing = list(run.get("warnings") or [])
        run["warnings"] = existing + list(merged.warnings)
    base["proofread_run"] = run
    from maw.project import normalize_project

    return normalize_project(base)


def dual_transcribe(
    media_path: str,
    *,
    config: DualAsrConfig | None = None,
    transcribe_fn: Callable[..., dict[str, Any]] | None = None,
    language: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], DualAsrConfig]:
    """Run primary (and optional secondary) ASR via injectable transcribe_fn.

    ``transcribe_fn(audio_path, language=..., model=...)`` must return a dict
    with ``segments`` (and optionally other project fields). Timeline always
    comes from the primary call.
    """

    cfg = config or DualAsrConfig()
    if transcribe_fn is None:
        raise ValueError("transcribe_fn is required (wire generate_subtitle_qwen_api.transcribe)")

    primary_payload = transcribe_fn(media_path, language=language, model=cfg.primary_model)
    primary_segments = list(primary_payload.get("segments") or [])
    if not primary_segments:
        raise ValueError("主 ASR 未返回任何字幕段")

    secondary_segments: list[dict[str, Any]] = []
    if cfg.mode == "dual":
        secondary_payload = transcribe_fn(media_path, language=language, model=cfg.secondary_model)
        secondary_segments = list(secondary_payload.get("segments") or [])
    return primary_segments, secondary_segments, cfg


def timeline_signature(segments: Sequence[Mapping[str, Any]]) -> tuple[tuple[int, int, str], ...]:
    """Fingerprint used in tests: secondary merge must not change this."""

    return tuple(
        (
            int(seg.get("start") or 0),
            int(seg.get("end") or 0),
            _seg_text(seg),
        )
        for seg in segments
    )
