"""Phase 3: proofread metadata persistence + color mapping + legacy compatibility."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
import tempfile

from maw.bdversion import (
    align_segments_to_manuscript,
    mark_manual_edit,
    manuscript_from_paste,
    project_with_alignment,
    status_color_name,
)
from maw.bdversion.project_meta import (
    apply_status_color,
    color_snapshot_for_status,
    normalize_proofread,
)
from maw.colors import COLOR_PALETTE
from maw.project import ProjectValidationFailed, normalize_project
from maw.project_io import serialize_mosp, write_mosp
from maw.postprocess_io import read_project


class ProofreadSchemaTests(unittest.TestCase):
    def test_legacy_mosp_without_proofread_still_opens(self) -> None:
        project = {
            "media": "clip.mp4",
            "segments": [
                {"start": 0, "end": 1000, "text": "大家好"},
                {"start": 1000, "end": 2000, "text": "今天介绍工作流"},
            ],
        }
        normalized = normalize_project(project)
        self.assertEqual(len(normalized["segments"]), 2)
        self.assertNotIn("proofread", normalized["segments"][0])
        text = serialize_mosp(normalized)
        data = json.loads(text)
        self.assertEqual(data["segments"][0]["text"], "大家好")
        self.assertNotIn("proofread", data["segments"][0])

    def test_normalize_accepts_valid_proofread(self) -> None:
        project = {
            "segments": [
                {
                    "start": 0,
                    "end": 1000,
                    "text": "大家好",
                    "proofread": {
                        "status": "verified",
                        "match_score": 1.0,
                        "script_text": "大家好",
                        "asr_original": "大家好",
                        "corrected": None,
                        "reason": None,
                    },
                }
            ]
        }
        normalized = normalize_project(project)
        self.assertEqual(normalized["segments"][0]["proofread"]["status"], "verified")

    def test_normalize_rejects_bad_status(self) -> None:
        project = {
            "segments": [
                {
                    "start": 0,
                    "end": 100,
                    "text": "x",
                    "proofread": {"status": "bogus"},
                }
            ]
        }
        with self.assertRaises(ProjectValidationFailed):
            normalize_project(project)

    def test_normalize_rejects_out_of_range_score(self) -> None:
        project = {
            "segments": [
                {
                    "start": 0,
                    "end": 100,
                    "text": "x",
                    "proofread": {"status": "verified", "match_score": 1.5},
                }
            ]
        }
        with self.assertRaises(ProjectValidationFailed):
            normalize_project(project)

    def test_normalize_proofread_helper(self) -> None:
        cleaned = normalize_proofread(
            {
                "status": "uncertain",
                "match_score": 0.8,
                "script_text": "文稿",
                "asr_original": "ASR",
            }
        )
        assert cleaned is not None
        self.assertEqual(cleaned["status"], "uncertain")
        self.assertEqual(cleaned["match_score"], 0.8)
        self.assertIsNone(cleaned["corrected"])


class ColorMappingTests(unittest.TestCase):
    def test_status_colors_use_existing_palette(self) -> None:
        palette = dict(COLOR_PALETTE)
        self.assertEqual(status_color_name("verified"), "green")
        self.assertEqual(status_color_name("improvised"), "yellow")
        self.assertEqual(status_color_name("uncertain"), "red")
        self.assertIsNone(status_color_name("manual"))
        self.assertEqual(color_snapshot_for_status("verified")["value"], palette["green"])
        self.assertEqual(color_snapshot_for_status("improvised")["value"], palette["yellow"])
        self.assertEqual(color_snapshot_for_status("uncertain")["value"], palette["red"])
        self.assertIsNone(color_snapshot_for_status("manual"))

    def test_apply_status_color_writes_color_head(self) -> None:
        segment = {
            "start": 0,
            "end": 500,
            "text": "大家好",
            "proofread": {"status": "verified", "match_score": 1.0},
        }
        self.assertTrue(apply_status_color(segment))
        self.assertEqual(segment["color"]["name"], "green")
        self.assertEqual(segment["color"]["start"], 0)
        self.assertEqual(segment["color"]["end"], 500)
        self.assertIsNone(segment["color_ref"])

    def test_manual_edit_sets_status_and_clears_auto_color(self) -> None:
        segment = {
            "start": 0,
            "end": 500,
            "text": "改过的字幕",
            "proofread": {"status": "verified", "asr_original": "原ASR", "match_score": 1.0},
            "color": {"name": "green", "value": "#66bb6a", "start": 0, "end": 500},
        }
        mark_manual_edit(segment)
        self.assertEqual(segment["proofread"]["status"], "manual")
        self.assertEqual(segment["proofread"]["asr_original"], "原ASR")
        self.assertEqual(segment["proofread"]["corrected"], "改过的字幕")
        self.assertIsNone(segment["color"])


class AlignmentProjectRoundtripTests(unittest.TestCase):
    def test_project_with_alignment_preserves_time_and_text(self) -> None:
        project = {
            "media": "clip.mp4",
            "segments": [
                {"id": "main-001", "start": 0, "end": 1000, "text": "大家好"},
                {"id": "main-002", "start": 1000, "end": 2000, "text": "现场即兴一句话"},
            ],
        }
        doc = manuscript_from_paste("大家好")
        alignment = align_segments_to_manumscript_safe(project, doc)
        out = project_with_alignment(
            project,
            alignment,
            manuscript_meta={"origin": "paste", "unit_count": doc.unit_count},
        )
        self.assertEqual(out["segments"][0]["text"], "大家好")
        self.assertEqual(out["segments"][0]["start"], 0)
        self.assertEqual(out["segments"][0]["end"], 1000)
        self.assertEqual(out["segments"][0]["proofread"]["status"], "verified")
        self.assertEqual(out["segments"][0]["color"]["name"], "green")
        self.assertEqual(out["segments"][1]["proofread"]["status"], "improvised")
        self.assertEqual(out["segments"][1]["color"]["name"], "yellow")
        self.assertEqual(out["segments"][1]["text"], "现场即兴一句话")
        self.assertIsNone(out["segments"][1]["proofread"]["corrected"])
        self.assertIn("proofread_run", out)
        self.assertEqual(out["proofread_run"]["schema"], "moy.asr.proofread.v1")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.mosp"
            write_mosp(path, out)
            reloaded = read_project(path)
            self.assertEqual(reloaded["segments"][0]["proofread"]["status"], "verified")
            self.assertEqual(reloaded["segments"][1]["proofread"]["asr_original"], "现场即兴一句话")
            self.assertEqual(reloaded["segments"][0]["start"], 0)

    def test_manual_status_not_overwritten_on_realign(self) -> None:
        from maw.bdversion.project_meta import attach_alignment_to_segments

        project_segments = [
            {
                "id": "main-001",
                "start": 0,
                "end": 1000,
                "text": "人工改过",
                "proofread": {"status": "manual", "asr_original": "原ASR"},
            }
        ]
        doc = manuscript_from_paste("完全不同的文稿")
        alignment = align_segments_to_manumscript_safe(
            {"segments": project_segments}, doc
        )
        updated = attach_alignment_to_segments(project_segments, alignment)
        self.assertEqual(updated[0]["proofread"]["status"], "manual")


def align_segments_to_manumscript_safe(project, doc):

    return align_segments_to_manuscript(project["segments"], doc)


if __name__ == "__main__":
    unittest.main()
