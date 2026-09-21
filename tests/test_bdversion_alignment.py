"""Phase 2 tests: manuscript loading, normalization, monotonic alignment."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from maw.bdversion import (
    align_segments_to_manuscript,
    load_manuscript,
    manuscript_from_paste,
    normalize_for_match,
    should_call_llm,
    status_color_name,
)
from maw.bdversion.alignment import proofread_payload
from maw.bdversion.manuscript import ManuscriptError
from maw.bdversion.status import classify_status


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    body_parts = []
    for para in paragraphs:
        body_parts.append(
            f'<w:p><w:r><w:t xml:space="preserve">{escape(para)}</w:t></w:r></w:p>'
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body_parts)}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr("word/document.xml", document_xml)


class NormalizeTests(unittest.TestCase):
    def test_punct_space_case_fullwidth(self) -> None:
        self.assertEqual(normalize_for_match("Hello，世界！"), normalize_for_match("hello 世界"))
        self.assertEqual(normalize_for_match("１００"), normalize_for_match("100"))
        self.assertEqual(normalize_for_match("１，０００"), normalize_for_match("1000"))

    def test_empty(self) -> None:
        self.assertEqual(normalize_for_match(None), "")
        self.assertEqual(normalize_for_match("  "), "")


class ManuscriptTests(unittest.TestCase):
    def test_txt_and_paste_units(self) -> None:
        doc = manuscript_from_paste("第一句。\n第二句。\n\n第三句。")
        self.assertGreaterEqual(doc.unit_count, 3)
        self.assertIn("第一句", doc.units[0].display_text)

    def test_markdown_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.md"
            path.write_text("# 标题\n\n**加粗**内容与[链接](https://x)\n", encoding="utf-8")
            doc = load_manuscript(path)
            self.assertNotIn("**", doc.display_text)
            self.assertIn("加粗内容", doc.display_text)

    def test_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.docx"
            _write_docx(path, ["大家好", "今天介绍工作流"])
            doc = load_manuscript(path)
            self.assertEqual(doc.source.origin, "docx")
            self.assertEqual(doc.unit_count, 2)

    def test_pdf_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.pdf"
            path.write_bytes(b"%PDF-1.4")
            with self.assertRaises(ManuscriptError):
                load_manuscript(path)

    def test_empty_rejected(self) -> None:
        with self.assertRaises(ManuscriptError):
            manuscript_from_paste("！！！")


class AlignmentTests(unittest.TestCase):
    def test_exact_match_verified(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "大家好"}]
        doc = manuscript_from_paste("大家好")
        result = align_segments_to_manuscript(segments, doc)
        cue = result.cues[0]
        self.assertTrue(cue.matched)
        self.assertEqual(cue.status, "verified")
        self.assertEqual(cue.script_text, "大家好")
        self.assertFalse(should_call_llm(cue.status, cue.match_score))
        self.assertEqual(status_color_name("verified"), "green")

    def test_homophone_high_score_uncertain_for_llm(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "今天介绍自工作流"}]
        doc = manuscript_from_paste("今天介绍字幕工作流")
        result = align_segments_to_manuscript(segments, doc)
        cue = result.cues[0]
        self.assertTrue(cue.matched)
        self.assertEqual(cue.status, "uncertain")
        self.assertGreaterEqual(cue.match_score, 0.7)
        self.assertTrue(should_call_llm(cue.status, cue.match_score))

    def test_person_name_error_still_matched(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 800, "text": "张三讲了流程"}]
        doc = manuscript_from_paste("章三讲了流程")
        result = align_segments_to_manuscript(segments, doc)
        cue = result.cues[0]
        self.assertTrue(cue.matched)
        self.assertNotEqual(cue.status, "improvised")

    def test_script_line_not_spoken_stays_unmatched_script(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "第一句内容"},
            {"id": "main-002", "start": 1000, "end": 2000, "text": "第三句内容"},
        ]
        doc = manuscript_from_paste("第一句内容\n这句文稿里有但没讲\n第三句内容")
        result = align_segments_to_manuscript(segments, doc)
        self.assertEqual(result.cues[0].status, "verified")
        self.assertEqual(result.cues[1].status, "verified")
        # middle manuscript unit should remain unmatched
        self.assertTrue(result.unmatched_script_units)

    def test_improvised_extra_sentence_kept_not_script(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "按文稿讲的一句"},
            {"id": "main-002", "start": 1000, "end": 2000, "text": "现场即兴又说了一句完全不同的话"},
        ]
        doc = manuscript_from_paste("按文稿讲的一句")
        result = align_segments_to_manuscript(segments, doc)
        self.assertEqual(result.cues[0].status, "verified")
        self.assertEqual(result.cues[1].status, "improvised")
        self.assertIsNone(result.cues[1].script_text)
        payload = proofread_payload(result.cues[1])
        self.assertIsNone(payload["corrected"])
        self.assertEqual(payload["asr_original"], "现场即兴又说了一句完全不同的话")

    def test_rephrase_not_rewritten_to_script(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "我们先把工程打开再导出"}]
        doc = manuscript_from_paste("请打开工程文件然后导出字幕")
        result = align_segments_to_manuscript(segments, doc)
        cue = result.cues[0]
        # may or may not match; never verified-equal to script rewrite
        if cue.matched:
            self.assertNotEqual(cue.status, "verified")
        self.assertEqual(cue.asr_text, "我们先把工程打开再导出")
        payload = proofread_payload(cue)
        self.assertEqual(payload["asr_original"], cue.asr_text)

    def test_cross_cue_script_match_monotonic(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 1000, "text": "今天"},
            {"id": "main-002", "start": 1000, "end": 2000, "text": "介绍工作流"},
        ]
        doc = manuscript_from_paste("今天介绍工作流")
        result = align_segments_to_manuscript(segments, doc, max_span=2)
        self.assertTrue(result.cues[0].matched)
        self.assertTrue(result.cues[1].matched)
        # second cue must not consume manuscript key before first cue ends
        r0 = result.cues[0].match_range
        r1 = result.cues[1].match_range
        assert r0 is not None and r1 is not None
        self.assertGreaterEqual(r1["key_start"], r0["key_end"])
        self.assertEqual(result.cues[0].script_text, "今天介绍工作流")
        self.assertEqual(result.cues[1].script_text, "今天介绍工作流")

    def test_mixed_language(self) -> None:
        segments = [{"id": "main-001", "start": 0, "end": 1000, "text": "MAW 工作流 Workflow"}]
        doc = manuscript_from_paste("MAW 工作流 Workflow")
        result = align_segments_to_manuscript(segments, doc)
        self.assertEqual(result.cues[0].status, "verified")

    def test_no_backward_cursor_with_skipped_improvised(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 500, "text": "开场白"},
            {"id": "main-002", "start": 500, "end": 900, "text": "完全无关的即兴内容"},
            {"id": "main-003", "start": 900, "end": 1500, "text": "第二句文稿"},
        ]
        doc = manuscript_from_paste("开场白\n第二句文稿")
        result = align_segments_to_manuscript(segments, doc)
        self.assertEqual(result.cues[0].status, "verified")
        self.assertEqual(result.cues[1].status, "improvised")
        self.assertEqual(result.cues[2].status, "verified")
        assert result.cues[0].match_range is not None
        assert result.cues[2].match_range is not None
        self.assertGreater(
            result.cues[2].match_range["unit_start"],
            result.cues[0].match_range["unit_start"],
        )

    def test_disabled_segments_skipped(self) -> None:
        segments = [
            {"id": "main-001", "start": 0, "end": 500, "text": "保留句", "disabled": True},
            {"id": "main-002", "start": 500, "end": 1000, "text": "保留句"},
        ]
        doc = manuscript_from_paste("保留句")
        result = align_segments_to_manuscript(segments, doc)
        self.assertFalse(result.cues[0].matched)
        self.assertEqual(result.cues[1].status, "verified")

    def test_classify_and_color_map(self) -> None:
        self.assertEqual(classify_status(asr_key="abc", script_key="abc", match_score=1.0, matched=True), "verified")
        self.assertEqual(classify_status(asr_key="abc", script_key=None, match_score=0.2, matched=False), "improvised")
        self.assertEqual(classify_status(asr_key="abcd", script_key="abxd", match_score=0.9, matched=True), "uncertain")
        self.assertEqual(status_color_name("improvised"), "yellow")
        self.assertEqual(status_color_name("uncertain"), "red")
        self.assertIsNone(status_color_name("manual"))
        self.assertFalse(should_call_llm("improvised", 0.99))
        self.assertFalse(should_call_llm("verified", 1.0))


if __name__ == "__main__":
    unittest.main()
