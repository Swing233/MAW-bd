# pyright: reportAny=false
"""Focused postprocess pipeline: fixed replacement only.

旧的文稿匹配 / OCR / 翻译 / LLM 重写步骤已在精简版移除。
保守 DeepSeek 校对接入 maw.bdversion（Phase 4），不在此管线自动改写。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Final

from maw.output_naming import format_elapsed, operation_suffix
from maw.postprocess import (
    FixedProcessRequest,
    OutputMode,
    Replacement,
    run_fixed_process,
)
from maw.postprocess_io import SubtitleArtifact
from maw.text_conversion import TextConversion, normalize_text_conversion_mode

POSTPROCESS_PLAN_VERSION: Final[int] = 2
POSTPROCESS_CONFIG_FILENAME: Final[str] = "maw-postprocess.json"
STEP_ORDER: Final[tuple[str, ...]] = ("replace",)


class PostprocessCancelled(RuntimeError):
    pass


class PostprocessPipelineError(RuntimeError):
    pass


@dataclass
class PostprocessPipelineResult:
    artifacts: tuple[SubtitleArtifact, ...] = ()
    warnings: tuple[str, ...] = ()
    elapsed: str = ""


def default_postprocess_plan() -> dict[str, object]:
    return {
        "version": POSTPROCESS_PLAN_VERSION,
        "enabled": False,
        "retainIntermediate": False,
        "steps": [
            {
                "id": "replace",
                "enabled": False,
                "replacements": [],
                "replacementSeparator": "arrow",
                "replacementTrim": True,
                "replacementCustomSeparator": "",
                "conversion": TextConversion.OFF.value,
            }
        ],
    }


def normalize_plan(raw: object) -> dict[str, object]:
    defaults = default_postprocess_plan()
    if not isinstance(raw, Mapping):
        return defaults
    steps_in = raw.get("steps")
    step: dict[str, object] = dict(defaults["steps"][0])  # type: ignore[index]
    if isinstance(steps_in, list):
        for item in steps_in:
            if isinstance(item, Mapping) and str(item.get("id")) == "replace":
                for key in step:
                    if key in item:
                        step[key] = item[key]
                break
    return {
        "version": POSTPROCESS_PLAN_VERSION,
        "enabled": bool(raw.get("enabled")),
        "retainIntermediate": bool(raw.get("retainIntermediate")),
        "steps": [step],
    }


def enabled_steps(plan: Mapping[str, object]) -> list[str]:
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return []
    out: list[str] = []
    for item in steps:
        if isinstance(item, Mapping) and item.get("id") in STEP_ORDER and item.get("enabled"):
            out.append(str(item["id"]))
    return out


def load_postprocess_plan(path: Path) -> dict[str, object]:
    import json

    if not path.is_file():
        return default_postprocess_plan()
    try:
        return normalize_plan(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return default_postprocess_plan()


def save_postprocess_plan(path: Path, plan: Mapping[str, object]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalize_plan(plan), ensure_ascii=False, indent=2), encoding="utf-8")


def validate_plan(plan: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    if plan.get("enabled") and not enabled_steps(plan):
        errors.append("后处理已开启，但没有启用任何步骤（精简版仅支持固定替换）")
    return errors


def is_llm_verified(*_a, **_k) -> bool:
    return False


def invalidate_llm_verification_if_changed(*_a, **_k) -> None:
    return None


def record_llm_verification(*_a, **_k) -> None:
    return None


def snapshot_postprocess_llm_settings(*_a, **_k) -> dict[str, object]:
    return {}


def run_postprocess_pipeline(
    *,
    project_path: Path,
    srt_path: Path | None,
    plan: Mapping[str, object],
    output_mode: OutputMode = OutputMode.BOTH,
    on_status: Callable[..., None] | None = None,
    cancel_event: Event | None = None,
) -> PostprocessPipelineResult:
    import time

    if cancel_event is not None and cancel_event.is_set():
        raise PostprocessCancelled("postprocess cancelled")
    steps = enabled_steps(plan)
    if not steps:
        raise PostprocessPipelineError("没有可执行的后处理步骤")
    started = time.time()
    artifacts: list[SubtitleArtifact] = []
    warnings: list[str] = []
    step_plan = None
    for item in plan.get("steps") or []:
        if isinstance(item, Mapping) and item.get("id") == "replace":
            step_plan = item
            break
    if step_plan is None:
        step_plan = default_postprocess_plan()["steps"][0]  # type: ignore[index]
    replacements: list[Replacement] = []
    raw_reps = step_plan.get("replacements") or []
    if isinstance(raw_reps, list):
        for row in raw_reps:
            if isinstance(row, Mapping):
                src = str(row.get("from") if "from" in row else row.get("source") or row.get("old") or "")
                dst = str(row.get("to") if "to" in row else row.get("target") or row.get("new") or "")
                if src or dst:
                    replacements.append(Replacement(source=src, target=dst))
            elif isinstance(row, str) and "=>" in row:
                left, right = row.split("=>", 1)
                replacements.append(Replacement(source=left.strip(), target=right.strip()))
    conversion = normalize_text_conversion_mode(step_plan.get("conversion"))
    request = FixedProcessRequest(
        project_path=project_path,
        srt_path=srt_path,
        replacements=tuple(replacements),
        conversion=conversion,
        output_mode=output_mode,
    )
    if on_status:
        on_status("replace")
    artifact = run_fixed_process(request)
    artifacts.append(artifact)
    warnings.extend(artifact.warnings)
    if cancel_event is not None and cancel_event.is_set():
        raise PostprocessCancelled("postprocess cancelled")
    return PostprocessPipelineResult(
        artifacts=tuple(artifacts),
        warnings=tuple(warnings),
        elapsed=format_elapsed(time.time() - started),
    )


def _operation_suffix(name: str) -> str:
    return operation_suffix(name)
