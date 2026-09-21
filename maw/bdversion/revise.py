"""Focused revise: DeepSeek + optional manuscript reference, or custom prompt."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from maw.bdversion.alignment import align_segments_to_manuscript
from maw.bdversion.deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    _default_complete,
    _parse_results,
)
from maw.bdversion.manuscript import ManuscriptError, load_manuscript, manuscript_from_paste
from maw.postprocess_llm import LlmDelta, LlmSettings, complete_subtitle_groups
from maw.project import normalize_project
from maw.project_io import write_mosp
from maw.project_preview import JsonDict

CompleteFn = Callable[[LlmSettings, str, list[dict[str, Any]]], Mapping[str, Any]]

SYSTEM_PROMPT_WITH_SCRIPT = (
    SYSTEM_PROMPT
    + "\n如果提供了 matched_script（文稿参考），仅在高度可能属于 ASR 识别错误时参考其用字；"
    "不得把现场发挥改写成文稿全文，不得补入 ASR 未出现的句子。"
)


def _read_json_text(path: Path) -> str:
    """Read JSON text; strip UTF-8 BOM without relying on utf-8-sig codec."""

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8")


def _load_project(path: Path) -> JsonDict:
    data = json.loads(_read_json_text(path))
    return normalize_project(data)


def _safe_project_path(project_path: str | Path) -> Path:
    """Resolve project path; raise clear error if not a real file."""

    raw = str(project_path or "").strip()
    if not raw or len(raw) > 1024 or "\n" in raw:
        raise FileNotFoundError("工程路径无效或为空")
    path = Path(raw).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"工程不存在：{raw[:200]}")
    return path.resolve()


def _srt_from_segments(segments: Sequence[Mapping[str, Any]]) -> str:
    def fmt(ms: int) -> str:
        ms = max(0, int(ms))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    lines: list[str] = []
    idx = 1
    for seg in segments:
        if seg.get("disabled") is True:
            continue
        text = seg.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        start, end = seg.get("start"), seg.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            continue
        lines.extend((str(idx), f"{fmt(start)} --> {fmt(end)}", text, ""))
        idx += 1
    return "\n".join(lines) + ("\n" if lines else "")


def _write_outputs(project: Mapping[str, Any], source: Path, suffix: str) -> dict[str, str]:
    source = Path(source)
    if not source.is_file():
        # never use a paste blob as filename
        base = "project"
        source = Path.cwd() / "project.mosp"
    else:
        base = source.name
    for ext in (".mosp", ".json"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
            break
    project_path = source.parent / f"{base}{suffix}.mosp"
    srt_path = source.parent / f"{base}{suffix}.srt"
    write_mosp(project_path, project)
    segments = project.get("segments")
    if isinstance(segments, list):
        srt_path.write_text("\ufeff" + _srt_from_segments(segments), encoding="utf-8")
    return {"projectPath": str(project_path), "srtPath": str(srt_path)}


def _enabled_indices(segments: Sequence[Mapping[str, Any]]) -> list[int]:
    return [i for i, seg in enumerate(segments) if seg.get("disabled") is not True]


def _cues_from_segments(segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    cues = []
    for n, i in enumerate(_enabled_indices(segments), 1):
        cues.append({"id": f"c{n:04d}", "text": str(segments[i].get("text") or "")})
    return cues


def _apply_groups_to_segments(
    segments: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    out = copy.deepcopy(list(segments))
    enabled = _enabled_indices(segments)
    id_to_idx = {f"c{n+1:04d}": i for n, i in enumerate(enabled)}
    for group in groups:
        text = group.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        sources = group.get("source_ids", group.get("id"))
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, list):
            continue
        idxs = [id_to_idx[str(s)] for s in sources if str(s) in id_to_idx]
        # Proofreading is one input cue -> one output cue. Ignore any model
        # attempt to merge cues so timing, item ranges, and cue count stay fixed.
        if len(idxs) != 1:
            continue
        out[idxs[0]]["text"] = text
    return out


def _looks_like_path(text: str) -> bool:
    """Heuristic: short, single-line, no huge paste, path-like chars."""

    s = text.strip()
    if not s or len(s) > 512:
        return False
    if "\n" in s or "\r" in s:
        return False
    if len(s.splitlines()[0] if s.splitlines() else s) > 512:
        return False
    # treat as path only if it has a slash or a file extension
    if "/" in s or "\\" in s:
        return True
    if "." in s and len(s) < 256:
        return True
    return False


def manuscript_document(manuscript: str | Path | None):
    """Load manuscript as file path OR raw pasted text — never Path(long paste)."""

    if manuscript is None:
        return None
    if isinstance(manuscript, Path):
        return load_manuscript(manuscript)
    text = str(manuscript)
    if not text.strip():
        return None
    # long or multi-line → always paste
    if _looks_like_path(text):
        try:
            maybe = Path(text).expanduser()
            if maybe.is_file():
                return load_manuscript(maybe)
        except OSError:
            # File name too long / invalid — fall through to paste
            pass
    return manuscript_from_paste(text)


def _script_refs_for_segments(segments: Sequence[Mapping[str, Any]], doc) -> dict[str, tuple[str, float]]:
    """cue_id -> (matched_script, score) via monotonic alignment."""

    if doc is None:
        return {}
    alignment = align_segments_to_manuscript(segments, doc)
    out: dict[str, tuple[str, float]] = {}
    for cue in alignment.cues:
        if cue.matched and cue.script_text:
            out[f"c{cue.cue_index + 1:04d}" if False else cue.cue_id] = (
                cue.script_text,
                cue.match_score,
            )
    # map by enabled-order cue ids used in payload
    enabled = _enabled_indices(segments)
    id_map = {idx: f"c{n+1:04d}" for n, idx in enumerate(enabled)}
    mapped: dict[str, tuple[str, float]] = {}
    for cue in alignment.cues:
        if not cue.matched or not cue.script_text:
            continue
        cid = id_map.get(cue.cue_index)
        if cid:
            mapped[cid] = (cue.script_text, cue.match_score)
    return mapped


def revise_project(
    project_path: Path | str,
    *,
    mode: str = "deepseek",
    api_key: str = "",
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    custom_prompt: str = "",
    apply_to_text: bool = True,
    manuscript: str | Path | None = None,
    complete: CompleteFn | None = None,
    on_llm_delta: LlmDelta | None = None,
) -> dict[str, Any]:
    """Revise subtitle text; timing stays from ASR. Manuscript is DeepSeek reference only."""

    try:
        source = _safe_project_path(project_path)
    except FileNotFoundError as error:
        return {"ok": False, "error": str(error)}
    try:
        project = _load_project(source)
    except Exception as error:
        return {"ok": False, "error": f"无法读取工程：{error}"}
    segments = list(project.get("segments") or [])
    if not segments:
        return {"ok": False, "error": "工程没有字幕段"}
    if not api_key and complete is None:
        return {"ok": False, "error": "缺少 API Key"}

    script_doc = None
    script_error = ""
    if manuscript is not None:
        try:
            script_doc = manuscript_document(manuscript)
        except ManuscriptError as error:
            script_error = str(error)
            if mode == "deepseek":
                return {"ok": False, "error": f"文稿无法读取：{error}"}

    settings = LlmSettings(
        provider_id="deepseek",
        api_key=api_key,
        base_url=base_url or DEFAULT_BASE_URL,
        model=model or DEFAULT_MODEL,
        reasoning_mode="off",
    )

    if mode == "custom":
        if not str(custom_prompt).strip():
            return {"ok": False, "error": "请填写自定义提示词"}
        extra = ""
        if script_doc is not None:
            extra = f"\n文稿参考（勿整段照抄）：\n{script_doc.display_text[:4000]}"
        system_prompt = (
            "你处理的是字幕文本修订。输入是 cue id 与字幕文字。"
            '只输出 JSON：{"groups":[{"source_ids":["c0001"],"text":"修订后"}]}。'
            "不要输出时间。每组必须且只能包含一个 source_id；不得合并、拆分、删除或重排字幕。"
            "每个输入 id 必须覆盖一次；无需修改时 text 保持原文。"
            f"\n用户要求：{custom_prompt.strip()}{extra}"
        )
        cues = _cues_from_segments(segments)
        runner = complete or (
            lambda s, prompt, batch: complete_subtitle_groups(
                s, prompt, batch, on_delta=on_llm_delta
            )
        )
        try:
            if on_llm_delta is not None:
                on_llm_delta("start", f"开始处理 {len(cues)} 条字幕")
            raw = runner(settings, system_prompt, cues)
            if on_llm_delta is not None:
                on_llm_delta("done", f"模型输出完成，共 {len(cues)} 条字幕")
        except Exception as error:
            return {"ok": False, "error": f"LLM 失败：{error}"}
        groups = raw.get("groups") if isinstance(raw, Mapping) else None
        if not isinstance(groups, list):
            return {"ok": False, "error": "LLM 返回缺少 groups"}
        new_segments = _apply_groups_to_segments(segments, groups)
        changed = sum(
            1
            for old, new in zip(segments, new_segments)
            if old.get("text") != new.get("text") and new.get("disabled") is not True
        )
        out_project = normalize_project({**project, "segments": new_segments})
        paths = _write_outputs(out_project, source, ".自定义修订")
        return {"ok": True, "mode": "custom", "changedCues": changed, "manuscriptUsed": script_doc is not None, **paths}

    # deepseek conservative ± manuscript reference
    enabled = _enabled_indices(segments)
    cues = _cues_from_segments(segments)
    script_map = _script_refs_for_segments(segments, script_doc) if script_doc is not None else {}
    payload = []
    for n, c in enumerate(cues):
        cid = c["id"]
        # aligner uses source cue ids like main-001; remap by enabled order
        matched, score = "", 0.0
        # script_map keys already in cXXXX form
        if cid in script_map:
            matched, score = script_map[cid]
        payload.append(
            {
                "cue_id": cid,
                "primary_asr": c["text"],
                "secondary_asr": None,
                "matched_script": matched or None,
                "match_score": float(score or 0.0),
            }
        )
    system_prompt = SYSTEM_PROMPT_WITH_SCRIPT if script_doc is not None else SYSTEM_PROMPT
    runner = complete or _default_complete
    try:
        if on_llm_delta is not None:
            on_llm_delta("start", f"开始处理 {len(payload)} 条字幕")
        if complete is None:
            raw = _default_complete(settings, system_prompt, payload, on_delta=on_llm_delta)
        else:
            raw = runner(settings, system_prompt, payload)
        if on_llm_delta is not None:
            on_llm_delta("done", f"模型输出完成，共 {len(payload)} 条字幕")
        parsed = _parse_results(raw, [p["cue_id"] for p in payload])
    except Exception as error:
        return {"ok": False, "error": f"DeepSeek 失败：{error}"}

    new_segments = copy.deepcopy(segments)
    id_to_idx = {f"c{n+1:04d}": i for n, i in enumerate(enabled)}
    changed = 0
    for result in parsed:
        seg_idx = id_to_idx.get(result.cue_id)
        if seg_idx is None:
            continue
        original = str(new_segments[seg_idx].get("text") or "")
        corrected = result.corrected_text
        if not corrected or corrected == original:
            continue
        if apply_to_text:
            new_segments[seg_idx]["text"] = corrected
        changed += 1
        pr = dict(new_segments[seg_idx].get("proofread") or {})
        pr.update(
            {
                "status": result.status or "uncertain",
                "asr_original": original,
                "corrected": corrected,
                "reason": result.reason or "deepseek revise",
                "script_text": (script_map.get(result.cue_id) or (None, 0))[0],
            }
        )
        new_segments[seg_idx]["proofread"] = pr
    suffix = ".修订" if apply_to_text else ".修订建议"
    out_project = normalize_project({**project, "segments": new_segments})
    paths = _write_outputs(out_project, source, suffix)
    return {
        "ok": True,
        "mode": "deepseek",
        "changedCues": changed,
        "manuscriptUsed": script_doc is not None,
        "manuscriptError": script_error,
        **paths,
    }


def resegment_project(
    project_path: Path | str,
    *,
    max_len: int = 20,
    min_len: int = 5,
    gap_split_ms: int = 750,
) -> dict[str, Any]:
    """Conservative sentence split applied in-place; writes only one project + one SRT.

    Overwrites the same ``<base>.mosp`` / ``<base>.srt`` family as the input
    (backup-style suffix is NOT created). If the input is already named
    ``*.修订.mosp``, outputs stay on that same stem.
    """

    from maw.bdversion.segment import resegment_segments

    try:
        source = _safe_project_path(project_path)
    except FileNotFoundError as error:
        return {"ok": False, "error": str(error)}
    try:
        project = _load_project(source)
    except Exception as error:
        return {"ok": False, "error": f"无法读取工程：{error}"}
    segments = list(project.get("segments") or [])
    if not segments:
        return {"ok": False, "error": "工程没有字幕段"}
    new_segments = resegment_segments(
        segments,
        max_len=max_len,
        min_len=min_len,
        gap_split_ms=gap_split_ms,
    )
    cleaned = []
    for seg in new_segments:
        item = dict(seg)
        item.pop("id", None)  # regenerate unique ids
        cleaned.append(item)
    out_project = normalize_project({**project, "segments": cleaned})
    paths = _write_outputs(out_project, source, "")
    return {"ok": True, "mode": "resegment", "cueCount": len(new_segments), **paths}
