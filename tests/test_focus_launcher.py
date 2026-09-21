"""Focused Launcher GUI contract + revise + local ASR wiring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maw.bdversion.revise import manuscript_document, revise_project
from maw.focus_launcher import FocusedLauncherApi, local_runtime_python


class FocusedGuiContractTests(unittest.TestCase):
    def test_editor_opens_blank_before_asr(self) -> None:
        api = FocusedLauncherApi()
        with (
            patch.object(api, "_port_free", return_value=True),
            patch.object(api, "_wait_http_ready", return_value=True),
            patch("maw.focus_launcher.subprocess.Popen") as popen,
            patch("webbrowser.open") as browser_open,
        ):
            popen.return_value.poll.return_value = None
            result = api.open_editor({})
            reopened = api.open_editor({})
        self.assertTrue(result["ok"])
        self.assertTrue(result["blank"])
        command = popen.call_args.args[0]
        self.assertIn("--blank", command)
        self.assertNotIn("-m", command)
        self.assertNotIn("--no-waveform", command)
        self.assertEqual(reopened["url"], result["url"])
        popen.assert_called_once()
        self.assertEqual(browser_open.call_count, 2)
        self.assertEqual(api._step_progress["asr"], 0)
        self.assertEqual(api._step_progress["revise"], 0)

    def test_imported_project_uses_its_media_for_waveform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "clip.mosp"
            project.write_text(json.dumps({"media": "clip.wav", "segments": []}), encoding="utf-8")
            api = FocusedLauncherApi()
            with (
                patch.object(api, "_port_free", return_value=True),
                patch.object(api, "_wait_http_ready", return_value=True),
                patch("maw.focus_launcher.subprocess.Popen") as popen,
                patch("webbrowser.open"),
            ):
                popen.return_value.poll.return_value = None
                result = api.open_editor({"projectPath": str(project)})
            self.assertTrue(result["ok"])
            command = popen.call_args.args[0]
            self.assertIn(str(project), command)
            self.assertNotIn("--no-waveform", command)
            self.assertNotIn("-m", command)

    def test_media_editor_creates_project_and_imports_same_name_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "clip.mp4"
            media.write_bytes(b"media")
            srt = media.with_suffix(".srt")
            srt.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n现成字幕\n",
                encoding="utf-8",
            )
            api = FocusedLauncherApi()
            with patch.object(api, "open_editor", return_value={"ok": True, "url": "http://127.0.0.1:8250"}) as open_editor:
                result = api.open_media_editor({"mediaPath": str(media)})

            self.assertTrue(result["ok"])
            self.assertTrue(result["importedSrt"])
            project_path = Path(result["projectPath"])
            self.assertEqual(project_path.name, "clip.maw-edit.mosp")
            project = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual(project["media"], str(media.resolve()))
            self.assertEqual(project["segments"][0]["text"], "现成字幕")
            open_editor.assert_called_once_with({"projectPath": str(project_path)})

    def test_launcher_log_stays_on_right_and_can_collapse(self) -> None:
        html = Path("web/launcher/index.html").read_text(encoding="utf-8")
        css = Path("web/launcher/launcher.css").read_text(encoding="utf-8")
        js = Path("web/launcher/launcher.js").read_text(encoding="utf-8")
        gui = Path("maw/gui_web.py").read_text(encoding="utf-8")

        self.assertIn('class="log-rail" id="log-rail"', html)
        self.assertIn('id="btn-toggle-log"', html)
        self.assertIn('id="btn-show-log"', html)
        self.assertIn('grid-template-columns: minmax(0, 1fr) clamp(240px, 28vw, 340px)', css)
        self.assertNotIn('grid-template-columns: 1fr;', css)
        self.assertIn('.page.log-collapsed .log-rail {\n  display: none;', css)
        self.assertIn("setLogCollapsed(true)", js)
        self.assertIn("setLogCollapsed(false)", js)
        self.assertIn("focusLlmDelta", js)
        self.assertIn("LLM 输出", js)
        self.assertIn('width=1120,', gui)
        self.assertIn('min_size=(800, 640),', gui)

    def test_launcher_does_not_report_pywebview_before_bridge_is_ready(self) -> None:
        js = Path("web/launcher/launcher.js").read_text(encoding="utf-8")

        self.assertNotIn("请通过 MAW-bd 应用启动本界面", js)
        self.assertIn("if (controlsBound) return", js)

    def test_launcher_logs_media_selection_from_backend_event_only(self) -> None:
        js = Path("web/launcher/launcher.js").read_text(encoding="utf-8")
        choose_start = js.index("async function chooseMedia()")
        choose_end = js.index("function mediaFromInput()", choose_start)
        choose_media = js[choose_start:choose_end]

        self.assertNotIn("setMsg('已选择媒体')", choose_media)
        self.assertIn("{ log: false }", js)

    def test_direct_media_editor_forwards_an_explicit_selected_path(self) -> None:
        js = Path("web/launcher/launcher.js").read_text(encoding="utf-8")
        start = js.index("async function openMediaEditor()")
        end = js.index("async function openEditor()", start)
        direct_editor = js[start:end]

        self.assertIn("await a.browse_media({})", direct_editor)
        self.assertIn("await a.open_media_editor({ mediaPath })", direct_editor)
        self.assertIn("正在创建字幕编辑工程并准备波形", direct_editor)
        self.assertIn("catch (error)", direct_editor)

    def test_launcher_has_local_asr_and_manuscript(self) -> None:
        html = Path("web/launcher/index.html").read_text(encoding="utf-8")
        for needle in (
            "本地模型（默认）",
            "添加文稿",
            "btn-manuscript",
            "asr-mode",
            "local-engine",
            "DeepSeek 保守校对",
            "打开字幕编辑器",
            "MP4 + SRT 直接编辑",
            "btn-media-editor",
        ):
            self.assertIn(needle, html)

    def test_run_app_uses_focused_api(self) -> None:
        src = Path("maw/gui_web.py").read_text(encoding="utf-8")
        self.assertIn("FocusedLauncherApi", src)

    def test_api_get_state_local_first(self) -> None:
        api = FocusedLauncherApi()
        state = api.get_state({})
        self.assertTrue(state["ok"])
        modes = state["config"]["asrModes"]
        self.assertEqual(modes[0]["id"], "local")
        self.assertTrue(hasattr(api, "set_manuscript_text"))
        self.assertTrue(hasattr(api, "build_gpt_srt_prompt"))
        self.assertTrue(hasattr(api, "open_editor"))
        self.assertIn("localRuntimeReady", state["config"])

    def test_local_runtime_python_path(self) -> None:
        p = local_runtime_python()
        self.assertTrue(str(p).endswith("local-runtime/bin/python"))

    def test_revise_deepseek_with_manuscript_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "clip.mosp"
            project.write_text(
                json.dumps(
                    {
                        "segments": [
                            {"id": "main-001", "start": 0, "end": 1000, "text": "欢迎来到字幕工作流"},
                            {"id": "main-002", "start": 1000, "end": 2000, "text": "现场多说一句"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            script = Path(tmp) / "script.txt"
            script.write_text("欢迎来到字幕工作流\n文稿里另一句没讲\n", encoding="utf-8")
            seen = {}

            def fake(settings, system_prompt, payload):
                seen["prompt"] = system_prompt
                seen["payload"] = payload
                return {
                    "results": [
                        {
                            "id": p["cue_id"],
                            "corrected_text": p["primary_asr"],
                            "status": "verified",
                            "changed": False,
                            "reason": "keep ASR",
                        }
                        for p in payload
                    ]
                }

            out = revise_project(
                project,
                mode="deepseek",
                api_key="k",
                manuscript=str(script),
                complete=fake,
                on_llm_delta=lambda kind, text: seen.setdefault("deltas", []).append((kind, text)),
            )
            self.assertTrue(out["ok"])
            self.assertTrue(out.get("manuscriptUsed"))
            self.assertIn("matched_script", seen["prompt"])
            self.assertIn("不得把现场发挥改写成文稿", seen["prompt"])
            # first cue should carry manuscript reference
            self.assertEqual(seen["payload"][0]["primary_asr"], "欢迎来到字幕工作流")
            self.assertTrue(seen["payload"][0].get("matched_script"))
            revised = json.loads(Path(out["projectPath"]).read_text(encoding="utf-8"))
            self.assertEqual([(s["start"], s["end"]) for s in revised["segments"]], [(0, 1000), (1000, 2000)])
            self.assertEqual(len(revised["segments"]), 2)
            self.assertEqual([kind for kind, _ in seen["deltas"]], ["start", "done"])

    def test_gpt_prompt_requests_downloadable_srt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / "采访.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n大家好\n", encoding="utf-8")
            api = FocusedLauncherApi()
            api._result["srtPath"] = str(srt)
            result = api.build_gpt_srt_prompt({})
            self.assertTrue(result["ok"])
            self.assertIn("采访.校对.srt", result["prompt"])
            self.assertIn("UTF-8 .srt 文件供下载", result["prompt"])
            self.assertIn("保持序号、条数、分段边界与时间码完全不变", result["prompt"])

    def test_revise_custom_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "a.mosp"
            project.write_text(
                json.dumps({"segments": [{"id": "m", "start": 0, "end": 500, "text": "原ASR"}]}),
                encoding="utf-8",
            )

            def fake(settings, system_prompt, cues):
                return {"groups": [{"source_ids": ["c0001"], "text": "修订后"}]}

            out = revise_project(project, mode="custom", api_key="k", custom_prompt="改错字", complete=fake)
            self.assertTrue(out["ok"])
            revised = json.loads(Path(out["projectPath"]).read_text(encoding="utf-8"))
            self.assertEqual(revised["segments"][0]["text"], "修订后")
            self.assertEqual(revised["segments"][0]["start"], 0)

    def test_custom_revise_cannot_merge_subtitle_cues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "merge.mosp"
            original = [
                {"id": "a", "start": 0, "end": 500, "text": "第一条"},
                {"id": "b", "start": 500, "end": 1000, "text": "第二条"},
            ]
            project.write_text(json.dumps({"segments": original}, ensure_ascii=False), encoding="utf-8")

            def fake(settings, system_prompt, cues):
                return {"groups": [{"source_ids": ["c0001", "c0002"], "text": "模型试图合并"}]}

            out = revise_project(project, mode="custom", api_key="k", custom_prompt="改错字", complete=fake)
            revised = json.loads(Path(out["projectPath"]).read_text(encoding="utf-8"))
            self.assertEqual([(s["start"], s["end"], s["text"]) for s in revised["segments"]], [
                (0, 500, "第一条"), (500, 1000, "第二条")
            ])

    def test_manuscript_loader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "s.md"
            p.write_text("# 标题\n**加粗**内容\n", encoding="utf-8")
            doc = manuscript_document(p)
            self.assertIsNotNone(doc)
            self.assertIn("加粗", doc.display_text)


if __name__ == "__main__":
    unittest.main()
