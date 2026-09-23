"""DeepSeek conservative proofread — speech is ground truth.

Never rewrites subtitle timing or automatically overwrites ``segments[*].text``.
``corrected_text`` is stored on ``proofread.corrected`` for human confirmation.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from maw.bdversion.alignment import AlignmentResult
from maw.bdversion.project_meta import PROOFREAD_STATUSES, attach_alignment_to_segments
from maw.bdversion.status import should_call_llm
from maw.postprocess_llm import LlmClientError, LlmDelta, LlmSettings, _read_stream_response, preset_by_id
from maw.project_preview import JsonDict

DEFAULT_BASE_URL: Final = "https://api.deepseek.com"
DEFAULT_MODEL: Final = "deepseek-flash"
DEFAULT_TEMPERATURE: Final = 0.1
PROVIDER_ID: Final = "deepseek"
LLM_SCORE_MIN_FOR_VERIFY: Final = 0.72

SYSTEM_PROMPT: Final = (
    "你处理的是字幕保守校对，不是改写。\n"
    "最高规则：\n"
    "1. 实际语音是真源，文稿只是纠错参考。\n"
    "2. 不允许将现场发挥、口语、重复、临时增删修改成文稿原文。\n"
    "3. 不允许润色，不允许改写句式。\n"
    "4. 不确定时保持 ASR 原文。\n"
    "5. 只有高度可能属于识别错误时才能修改（同音/近音错字、错别字、专有名词、人名、地名、技术词汇）。\n"
    "6. 不允许补入 ASR 中不存在的文稿内容。\n"
    "7. 不要输出或修改任何时间；不要改变字幕顺序。\n"
    "8. 校对文字中的明确数字默认使用阿拉伯数字（如‘二十五个’写作‘25个’）；只改变数字写法，绝不增删数字或改变语义。成语、人名、地名、专有名词中的汉字数字及含义不确定的数字保持原样。\n"
    "只返回一个严格有效的 JSON 对象，不要 Markdown 代码块或解释。\n"
    '返回格式：{"results":[{"id":"c0001","corrected_text":"...","status":"verified|improvised|uncertain",'
    '"changed":true|false,"reason":"..."}]}\n'
    "每个输入 cue 必须返回且只能返回一条同 id 结果；id 顺序与输入一致。\n"
    "若无需修改，corrected_text 必须与输入 primary_asr 完全一致，changed=false。"
)

ProofreadComplete = Callable[[LlmSettings, str, list[dict[str, Any]]], Mapping[str, Any]]


def deepseek_settings(
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
) -> LlmSettings:
    preset = preset_by_id(PROVIDER_ID)
    return LlmSettings(
        provider_id=PROVIDER_ID,
        api_key=api_key,
        base_url=base_url or preset.base_url or DEFAULT_BASE_URL,
        model=model or DEFAULT_MODEL,
        reasoning_mode="off",
    )


@dataclass(frozen=True, slots=True)
class ProofreadCue:
    cue_id: str
    cue_index: int
    primary_asr: str
    secondary_asr: str | None
    matched_script: str | None
    match_score: float
    initial_status: str
    route_llm: bool


@dataclass(frozen=True, slots=True)
class ProofreadResult:
    cue_id: str
    corrected_text: str
    status: str
    changed: bool
    reason: str
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class ConservativeProofreadOutcome:
    cues: tuple[ProofreadCue, ...]
    results: tuple[ProofreadResult, ...]
    called_llm: bool
    llm_cue_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def build_proofread_cues(
    alignment: AlignmentResult,
    *,
    secondary_texts: Mapping[int, str] | None = None,
) -> list[ProofreadCue]:
    secondary = secondary_texts or {}
    cues: list[ProofreadCue] = []
    for cue in alignment.cues:
        route = should_call_llm(cue.status, cue.match_score) and cue.asr_key != ""
        if cue.status == "verified":
            route = False
        cues.append(
            ProofreadCue(
                cue_id=cue.cue_id,
                cue_index=cue.cue_index,
                primary_asr=cue.asr_text,
                secondary_asr=secondary.get(cue.cue_index),
                matched_script=cue.script_text,
                match_score=cue.match_score,
                initial_status=cue.status,
                route_llm=route,
            )
        )
    return cues


def _llm_payload_cues(cues: Sequence[ProofreadCue]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for cue in cues:
        if not cue.route_llm:
            continue
        payload.append(
            {
                "cue_id": cue.cue_id,
                "primary_asr": cue.primary_asr,
                "secondary_asr": cue.secondary_asr,
                "matched_script": cue.matched_script,
                "match_score": cue.match_score,
            }
        )
    return payload


def _parse_results(raw: Mapping[str, Any], expected_ids: Sequence[str]) -> list[ProofreadResult]:
    results_raw = raw.get("results")
    if not isinstance(results_raw, list):
        raise LlmClientError("DeepSeek proofread response missing results[]", category="protocol")
    by_id: dict[str, ProofreadResult] = {}
    for item in results_raw:
        if not isinstance(item, Mapping):
            continue
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        status = str(item.get("status") or "uncertain")
        if status not in PROOFREAD_STATUSES:
            status = "uncertain"
        changed = bool(item.get("changed"))
        primary = None  # filled by caller context if needed
        corrected = item.get("corrected_text")
        if not isinstance(corrected, str) or not corrected.strip():
            corrected = ""
        reason = item.get("reason")
        by_id[rid] = ProofreadResult(
            cue_id=rid,
            corrected_text=corrected,
            status=status if status != "manual" else "uncertain",
            changed=changed,
            reason=reason if isinstance(reason, str) else "",
        )
        _ = primary
    out: list[ProofreadResult] = []
    for rid in expected_ids:
        if rid in by_id:
            out.append(by_id[rid])
        else:
            out.append(
                ProofreadResult(
                    cue_id=rid,
                    corrected_text="",
                    status="uncertain",
                    changed=False,
                    reason="missing in LLM response; kept ASR",
                    skipped=True,
                )
            )
    return out


def _default_complete(
    settings: LlmSettings,
    system_prompt: str,
    cues: list[dict[str, Any]],
    *,
    on_delta: LlmDelta | None = None,
) -> Mapping[str, Any]:
    """HTTP call against OpenAI-compatible DeepSeek; temperature fixed at 0.1."""

    import requests
    from requests.exceptions import RequestException

    base = settings.base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        endpoint = base
    else:
        endpoint = f"{base}/chat/completions"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(cues, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": DEFAULT_TEMPERATURE,
    }
    if on_delta is not None:
        payload["stream"] = True
    headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
    try:
        with requests.Session() as session:
            response = session.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=(10, 180),
                stream=on_delta is not None,
            )
            response.raise_for_status()
            if on_delta is not None:
                try:
                    body = _read_stream_response(response, on_delta, settings=settings)
                finally:
                    response.close()
            else:
                body = response.json()
    except RequestException as error:
        raise LlmClientError(f"DeepSeek request failed: {error}", category="network") from error
    if not isinstance(body, Mapping):
        raise LlmClientError("DeepSeek response must be a JSON object", category="protocol")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise LlmClientError("DeepSeek response missing choices/message/content", category="protocol") from error
    if isinstance(content, Mapping):
        return content
    text = str(content).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise LlmClientError(f"DeepSeek returned invalid JSON: {error}", category="protocol") from error
    if not isinstance(parsed, Mapping):
        raise LlmClientError("DeepSeek JSON root must be an object", category="protocol")
    return parsed


def run_conservative_proofread(
    alignment: AlignmentResult,
    api_key: str,
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    secondary_texts: Mapping[int, str] | None = None,
    complete: ProofreadComplete | None = None,
    settings: LlmSettings | None = None,
) -> ConservativeProofreadOutcome:
    """Route + optional DeepSeek call. Never mutates segment text or times."""

    if settings is None:
        settings = deepseek_settings(api_key, model=model, base_url=base_url)
    cues = build_proofread_cues(alignment, secondary_texts=secondary_texts)
    llm_cues = [cue for cue in cues if cue.route_llm]
    warnings: list[str] = []
    results: list[ProofreadResult] = []
    called = False

    by_id = {cue.cue_id: cue for cue in cues}
    if llm_cues:
        if not (api_key or settings.api_key):
            raise LlmClientError("DeepSeek API key is required", category="client")
        payload = _llm_payload_cues(llm_cues)
        runner = complete or _default_complete
        raw = runner(settings, SYSTEM_PROMPT, payload)
        parsed = _parse_results(raw, [cue.cue_id for cue in llm_cues])
        called = True
        for result in parsed:
            cue = by_id[result.cue_id]
            if result.skipped or not result.corrected_text:
                results.append(
                    ProofreadResult(
                        cue_id=cue.cue_id,
                        corrected_text=cue.primary_asr,
                        status="uncertain",
                        changed=False,
                        reason=result.reason or "kept ASR",
                    )
                )
                continue
            changed = result.corrected_text != cue.primary_asr
            status = result.status
            if not changed:
                # LLM confirmed ASR; high-enough alignment → verified
                if cue.match_score >= LLM_SCORE_MIN_FOR_VERIFY:
                    status = "verified"
                elif status not in PROOFREAD_STATUSES:
                    status = cue.initial_status
            results.append(
                ProofreadResult(
                    cue_id=cue.cue_id,
                    corrected_text=result.corrected_text,
                    status=status if status in PROOFREAD_STATUSES else "uncertain",
                    changed=changed,
                    reason=result.reason,
                )
            )
    else:
        warnings.append("没有需要 DeepSeek 校对的字幕（已全部 verified / improvised / 低分 uncertain）")

    for cue in cues:
        if cue.route_llm:
            continue
        results.append(
            ProofreadResult(
                cue_id=cue.cue_id,
                corrected_text="",
                status=cue.initial_status,
                changed=False,
                reason="local route; no LLM",
            )
        )

    # stable order by cue_index
    order = {cue.cue_id: cue.cue_index for cue in cues}
    results.sort(key=lambda item: order.get(item.cue_id, 0))
    return ConservativeProofreadOutcome(
        cues=tuple(cues),
        results=tuple(results),
        called_llm=called,
        llm_cue_ids=tuple(cue.cue_id for cue in llm_cues),
        warnings=tuple(warnings),
    )


def apply_proofread_outcome_to_segments(
    segments: Sequence[Mapping[str, Any]],
    alignment: AlignmentResult,
    outcome: ConservativeProofreadOutcome,
    *,
    apply_colors: bool = True,
    overwrite_text: bool = False,
) -> list[JsonDict]:
    """Attach proofread metadata from outcome.

    ``overwrite_text`` defaults to False (user decision): ASR text stays unless
    explicitly enabled. Timing fields are never modified.
    """

    updated = attach_alignment_to_segments(segments, alignment, apply_colors=apply_colors)
    by_cue = {result.cue_id: result for result in outcome.results}
    for segment in updated:
        sid = segment.get("id")
        if not isinstance(sid, str) or sid not in by_cue:
            continue
        result = by_cue[sid]
        payload = segment.get("proofread")
        if not isinstance(payload, dict):
            payload = {}
        else:
            payload = dict(payload)
        payload["status"] = result.status
        if result.changed and result.corrected_text:
            payload["corrected"] = result.corrected_text
        elif result.reason == "local route; no LLM" or not result.corrected_text:
            payload["corrected"] = None
        else:
            payload["corrected"] = result.corrected_text
        payload["reason"] = result.reason or None
        if payload.get("asr_original") is None:
            payload["asr_original"] = segment.get("text")
        segment["proofread"] = payload
        if overwrite_text and result.changed and result.corrected_text:
            # Explicit opt-in only; still never touch start/end/items.
            segment["text"] = result.corrected_text
        if apply_colors:
            from maw.bdversion.project_meta import apply_status_color

            apply_status_color(segment, overwrite=True)
    return updated
