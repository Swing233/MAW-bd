"""Focused speech-first proofread domain (maw-bdversion).

语音是真源；文稿只作匹配与错字参考。本包不改写最终字幕时间轴。

The public facade is deliberately lazy.  The packaged ASR subprocess imports
``maw.bdversion.segment`` from a small source runtime that does not ship the
GUI's LLM modules.  Eagerly importing the proofreader here would therefore
make segmentation fail before ASR starts.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AlignmentResult",
    "CueAlignment",
    "ManuscriptDocument",
    "ManuscriptSource",
    "ManuscriptUnit",
    "STATUS_COLOR_NAMES",
    "DEEPSEEK_DEFAULT_MODEL",
    "DualAsrConfig",
    "DualMergeResult",
    "PRIMARY_MODEL",
    "SECONDARY_MODEL",
    "align_segments_to_manuscript",
    "apply_proofread_outcome_to_segments",
    "apply_status_color",
    "attach_alignment_to_segments",
    "build_proofread_cues",
    "classify_status",
    "color_snapshot_for_status",
    "deepseek_settings",
    "dual_transcribe",
    "load_manuscript",
    "manuscript_from_paste",
    "mark_manual_edit",
    "merge_dual_asr",
    "normalize_for_match",
    "normalize_proofread",
    "project_with_alignment",
    "project_with_dual_asr",
    "run_conservative_proofread",
    "should_call_llm",
    "status_color_name",
]


_EXPORTS: dict[str, tuple[str, str]] = {
    "AlignmentResult": ("maw.bdversion.alignment", "AlignmentResult"),
    "CueAlignment": ("maw.bdversion.alignment", "CueAlignment"),
    "align_segments_to_manuscript": ("maw.bdversion.alignment", "align_segments_to_manuscript"),
    "ManuscriptDocument": ("maw.bdversion.manuscript", "ManuscriptDocument"),
    "ManuscriptSource": ("maw.bdversion.manuscript", "ManuscriptSource"),
    "ManuscriptUnit": ("maw.bdversion.manuscript", "ManuscriptUnit"),
    "load_manuscript": ("maw.bdversion.manuscript", "load_manuscript"),
    "manuscript_from_paste": ("maw.bdversion.manuscript", "manuscript_from_paste"),
    "normalize_for_match": ("maw.bdversion.normalize", "normalize_for_match"),
    "DEEPSEEK_DEFAULT_MODEL": ("maw.bdversion.deepseek", "DEFAULT_MODEL"),
    "apply_proofread_outcome_to_segments": ("maw.bdversion.deepseek", "apply_proofread_outcome_to_segments"),
    "build_proofread_cues": ("maw.bdversion.deepseek", "build_proofread_cues"),
    "deepseek_settings": ("maw.bdversion.deepseek", "deepseek_settings"),
    "run_conservative_proofread": ("maw.bdversion.deepseek", "run_conservative_proofread"),
    "PRIMARY_MODEL": ("maw.bdversion.dual_asr", "PRIMARY_MODEL"),
    "SECONDARY_MODEL": ("maw.bdversion.dual_asr", "SECONDARY_MODEL"),
    "DualAsrConfig": ("maw.bdversion.dual_asr", "DualAsrConfig"),
    "DualMergeResult": ("maw.bdversion.dual_asr", "DualMergeResult"),
    "dual_transcribe": ("maw.bdversion.dual_asr", "dual_transcribe"),
    "merge_dual_asr": ("maw.bdversion.dual_asr", "merge_dual_asr"),
    "project_with_dual_asr": ("maw.bdversion.dual_asr", "project_with_dual_asr"),
    "apply_status_color": ("maw.bdversion.project_meta", "apply_status_color"),
    "attach_alignment_to_segments": ("maw.bdversion.project_meta", "attach_alignment_to_segments"),
    "color_snapshot_for_status": ("maw.bdversion.project_meta", "color_snapshot_for_status"),
    "mark_manual_edit": ("maw.bdversion.project_meta", "mark_manual_edit"),
    "normalize_proofread": ("maw.bdversion.project_meta", "normalize_proofread"),
    "project_with_alignment": ("maw.bdversion.project_meta", "project_with_alignment"),
    "STATUS_COLOR_NAMES": ("maw.bdversion.status", "STATUS_COLOR_NAMES"),
    "classify_status": ("maw.bdversion.status", "classify_status"),
    "should_call_llm": ("maw.bdversion.status", "should_call_llm"),
    "status_color_name": ("maw.bdversion.status", "status_color_name"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
