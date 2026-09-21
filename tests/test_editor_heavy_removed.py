"""Heavy editor features disabled in focused MAW-bd build."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server-editor" / "serve.py"
SPEC = importlib.util.spec_from_file_location("focused_editor_server", SERVER_PATH)
assert SPEC and SPEC.loader
server_editor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server_editor
SPEC.loader.exec_module(server_editor)


class HeavyFeaturesRemovedTests(unittest.TestCase):
    def test_constant_declares_removal(self) -> None:
        self.assertEqual(server_editor.HEAVY_FEATURES_REMOVED, "editor-heavy-features-removed")

    def test_server_config_has_null_heavy_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_path = root / "p.mosp"
            project_path.write_text(
                json.dumps({"segments": [{"start": 0, "end": 100, "text": "hi"}]}),
                encoding="utf-8",
            )
            project = server_editor.load_project(
                project_path, None, None, no_waveform=True, peaks_per_second=100
            )
            html = server_editor.build_server_page(project)
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="ignore")
            self.assertIn("MaweProofread", html)
            for needle in (
                "/api/exports/lottie",
                "/api/exports/ograf",
                "/api/exports/sticker-otio",
                "/api/ass-styles",
                "/api/stickers/root",
            ):
                # URLs must not be injected as active endpoints
                self.assertNotIn(f'"{needle}"', html)

    def test_template_hides_heavy_panels(self) -> None:
        html = (ROOT / "web" / "editor-template.html").read_text(encoding="utf-8")
        for id_ in ("multi-subtitle-controls", "overlay-track-controls", "ass-style-window", "lottie-export-modal"):
            self.assertIn(f'id="{id_}"', html)
            # force hidden attribute present on those containers
        css = (ROOT / "web" / "editor.css").read_text(encoding="utf-8")
        self.assertIn("focused-build: hide heavy editor features", css)
        self.assertIn("#multi-subtitle-controls", css)

    def test_ass_styles_module_is_stub(self) -> None:
        from maw import ass_styles

        lib = ass_styles.load_ass_style_library()
        self.assertEqual(lib.get("styles"), [])
        self.assertIsNone(ass_styles.find_ass_style({}))
