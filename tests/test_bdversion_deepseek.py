"""Phase 4 tests: DeepSeek routing + conservative proofread protocol (mocked API)."""

from __future__ import annotations

import unittest

from maw.bdversion import align_segments_to_manuscript, manuscript_from_paste
from maw.bdversion.deepseek import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    _default_complete,
    apply_proofread_outcome_to_segments,
    build_proofread_cues,
    deepseek_settings,
    run_conservative_proofread,
)
from maw.bdversion.project_meta import project_with_alignment
from maw.postprocess_llm import LlmClientError


def _align(segments, script_text):
    doc = manuscript_from_paste(script_text)
    return align_segments_to_manuscript(segments, doc)


class RoutingTests(unittest.TestCase):
    def test_default_complete_streams_output_deltas(self) -> None:
        import json
        from unittest.mock import patch

        content = '{"results":[]}'
        event = {"choices": [{"delta": {"content": content}}]}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def iter_lines(self, decode_unicode=False):
                del decode_unicode
                return [b"data: " + json.dumps(event).encode("utf-8"), b"data: [DONE]"]

            def close(self):
                return None

        class FakeSession:
            posted = None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def post(self, endpoint, **kwargs):
                del endpoint
                FakeSession.posted = kwargs
                return FakeResponse()

        deltas = []
        with patch("requests.Session", FakeSession):
            result = _default_complete(
                deepseek_settings("sk-test"),
                SYSTEM_PROMPT,
                [],
                on_delta=lambda kind, text: deltas.append((kind, text)),
            )
        self.assertEqual(result, {"results": []})
        self.assertEqual(deltas, [("content", content)])
        self.assertTrue(FakeSession.posted["json"]["stream"])
        self.assertTrue(FakeSession.posted["stream"])

    def test_exact_match_does_not_call_llm(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "大家好"}]
        alignment = _align(segments, "大家好")
        cues = build_proofread_cues(alignment)
        self.assertEqual(cues[0].initial_status, "verified")
        self.assertFalse(cues[0].route_llm)
        outcome = run_conservative_proofread(alignment, api_key="", complete=lambda *a: {"results": []})
        self.assertFalse(outcome.called_llm)
        self.assertEqual(outcome.results[0].status, "verified")
        self.assertFalse(outcome.results[0].changed)
        # 本地路由不产生 corrected 建议
        self.assertEqual(outcome.results[0].corrected_text, "")

    def test_improvised_does_not_call_llm(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "完全现场即兴的一句话"}]
        alignment = _align(segments, "文稿里完全另一句")
        cues = build_proofread_cues(alignment)
        self.assertEqual(cues[0].initial_status, "improvised")
        self.assertFalse(cues[0].route_llm)

    def test_high_score_diff_routes_to_llm(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")
        cues = build_proofread_cues(alignment)
        self.assertEqual(cues[0].initial_status, "uncertain")
        self.assertTrue(cues[0].route_llm)
        self.assertGreaterEqual(cues[0].match_score, 0.72)

    def test_system_prompt_contains_speech_first_rules(self) -> None:
        self.assertIn("语音是真源", SYSTEM_PROMPT)
        self.assertIn("不允许润色", SYSTEM_PROMPT)
        self.assertIn("不确定时保持 ASR", SYSTEM_PROMPT)
        self.assertIn("不要输出或修改任何时间", SYSTEM_PROMPT)
        self.assertIn("数字默认使用阿拉伯数字", SYSTEM_PROMPT)


class ConservativeApplyTests(unittest.TestCase):
    def test_llm_typo_fix_written_to_corrected_not_text(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"},
            {"id": "main-002", "start": 1000, "end": 2000, "text": "完全现场即兴内容"},
        ]
        doc = manuscript_from_paste("今天介绍字幕工作流\n完全现场即兴内容")
        alignment = align_segments_to_manuscript(segments, doc)

        def fake_complete(settings, system_prompt, cues):
            self.assertEqual(settings.model, DEFAULT_MODEL)
            self.assertTrue(cues)
            results = []
            for cue in cues:
                results.append(
                    {
                        "id": cue["cue_id"],
                        "corrected_text": "今天介绍字幕工作流",
                        "status": "uncertain",
                        "changed": True,
                        "reason": "同音错字：自→字",
                    }
                )
            return {"results": results}

        outcome = run_conservative_proofread(
            alignment,
            api_key="sk-test",
            complete=fake_complete,
        )
        self.assertTrue(outcome.called_llm)
        self.assertIn("main-001", outcome.llm_cue_ids)
        self.assertNotIn("main-002", outcome.llm_cue_ids)

        updated = apply_proofread_outcome_to_segments(segments, alignment, outcome)
        # text unchanged (speech is truth)
        self.assertEqual(updated[0]["text"], "今天介绍自工作流")
        self.assertEqual(updated[0]["start"], 0)
        self.assertEqual(updated[0]["end"], 1000)
        self.assertEqual(updated[0]["proofread"]["corrected"], "今天介绍字幕工作流")
        self.assertEqual(updated[0]["proofread"]["asr_original"], "今天介绍自工作流")
        self.assertTrue(updated[0]["proofread"]["reason"])
        # improvised segment keeps ASR, no corrected overwrite
        self.assertEqual(updated[1]["text"], "完全现场即兴内容")
        self.assertIsNone(updated[1]["proofread"].get("corrected") or None)

    def test_explicit_overwrite_text_still_keeps_timing(self) -> None:
        segments = [{"id": "main-001", "start": 100, "end": 900, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")

        def fake_complete(settings, system_prompt, cues):
            return {
                "results": [
                    {
                        "id": cues[0]["cue_id"],
                        "corrected_text": "今天介绍字幕工作流",
                        "status": "uncertain",
                        "changed": True,
                        "reason": "typo",
                    }
                ]
            }

        outcome = run_conservative_proofread(alignment, api_key="sk", complete=fake_complete)
        updated = apply_proofread_outcome_to_segments(
            segments, alignment, outcome, overwrite_text=True
        )
        self.assertEqual(updated[0]["text"], "今天介绍字幕工作流")
        self.assertEqual(updated[0]["start"], 100)
        self.assertEqual(updated[0]["end"], 900)

    def test_llm_keeps_asr_marks_verified_when_score_high(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")

        def fake_complete(settings, system_prompt, cues):
            return {
                "results": [
                    {
                        "id": cues[0]["cue_id"],
                        "corrected_text": "今天介绍自工作流",
                        "status": "uncertain",
                        "changed": False,
                        "reason": "可能是口语，保持 ASR",
                    }
                ]
            }

        outcome = run_conservative_proofread(alignment, api_key="sk", complete=fake_complete)
        updated = apply_proofread_outcome_to_segments(segments, alignment, outcome)
        self.assertEqual(updated[0]["proofread"]["status"], "verified")
        self.assertEqual(updated[0]["text"], "今天介绍自工作流")
        self.assertEqual(updated[0]["color"]["name"], "green")

    def test_missing_llm_ids_keep_asr(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")

        def fake_complete(settings, system_prompt, cues):
            return {"results": []}

        outcome = run_conservative_proofread(alignment, api_key="sk", complete=fake_complete)
        self.assertTrue(outcome.called_llm)
        self.assertEqual(outcome.results[0].corrected_text, "今天介绍自工作流")
        self.assertFalse(outcome.results[0].changed)

    def test_no_api_key_without_llm_route(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "大家好"}]
        alignment = _align(segments, "大家好")
        # No LLM route → key not required
        outcome = run_conservative_proofread(alignment, api_key="")
        self.assertFalse(outcome.called_llm)

    def test_api_key_required_when_llm_routed(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")
        with self.assertRaises(LlmClientError):
            run_conservative_proofread(alignment, api_key="")

    def test_deepseek_settings_defaults(self) -> None:
        settings = deepseek_settings("sk-x")
        self.assertEqual(settings.provider_id, "deepseek")
        self.assertEqual(settings.model, DEFAULT_MODEL)
        self.assertEqual(settings.base_url, "https://api.deepseek.com")
        self.assertEqual(settings.api_key, "sk-x")

    def test_project_roundtrip_with_corrected_metadata(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        alignment = _align(segments, "今天介绍字幕工作流")

        def fake_complete(settings, system_prompt, cues):
            return {
                "results": [
                    {
                        "id": cues[0]["cue_id"],
                        "corrected_text": "今天介绍字幕工作流",
                        "status": "uncertain",
                        "changed": True,
                        "reason": "typo",
                    }
                ]
            }

        outcome = run_conservative_proofread(alignment, api_key="sk", complete=fake_complete)
        base = {"media": "a.mp4", "segments": segments}
        aligned = project_with_alignment(base, alignment)
        # re-apply outcome onto aligned segments
        aligned["segments"] = apply_proofread_outcome_to_segments(
            aligned["segments"], alignment, outcome
        )
        from maw.project import normalize_project
        from maw.project_io import serialize_mosp
        import json

        normalized = normalize_project(aligned)
        data = json.loads(serialize_mosp(normalized))
        self.assertEqual(data["segments"][0]["text"], "今天介绍自工作流")
        self.assertEqual(data["segments"][0]["proofread"]["corrected"], "今天介绍字幕工作流")


if __name__ == "__main__":
    unittest.main()
