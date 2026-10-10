"""Human decisions on LLM suggestions, without changing the ASR timeline."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping


def review_rows(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for index, segment in enumerate(project.get("segments") or []):
        pr = segment.get("proofread") or {}
        original = pr.get("review_original", pr.get("asr_original"))
        corrected = pr.get("review_text", pr.get("corrected"))
        if not isinstance(original, str) or not isinstance(corrected, str) or not corrected or corrected == original:
            continue
        # Old manual edits are not evidence that an LLM changed the cue.
        if pr.get("status") == "manual" and "review_text" not in pr:
            continue
        current = str(segment.get("text") or "")
        rows.append({"index": index, "start": segment.get("start"), "end": segment.get("end"),
                     "original": original, "corrected": corrected, "current": current,
                     "reason": pr.get("reason") or "", "state": pr.get("review_state") or "pending",
                     "locked": pr.get("status") == "manual" or current not in {original, corrected}})
    return rows


def apply_review_decisions(project: Mapping[str, Any], choices: list[dict[str, Any]]) -> dict[str, Any]:
    rows = {row["index"]: row for row in review_rows(project)}
    seen = set()
    for choice in choices:
        if not isinstance(choice, Mapping):
            raise ValueError("校对审查选项无效")
        index, accepted = choice.get("index"), choice.get("accepted")
        if type(index) is not int or type(accepted) is not bool or index in seen or index not in rows:
            raise ValueError("校对审查选项无效，请重新打开审查")
        if rows[index]["locked"]:
            raise ValueError("字幕已人工修改，不能覆盖，请重新打开审查")
        seen.add(index)
    result = copy.deepcopy(project)
    for choice in choices:
        row = rows[choice["index"]]
        segment = result["segments"][choice["index"]]
        segment["text"] = row["corrected"] if choice["accepted"] else row["original"]
        segment["proofread"].update(review_original=row["original"], review_text=row["corrected"],
                                     review_state="accepted" if choice["accepted"] else "rejected")
    return result


def project_token(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
