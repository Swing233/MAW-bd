"""Phase 5 tests: dual ASR merge keeps primary timeline."""

from __future__ import annotations

import unittest

from maw.bdversion.dual_asr import (
    DualAsrConfig,
    PRIMARY_MODEL,
    SECONDARY_MODEL,
    dual_transcribe,
    merge_dual_asr,
    project_with_dual_asr,
    timeline_signature,
)


class DualMergeTests(unittest.TestCase):
    def test_secondary_never_changes_primary_timeline(self) -> None:
        primary = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"},
            {"id": "main-002", "start": 1000, "end": 2200, "text": "现场多说了一句"},
        ]
        secondary = [
            {"start": 0, "end": 900, "text": "今天介绍字幕工作流"},
            {"start": 900, "end": 2000, "text": "现场多说了一句"},
        ]
        before = timeline_signature(primary)
        result = merge_dual_asr(primary, secondary, config=DualAsrConfig(mode="dual"))
        after = timeline_signature(result.segments)
        self.assertEqual(before, after)
        self.assertEqual(result.segments[0]["start"], 0)
        self.assertEqual(result.segments[0]["end"], 1000)
        self.assertEqual(result.segments[0]["text"], "今天介绍自工作流")
        # secondary text recorded for LLM evidence
        self.assertIsNotNone(result.segments[0]["proofread"]["secondary_asr"])
        self.assertIn("工作流", result.segments[0]["proofread"]["secondary_asr"])
        # disagreement recorded when texts differ after normalize
        self.assertTrue(result.segments[0]["proofread"]["disagreement"]["flag"])

    def test_agreement_when_secondary_matches(self) -> None:
        primary = [{"id": "main-001", "start": 0, "end": 800, "text": "大家好"}]
        secondary = [{"start": 0, "end": 800, "text": "大家好"}]
        result = merge_dual_asr(primary, secondary, config=DualAsrConfig(mode="dual"))
        self.assertEqual(result.disagreement_count, 0)
        self.assertEqual(result.segments[0]["proofread"]["secondary_asr"], "大家好")
        self.assertFalse(result.segments[0]["proofread"]["disagreement"]["flag"])

    def test_single_mode_skips_secondary(self) -> None:
        primary = [{"id": "main-001", "start": 0, "end": 800, "text": "大家好"}]
        result = merge_dual_asr(primary, [], config=DualAsrConfig(mode="single"))
        self.assertIsNone(result.segments[0]["proofread"]["secondary_asr"])
        self.assertEqual(result.segments[0]["text"], "大家好")

    def test_project_with_dual_asr_sets_models(self) -> None:
        project = {
            "media": "clip.mp4",
            "segments": [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}],
        }
        secondary = [{"start": 0, "end": 1000, "text": "今天介绍字幕工作流"}]
        out = project_with_dual_asr(
            project,
            secondary,
            config=DualAsrConfig(mode="dual", primary_model=PRIMARY_MODEL, secondary_model=SECONDARY_MODEL),
        )
        self.assertEqual(out["model"], PRIMARY_MODEL)
        self.assertEqual(out["proofread_run"]["asr_mode"], "dual")
        self.assertEqual(out["proofread_run"]["primary_model"], PRIMARY_MODEL)
        self.assertEqual(out["proofread_run"]["secondary_model"], SECONDARY_MODEL)
        self.assertGreaterEqual(out["proofread_run"]["disagreement_count"], 1)
        # normalize kept
        self.assertEqual(out["segments"][0]["start"], 0)
        self.assertEqual(out["segments"][0]["text"], "今天介绍自工作流")

    def test_dual_transcribe_uses_primary_timeline(self) -> None:
        calls: list[str] = []

        def fake_transcribe(media_path, language=None, model=None, **kwargs):
            calls.append(model or "")
            if model == PRIMARY_MODEL:
                return {
                    "segments": [
                        {"id": "main-001", "start": 0, "end": 1200, "text": "主模型时间轴文本"},
                    ]
                }
            return {
                "segments": [
                    # different times — must be ignored
                    {"start": 111, "end": 999, "text": "副模型不同文本"},
                ]
            }

        primary, secondary, cfg = dual_transcribe(
            "clip.mp4",
            config=DualAsrConfig(mode="dual"),
            transcribe_fn=fake_transcribe,
        )
        self.assertEqual(calls, [PRIMARY_MODEL, SECONDARY_MODEL])
        self.assertEqual(primary[0]["start"], 0)
        self.assertEqual(primary[0]["end"], 1200)
        self.assertEqual(primary[0]["text"], "主模型时间轴文本")
        self.assertEqual(secondary[0]["start"], 111)

        merged = merge_dual_asr(primary, secondary, config=cfg)
        self.assertEqual(merged.segments[0]["start"], 0)
        self.assertEqual(merged.segments[0]["end"], 1200)
        self.assertEqual(merged.segments[0]["text"], "主模型时间轴文本")
        self.assertIsNotNone(merged.segments[0]["proofread"]["secondary_asr"])

    def test_dual_transcribe_single_mode_only_calls_primary(self) -> None:
        calls: list[str] = []

        def fake_transcribe(media_path, language=None, model=None, **kwargs):
            calls.append(model or "")
            return {"segments": [{"id": "m", "start": 0, "end": 10, "text": "x"}]}

        primary, secondary, cfg = dual_transcribe(
            "a.mp4",
            config=DualAsrConfig(mode="single"),
            transcribe_fn=fake_transcribe,
        )
        self.assertEqual(calls, [PRIMARY_MODEL])
        self.assertEqual(secondary, [])
        self.assertEqual(cfg.mode, "single")

    def test_missing_transcribe_fn_raises(self) -> None:
        with self.assertRaises(ValueError):
            dual_transcribe("a.mp4")

    def test_empty_primary_raises(self) -> None:
        def fake_transcribe(media_path, language=None, model=None, **kwargs):
            return {"segments": []}

        with self.assertRaises(ValueError):
            dual_transcribe("a.mp4", transcribe_fn=fake_transcribe)

    def test_deepseek_cue_builder_consumes_secondary(self) -> None:
        from maw.bdversion import align_segments_to_manuscript, manuscript_from_paste
        from maw.bdversion.deepseek import build_proofread_cues
        from maw.bdversion.dual_asr import merge_dual_asr

        primary = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        secondary = [{"start": 0, "end": 1000, "text": "今天介绍字幕工作流"}]
        merged = merge_dual_asr(primary, secondary, config=DualAsrConfig(mode="dual"))
        doc = manuscript_from_paste("今天介绍字幕工作流")
        alignment = align_segments_to_manuscript(merged.segments, doc)
        cues = build_proofread_cues(
            alignment,
            secondary_texts=merged.secondary_texts_by_index(),
        )
        self.assertTrue(cues[0].route_llm)
        self.assertEqual(cues[0].secondary_asr, "今天介绍字幕工作流")


if __name__ == "__main__":
    unittest.main()
