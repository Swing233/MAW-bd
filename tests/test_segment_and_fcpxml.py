from __future__ import annotations
import unittest
from maw.bdversion.segment import split_items_sentence_aware
from maw.bdversion.revise import resegment_project
from maw.local_asr import QWEN_DEFAULT_MODEL
from generate_subtitle_local import build_parser
import json
import tempfile
from pathlib import Path

class SegmentTests(unittest.TestCase):
    def test_qwen_default_17b(self):
        self.assertEqual(QWEN_DEFAULT_MODEL, "Qwen/Qwen3-ASR-1.7B")

    def test_local_segmentation_defaults_use_normal_reading_limit(self):
        args = build_parser().parse_args(["input.wav"])
        self.assertEqual((args.max_len, args.min_len, args.gap_split), (20, 5, 750))

    def test_sentence_breaks_preserve_text(self):
        text = "你好。今天介绍工作流。这一句很长很长很长很长很长很长很长很长没有句号"
        items = [{"text": ch, "start": i, "end": i + 1} for i, ch in enumerate(text)]
        groups = split_items_sentence_aware(items)
        texts = ["".join(x["text"] for x in g) for g in groups]
        self.assertEqual(texts[0], "你好。")
        self.assertTrue(texts[1].startswith("今天介绍工作流。"))
        self.assertTrue(any("没有句号" in t for t in texts))
        self.assertEqual("".join(texts), text)

    def test_long_unpunctuated_speech_is_bounded(self):
        text = "这是一段完全没有任何标点而且会持续很久的现场讲话内容我们还会继续补充细节说明方便大家理解完整流程"
        items = [{"text": text, "start": 0, "end": 9600}]
        groups = split_items_sentence_aware(items, max_len=28)
        texts = ["".join(item["text"] for item in group) for group in groups]
        self.assertGreater(len(texts), 1)
        self.assertTrue(all(len(part) <= 28 for part in texts))
        self.assertEqual("".join(texts), text)
        self.assertEqual(groups[0][0]["start"], 0)
        self.assertEqual(groups[-1][-1]["end"], 9600)

    def test_long_sentence_prefers_clause_and_keeps_latin_words(self):
        text = "我们先介绍整个流程的背景和设计思路，然后再讲如何导入文稿和完成字幕校对，最后查看导出结果。"
        groups = split_items_sentence_aware([{"text": text, "start": 0, "end": 9000}], max_len=28)
        texts = ["".join(item["text"] for item in group) for group in groups]
        self.assertTrue(texts[0].endswith("，"))
        self.assertTrue(all(len(part) <= 28 for part in texts))
        english = "We explain the complete subtitle workflow and then export the result."
        groups = split_items_sentence_aware([{"text": english, "start": 0, "end": 7000}], max_len=28)
        self.assertEqual("".join(item["text"] for group in groups for item in group), english)
        self.assertNotIn("work|flow", "|".join("".join(item["text"] for item in group) for group in groups))

    def test_resegment_writes_single_pair_not_断句_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "clip.mosp"
            fp.write_text(json.dumps({"segments": [{
                "id": "main-001", "start": 0, "end": 3000,
                "text": "第一句。第二句有句号结束。"
            }]}, ensure_ascii=False), encoding="utf-8")
            out = resegment_project(fp)
            self.assertTrue(out["ok"])
            self.assertNotIn("断句", Path(out["projectPath"]).name)
            self.assertTrue(Path(out["projectPath"]).exists())
            self.assertTrue(Path(out["srtPath"]).exists())

    def test_resegment_uses_revised_text_not_stale_items(self):
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "revised.mosp"
            text = "这是修订后的第一句话。这里是修订后的第二句话。"
            fp.write_text(json.dumps({"segments": [{
                "start": 0, "end": 5000, "text": text,
                "items": [{"text": "旧的识别文本", "start": 0, "end": 5000}],
            }]}, ensure_ascii=False), encoding="utf-8")
            out = resegment_project(fp)
            self.assertTrue(out["ok"])
            saved = json.loads(Path(out["projectPath"]).read_text(encoding="utf-8"))
            self.assertEqual("".join(seg["text"] for seg in saved["segments"]), text)
            self.assertEqual(len(saved["segments"]), 2)

class FlowTests(unittest.TestCase):
    def test_launcher_no_auto_reseg_button(self):
        html = Path("web/launcher/index.html").read_text(encoding="utf-8")
        self.assertNotIn("btn-resegment", html)
        self.assertIn("log-rail", html)
        src = Path("maw/focus_launcher.py").read_text(encoding="utf-8")
        self.assertIn("仅识别", src)
        self.assertNotIn("_auto_resegment_after_asr", src)
        self.assertIn("max_len=20, min_len=5, gap_split_ms=750", src)
        self.assertIn("保留 ASR 分段与时间轴", src)

if __name__ == "__main__":
    unittest.main()
