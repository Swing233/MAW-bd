from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest import mock

from generate_subtitle_qwen_api import (
    build_segments_from_api_sentences,
    generate_srt,
    QWEN3_ASR_FILETRANS_MODEL,
    split_segments_auto,
    submit_filetrans,
)
from maw.bdversion import align_segments_to_manuscript, manuscript_from_paste
from maw.bdversion.project_meta import project_with_alignment
from maw.bdversion.deepseek import (
    apply_proofread_outcome_to_segments,
    run_conservative_proofread,
)
from maw.bdversion.segment import resegment_segments
from maw.project import normalize_project


def char_items(text: str, *, gap_after: dict[int, int] | None = None) -> list[dict]:
    result = []
    cursor = 0
    for index, char in enumerate(text):
        result.append({"text": char, "start": cursor, "end": cursor + 100})
        cursor += 100 + (gap_after or {}).get(index, 0)
    return result


def texts(segments: list[dict]) -> list[str]:
    return [str(segment.get("text") or "") for segment in segments]


class NaturalSegmentationTests(unittest.TestCase):
    def split(self, text: str, *, gap_after: dict[int, int] | None = None) -> list[dict]:
        return split_segments_auto(
            char_items(text, gap_after=gap_after),
            max_len=20,
            min_len=5,
            gap_split_ms=750,
            natural_cjk=True,
            split_mode="continuous",
        )

    def test_short_complete_sentence_stays_one_cue(self) -> None:
        self.assertEqual(texts(self.split("今天开会。")), ["今天开会。"])

    def test_consecutive_strong_punctuation_keeps_sentence_boundaries(self) -> None:
        self.assertEqual(
            texts(self.split("你好。准备好了吗？现在开始！")),
            ["你好。", "准备好了吗？", "现在开始！"],
        )

    def test_long_sentence_prefers_clause_punctuation(self) -> None:
        result = self.split("我们先介绍项目背景，然后说明字幕流程，最后检查导出结果。")
        self.assertGreaterEqual(len(result), 2)
        self.assertTrue(any(part.endswith("，") for part in texts(result)[:-1]))
        self.assertTrue(all(len(part) <= 25 for part in texts(result)))

    def test_unpunctuated_chinese_uses_semantic_dp(self) -> None:
        result = self.split("今天我们继续介绍字幕编辑流程接下来演示如何导入视频并检查最终结果")
        self.assertGreater(len(result), 1)
        self.assertTrue(all(len(part) <= 25 for part in texts(result)))
        self.assertEqual("".join(texts(result)), "今天我们继续介绍字幕编辑流程接下来演示如何导入视频并检查最终结果")

    def test_real_strong_pause_beats_length_target(self) -> None:
        text = "今天介绍字幕工作流然后继续演示导出"
        pause_index = text.index("流")
        result = self.split(text, gap_after={pause_index: 900})
        self.assertEqual(texts(result)[0], "今天介绍字幕工作流")

    def test_names_titles_places_and_technical_terms_are_not_split(self) -> None:
        result = self.split("今天由张三丰教授在北京市海淀区介绍Qwen3-ASR字幕系统的完整流程")
        joined = "|".join(texts(result))
        for protected in ("张三丰教授", "北京市海淀区", "Qwen3-ASR"):
            self.assertIn(protected, joined.replace("|", ""))
            self.assertNotIn(protected[: max(1, len(protected) // 2)] + "|", joined)

    def test_number_and_measure_word_stay_together(self) -> None:
        result = self.split("这个过程大约需要3分钟然后再检查25个字幕片段是否正确")
        joined = "|".join(texts(result))
        self.assertNotIn("3|分钟", joined)
        self.assertNotIn("25|个", joined)

    def test_versions_and_mixed_language_stay_atomic(self) -> None:
        result = self.split("请使用Final Cut Pro 10.8.1导入Qwen3-ASR生成的FCPXML文件")
        joined = "|".join(texts(result))
        self.assertNotIn("Final| Cut", joined)
        self.assertNotIn("10.|8.1", joined)
        self.assertNotIn("Qwen3-|ASR", joined)

    def test_short_tail_is_rebalanced(self) -> None:
        result = self.split("今天我们详细介绍新的字幕编辑工作流程和导出方法以及它")
        self.assertGreater(len(result), 1)
        self.assertGreaterEqual(len(texts(result)[-1]), 5)

    def test_itemless_sentence_uses_marked_estimated_timing_without_items(self) -> None:
        text = "今天我们介绍一个没有词级时间戳但仍然需要自然断句的长句子然后检查结果"
        result = build_segments_from_api_sentences(
            [{"start": 100, "end": 8100, "text": text}],
            max_len=20,
            min_len=5,
            gap_split_ms=750,
            split_mode="continuous",
        )
        self.assertGreater(len(result), 1)
        self.assertEqual("".join(texts(result)), text)
        self.assertTrue(all(segment.get("timing_estimated") is True for segment in result))
        self.assertTrue(all("items" not in segment for segment in result))
        self.assertEqual(result[0]["start"], 100)
        self.assertEqual(result[-1]["end"], 8100)
        self.assertTrue(all(left["end"] == right["start"] for left, right in zip(result, result[1:])))

    def test_real_items_define_internal_boundaries(self) -> None:
        text = "今天介绍字幕工作流然后继续演示导出结果"
        items = char_items(text, gap_after={8: 900})
        result = build_segments_from_api_sentences(
            [{"start": 0, "end": items[-1]["end"], "text": text, "items": items}],
            max_len=20,
            min_len=5,
            gap_split_ms=750,
            split_mode="continuous",
        )
        self.assertEqual(result[0]["end"], items[8]["end"])
        self.assertEqual(result[1]["start"], items[9]["start"])
        self.assertNotIn("timing_estimated", result[0])

    def test_manual_resegment_never_merges_existing_asr_cues(self) -> None:
        original = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "第一句。"},
            {"id": "main-002", "start": 1500, "end": 2500, "text": "第二句。"},
        ]
        result = resegment_segments(original)
        self.assertEqual([(s["start"], s["end"], s["text"]) for s in result], [(0, 1000, "第一句。"), (1500, 2500, "第二句。")])

    def test_manuscript_alignment_keeps_count_and_time(self) -> None:
        segments = [
            {"id": "main-001", "start": 100, "end": 900, "text": "大家好", "items": [{"text": "大家好", "start": 100, "end": 900}]},
            {"id": "main-002", "start": 1000, "end": 1800, "text": "开始演示", "items": [{"text": "开始演示", "start": 1000, "end": 1800}]},
        ]
        before = copy.deepcopy(segments)
        aligned = align_segments_to_manuscript(segments, manuscript_from_paste("大家好。开始演示。"))
        output = project_with_alignment({"segments": segments}, aligned)["segments"]
        self.assertEqual([(s["start"], s["end"], s.get("items")) for s in output], [(s["start"], s["end"], s.get("items")) for s in before])
        self.assertEqual(len(output), len(before))

    def test_llm_proofread_keeps_order_count_and_all_timing(self) -> None:
        segments = [
            {"id": "main-001", "start": 100, "end": 900, "text": "字幕工做流", "items": [{"text": "字幕工做流", "start": 100, "end": 900}]},
            {"id": "main-002", "start": 1000, "end": 1800, "text": "现场发挥", "items": [{"text": "现场发挥", "start": 1000, "end": 1800}]},
        ]
        before = copy.deepcopy(segments)
        alignment = align_segments_to_manuscript(segments, manuscript_from_paste("字幕工作流"))

        def complete(_settings, _prompt, cues):
            return {"results": [{"id": cues[0]["cue_id"], "corrected_text": "字幕工作流", "status": "uncertain", "changed": True, "reason": "同音字"}]}

        outcome = run_conservative_proofread(alignment, api_key="sk-test", complete=complete)
        output = apply_proofread_outcome_to_segments(segments, alignment, outcome, overwrite_text=True)
        self.assertEqual([s["id"] for s in output], [s["id"] for s in before])
        self.assertEqual([(s["start"], s["end"], s["items"]) for s in output], [(s["start"], s["end"], s["items"]) for s in before])

    def test_legacy_project_and_single_line_srt(self) -> None:
        legacy = normalize_project({"segments": [{"start": 0, "end": 1000, "text": "第一行\n第二行"}]})
        self.assertEqual(legacy["schema"], "moy.asr.project.v1")
        srt = generate_srt(legacy["segments"])
        self.assertIn("第一行 第二行", srt)
        self.assertIn("00:00:00,000 --> 00:00:01,000", srt)

    @mock.patch("generate_subtitle_qwen_api.requests.post")
    def test_qwen3_always_requests_real_word_timestamps(self, post: mock.Mock) -> None:
        response = mock.Mock()
        response.json.return_value = {"output": {"task_id": "task-1"}}
        post.return_value = response
        submit_filetrans(
            "https://dashscope.aliyuncs.com",
            "secret",
            "oss://temporary/audio.wav",
            language="zh",
            enable_words=False,
            enable_itn=False,
            model=QWEN3_ASR_FILETRANS_MODEL,
        )
        payload = post.call_args.kwargs["json"]
        self.assertIs(payload["parameters"]["enable_words"], True)


class LauncherContractTests(unittest.TestCase):
    def test_asr_worker_does_not_auto_resegment(self) -> None:
        source = Path("maw/focus_launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("_auto_resegment_after_asr", source)
        self.assertIn('"20"', source)
        self.assertIn('"750"', source)


if __name__ == "__main__":
    unittest.main()
