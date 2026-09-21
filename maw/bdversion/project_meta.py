"""Write proofread metadata onto MAW projects without touching timing/text truth."""

from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from maw.bdversion.alignment import AlignmentResult, proofread_payload
from maw.bdversion.status import status_color_name, status_color_value
from maw.colors import COLOR_PALETTE
from maw.project import normalize_project
from maw.project_preview import JsonDict

PROOFREAD_STATUSES = frozenset({"verified", "improvised", "uncertain", "manual"})
PROOFREAD_RUN_SCHEMA = "moy.asr.proofread.v1"

_COLOR_BY_NAME = dict(COLOR_PALETTE)


def normalize_proofread(raw: object) -> dict[str, Any] | None:
    """Return a cleaned proofread object, or None when absent/invalid-empty."""

    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("proofread must be an object")
    status = raw.get("status")
    if status is not None and status not in PROOFREAD_STATUSES:
        raise ValueError(f"proofread.status must be one of {sorted(PROOFREAD_STATUSES)}")
    match_score = raw.get("match_score")
    if match_score is not None:
        if isinstance(match_score, bool) or not isinstance(match_score, (int, float)):
            raise ValueError("proofread.match_score must be a number")
        if not 0.0 <= float(match_score) <= 1.0:
            raise ValueError("proofread.match_score must be between 0 and 1")
        match_score = float(match_score)
    match_range = raw.get("match_range")
    if match_range is not None and not isinstance(match_range, Mapping):
        raise ValueError("proofread.match_range must be an object")
    for key in (
        "script_text",
        "asr_original",
        "secondary_asr",
        "corrected",
        "reason",
    ):
        value = raw.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"proofread.{key} must be a string or null")
    disagreement = raw.get("disagreement")
    if disagreement is not None and not isinstance(disagreement, Mapping):
        raise ValueError("proofread.disagreement must be an object")
    return {
        "status": status,
        "match_score": match_score,
        "match_range": dict(match_range) if isinstance(match_range, Mapping) else None,
        "script_text": raw.get("script_text"),
        "asr_original": raw.get("asr_original"),
        "secondary_asr": raw.get("secondary_asr"),
        "corrected": raw.get("corrected"),
        "reason": raw.get("reason"),
        "disagreement": dict(disagreement) if isinstance(disagreement, Mapping) else None,
    }


def color_snapshot_for_status(status: str | None) -> dict[str, Any] | None:
    """Existing MAW color head shape; None for manual/unknown (no auto color)."""

    name = status_color_name(status)
    if not name:
        return None
    value = status_color_value(status) or _COLOR_BY_NAME.get(name)
    return {"name": name, "value": value}


def apply_status_color(
    segment: JsonDict,
    *,
    start: int | None = None,
    end: int | None = None,
    overwrite: bool = True,
) -> bool:
    """Paint segment.color from proofread.status using the shared 5-color palette."""

    proofread = segment.get("proofread")
    if not isinstance(proofread, Mapping):
        return False
    status = proofread.get("status")
    snapshot = color_snapshot_for_status(status if isinstance(status, str) else None)
    if snapshot is None:
        return False
    if not overwrite and segment.get("color") is not None:
        return False
    seg_start = start if isinstance(start, int) else segment.get("start")
    seg_end = end if isinstance(end, int) else segment.get("end")
    if not isinstance(seg_start, int) or not isinstance(seg_end, int):
        return False
    # Preserve existing color_ref head if same name already starts here
    segment["color"] = {
        "name": snapshot["name"],
        "value": snapshot["value"],
        "start": seg_start,
        "end": seg_end,
    }
    segment["color_ref"] = None
    return True


def attach_alignment_to_segments(
    segments: Sequence[Mapping[str, Any]] | list[JsonDict],
    alignment: AlignmentResult,
    *,
    apply_colors: bool = True,
    preserve_manual: bool = True,
) -> list[JsonDict]:
    """Deep-copy segments and write proofread (+ optional color) from alignment."""

    updated: list[JsonDict] = []
    by_index = {cue.cue_index: cue for cue in alignment.cues}
    for index, segment in enumerate(segments):
        new_segment = copy.deepcopy(dict(segment))
        cue = by_index.get(index)
        if cue is not None:
            existing = new_segment.get("proofread")
            if (
                preserve_manual
                and isinstance(existing, Mapping)
                and existing.get("status") == "manual"
            ):
                # 人工改过的段不被自动对齐覆盖
                pass
            else:
                new_segment["proofread"] = proofread_payload(cue)
                if apply_colors:
                    apply_status_color(new_segment)
        updated.append(new_segment)
    return updated


def project_with_alignment(
    project: Mapping[str, Any],
    alignment: AlignmentResult,
    *,
    manuscript_meta: Mapping[str, Any] | None = None,
    apply_colors: bool = True,
) -> JsonDict:
    """Return a normalized project copy with proofread fields attached."""

    base = copy.deepcopy(dict(project))
    segments = base.get("segments")
    if not isinstance(segments, list):
        base["segments"] = []
        segments = base["segments"]
    base["segments"] = attach_alignment_to_segments(
        segments,
        alignment,
        apply_colors=apply_colors,
    )
    run: dict[str, Any] = {
        "schema": PROOFREAD_RUN_SCHEMA,
        "asr_mode": "single",
        "created_from": "bdversion.alignment",
        "cursor_end": alignment.cursor_end,
        "status_counts": alignment.by_status(),
        "warnings": list(alignment.warnings),
    }
    if manuscript_meta:
        run["manuscript"] = dict(manuscript_meta)
    base["proofread_run"] = run
    return normalize_project(base)


def mark_manual_edit(segment: JsonDict) -> JsonDict:
    """User edited cue text in MAWE → status=manual; no auto color."""

    proofread = segment.get("proofread")
    if not isinstance(proofread, Mapping):
        proofread = {}
    else:
        proofread = dict(proofread)
    if proofread.get("asr_original") is None:
        # keep last known original if missing; do not invent
        proofread.setdefault("asr_original", segment.get("text"))
    proofread["status"] = "manual"
    proofread["corrected"] = segment.get("text")
    proofread["reason"] = proofread.get("reason") or "manual edit"
    segment["proofread"] = proofread
    # manual 不自动上色；若存在校对自动色则清除
    color = segment.get("color")
    if isinstance(color, Mapping):
        name = color.get("name")
        if name in {status_color_name(s) for s in PROOFREAD_STATUSES if s != "manual"}:
            segment["color"] = None
            segment["color_ref"] = None
    return segment
