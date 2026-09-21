"""Phase 6: editor proofread UI contract (template IDs + script presence)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class EditorProofreadUiTests(unittest.TestCase):
    def test_scripts_include_editor_proofread(self) -> None:
        listing = (WEB / "editor-scripts.txt").read_text(encoding="utf-8")
        self.assertIn("editor-proofread.js", listing)
        self.assertLess(listing.index("editor-proofread.js"), listing.index("editor.js"))

    def test_template_has_filter_and_panel_ids(self) -> None:
        html = (WEB / "editor-template.html").read_text(encoding="utf-8")
        for id_ in (
            "proofread-filter-dropdown",
            "proofread-filter-btn",
            "proofread-filter-menu",
            "cue-panel-proofread",
            "cue-panel-proofread-status",
            "cue-panel-proofread-script",
            "cue-panel-proofread-asr",
            "cue-panel-proofread-secondary",
            "cue-panel-proofread-corrected",
            "cue-panel-proofread-reason",
        ):
            self.assertIn(f'id="{id_}"', html)

    def test_editor_js_wires_proofread(self) -> None:
        js = (WEB / "editor.js").read_text(encoding="utf-8")
        self.assertIn("MaweProofread", js)
        self.assertIn("proofreadFilterId", js)
        self.assertIn("markManual", js)
        self.assertIn("renderProofreadPanel", js)
        self.assertIn("filterPass", js)

    def test_editor_js_persists_proofread(self) -> None:
        js = (WEB / "editor.js").read_text(encoding="utf-8")
        self.assertIn("if (s.proofread) o.proofread = s.proofread;", js)
        self.assertIn("proofread_run", js)

    def test_proofread_module_mark_manual_and_filter(self) -> None:
        src = (WEB / "editor-proofread.js").read_text(encoding="utf-8")
        self.assertIn("markManual", src)
        self.assertIn("filterPass", src)
        self.assertIn("verified", src)
        self.assertIn("manual", src)
        # manual 不自动上色
        self.assertIn("manual 不自动上色", src)

    def test_css_has_proofread_styles(self) -> None:
        css = (WEB / "editor.css").read_text(encoding="utf-8")
        self.assertIn("proofread-badge-verified", css)
        self.assertIn("cue-panel-proofread", css)

    def test_fcpxml_dialog_is_bound_and_can_reopen(self) -> None:
        html = (WEB / "editor-template.html").read_text(encoding="utf-8")
        js = (WEB / "editor.js").read_text(encoding="utf-8")
        self.assertIn('id="download-fcpxml"', html)
        self.assertLess(html.index('id="fcpxml-export-modal"'), html.index("__EDITOR_SCRIPTS_JS__"))
        self.assertIn("modal.classList.remove('hidden')", js)
        self.assertIn("if (!saved) return;", js)

    def test_waveform_double_click_opens_anchored_subtitle_edit_popover(self) -> None:
        html = (WEB / "editor-template.html").read_text(encoding="utf-8")
        js = (WEB / "editor.js").read_text(encoding="utf-8")
        css = (WEB / "editor.css").read_text(encoding="utf-8")
        for id_ in (
            "waveform-cue-edit-modal",
            "waveform-cue-edit-text",
            "waveform-cue-edit-cancel",
            "waveform-cue-edit-save",
        ):
            self.assertIn(f'id="{id_}"', html)
        self.assertIn('class="waveform-cue-edit-popover waveform-cue-edit-dialog"', html)
        self.assertIn('aria-modal="false"', html)
        self.assertIn("function openWaveformCueEditDialog(", js)
        self.assertIn("openWaveformCueEditDialog('main', idx, null, anchor)", js)
        self.assertIn("openWaveformCueEditDialog('extension', idx", js)
        self.assertIn("openWaveformCueEditDialog('overlay', idx, null, anchor)", js)
        self.assertIn("positionWaveformCueEditDialog", js)
        self.assertIn("#waveform-cue-edit-modal.show", css)
        self.assertIn("position: fixed", css)

    def test_focused_editor_removes_sticker_and_extra_export_entries(self) -> None:
        html = (WEB / "editor-template.html").read_text(encoding="utf-8")
        js = (WEB / "editor.js").read_text(encoding="utf-8")
        for removed in (
            'id="extra-export-dropdown"',
            'id="extra-export-btn"',
            'id="editor-settings-tab-sticker"',
            'id="editor-settings-tab-easter-eggs"',
            '<kbd>T</kbd> 分配表情包',
        ):
            self.assertNotIn(removed, html)
        self.assertNotIn("addItem('分配表情包…'", js)
        self.assertNotIn("addItem('统一分配表情包…'", js)

    def test_fcpxml_generator_outputs_valid_xml(self) -> None:
        import subprocess
        import xml.etree.ElementTree as ET

        jsc = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
        if not jsc.is_file():
            self.skipTest("JavaScriptCore not available")
        script = (
            "var window={}; "
            "eval(readFile('web/gap-remove-core.js')); "
            "eval(readFile('web/editor-utils.js')); "
            "print(window.AsrEditorUtils.buildFcpxmlFromSegments("
            "[{start:0,end:1500,text:'你好'}],"
            "{fps:'25',resolution:'1920x1080',projectName:'Test'}));"
        )
        result = subprocess.run([str(jsc), "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        root = ET.fromstring(result.stdout)
        self.assertEqual(root.tag, "fcpxml")
        self.assertEqual(root.findtext(".//title/text/text-style"), "你好")
        resources = root.find("resources")
        self.assertIsNotNone(resources)
        self.assertEqual([child.tag for child in resources], ["format", "effect"])
        self.assertIsNone(resources.find("text-style-def"))
        self.assertIsNotNone(root.find(".//title/text-style-def"))

    def test_fcpxml_passes_installed_final_cut_dtd(self) -> None:
        import shutil
        import subprocess
        import tempfile

        jsc = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
        xmllint = Path("/usr/bin/xmllint")
        dtd = Path(
            "/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/"
            "Versions/A/Resources/FCPXMLv1_7.dtd"
        )
        if not (jsc.is_file() and xmllint.is_file() and dtd.is_file()):
            self.skipTest("Final Cut Pro 1.7 DTD validation tools not available")
        script = (
            "var window={}; "
            "eval(readFile('web/gap-remove-core.js')); "
            "eval(readFile('web/editor-utils.js')); "
            "print(window.AsrEditorUtils.buildFcpxmlFromSegments("
            "[{start:0,end:1500,text:'你好'}],"
            "{fps:'25',resolution:'1920x1080',projectName:'Test'}));"
        )
        generated = subprocess.run([str(jsc), "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "test.fcpxml"
            dtd_copy = Path(tmp) / "FCPXMLv1_7.dtd"
            xml_path.write_text(generated.stdout, encoding="utf-8")
            shutil.copyfile(dtd, dtd_copy)
            checked = subprocess.run(
                [str(xmllint), "--noout", "--dtdvalid", str(dtd_copy), str(xml_path)],
                capture_output=True,
                text=True,
            )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_editor_js_syntax_via_node_if_available(self) -> None:
        import os
        import subprocess

        node = os.environ.get("MIMO_NODE") or "node"
        try:
            proc = subprocess.run(
                [node, "--check", str(WEB / "editor.js")],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest("node not available")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc2 = subprocess.run(
            [node, "--check", str(WEB / "editor-proofread.js")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc2.returncode, 0, proc2.stderr)


if __name__ == "__main__":
    unittest.main()
