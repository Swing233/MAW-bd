"""Focused-build packaging contract (macOS/.app + localhost security)."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingContractTests(unittest.TestCase):
    def test_spec_includes_core_payloads(self) -> None:
        spec = (ROOT / "MAW.spec").read_text(encoding="utf-8")
        for needle in (
            'str(ROOT / "web")',
            'str(ROOT / "server-editor")',
            "generate_subtitle_qwen_api.py",
            "maw.bdversion",
            "web",  # srt2fcpxml-page lives under web/
        ):
            self.assertIn(needle, spec)
        # srt2fcpxml page is under web/ so shipped with web datas
        self.assertTrue((ROOT / "web" / "srt2fcpxml-page" / "index.html").is_file())
        self.assertTrue((ROOT / "web" / "editor-proofread.js").is_file())

    def test_spec_excludes_removed_providers(self) -> None:
        spec = (ROOT / "MAW.spec").read_text(encoding="utf-8")
        # Active hiddenimports must not pull removed modules
        banned_hidden = (
            "generate_subtitle_soniox_api",
            "generate_subtitle_tencent_api",
            "generate_subtitle_doubao_api",
            "generate_subtitle_bcut_api",
            "generate_subtitle_openai_api",
            "maw.local_models",
            "maw.postprocess_match",
            "maw.script_alignment",
            "maw.soniox",
        )
        # Parse hiddenimports list from spec text
        self.assertIn("hiddenimports=[", spec)
        start = spec.index("hiddenimports=[")
        end = spec.index("]", start)
        hidden_block = spec[start:end]
        for banned in banned_hidden:
            self.assertNotIn(f'"{banned}"', hidden_block)
            self.assertNotIn(f"'{banned}'", hidden_block)
        # Those modules should appear in excludes when still named
        self.assertIn("excluded_modules", spec)
        self.assertIn('"maw.soniox"', spec)
        self.assertIn('"maw.postprocess_match"', spec)
        # Active ASR + proofread domain
        self.assertIn('"generate_subtitle_qwen_api"', spec)
        self.assertIn('"generate_subtitle_local"', spec)
        self.assertIn('"maw.local_asr"', spec)
        self.assertIn('"maw.bdversion.deepseek"', spec)
        self.assertNotIn("server-align", spec)

    def test_spec_darwin_bundle_identity(self) -> None:
        spec = (ROOT / "MAW.spec").read_text(encoding="utf-8")
        self.assertIn("sys.platform == 'darwin'", spec)
        self.assertIn("MAW-bd.app", spec)
        self.assertIn("maw.icns", spec)
        self.assertIn("com.moy.maw.bdversion", spec)

    def test_serve_binds_loopback_only(self) -> None:
        src = (ROOT / "server-editor" / "serve.py").read_text(encoding="utf-8")
        self.assertIn('open_editor_server(\n            "127.0.0.1"', src.replace("\r\n", "\n"))
        self.assertNotIn('"0.0.0.0"', src)
        # default server host constant if present
        self.assertIn("127.0.0.1", src)

    def test_ffmpeg_resolves_bundled_macos_path(self) -> None:
        src = (ROOT / "maw" / "ffmpeg.py").read_text(encoding="utf-8")
        self.assertIn("ffmpeg", src)
        self.assertIn("ffprobe", src)
        self.assertIn("bundled", src.lower())
        # frozen app layout: executable sibling ffmpeg/bin
        self.assertIn('executable_path.parent / "ffmpeg" / "bin"', src)

    def test_app_paths_macos_user_data(self) -> None:
        src = (ROOT / "maw" / "app_paths.py").read_text(encoding="utf-8")
        self.assertIn("Application Support", src)
        self.assertIn("MAW", src)
        self.assertIn("default_env_path", src)

    def test_gui_config_only_dual_qwen(self) -> None:
        from maw.gui_config import DEFAULT_MODEL_ID, PROVIDERS, QWEN_MODELS, QWEN3_ASR_MODEL_ID, QWEN_AUDIO_MODEL_ID

        self.assertEqual(DEFAULT_MODEL_ID, QWEN_AUDIO_MODEL_ID)
        self.assertEqual([m.id for m in QWEN_MODELS], [QWEN_AUDIO_MODEL_ID, QWEN3_ASR_MODEL_ID])
        self.assertEqual([p.id for p in PROVIDERS], ["qwen"])

    def test_deprecated_python_fcpxml_not_required_by_spec(self) -> None:
        spec = (ROOT / "MAW.spec").read_text(encoding="utf-8")
        # exporters package is optional; webpage is the supported conversion path
        self.assertNotIn("exporters.fcpxml", spec)

    def test_third_party_notice_srt2fcpxml(self) -> None:
        text = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("srt2fcpxml", text)
        self.assertIn("MIT", text)
        self.assertIn("GanymedeNil", text)

    def test_spec_is_valid_python_ast(self) -> None:
        spec = (ROOT / "MAW.spec").read_text(encoding="utf-8")
        # SPECPATH is injected by PyInstaller; stub for parse-only check
        compile(spec.replace("Path(SPECPATH)", "Path('.')"), "MAW.spec", "exec")

    def test_local_segment_does_not_eagerly_import_llm_runtime(self) -> None:
        """The source runtime used by packaged ASR intentionally omits GUI LLM files."""

        script = """
import builtins
real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == 'maw.postprocess_llm':
        raise AssertionError('segmentation eagerly imported the GUI LLM runtime')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
import maw.local_segment
print(maw.local_segment.DEFAULT_MAX_LEN)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().isdigit())

    def test_keychain_documented_as_future(self) -> None:
        doc = ROOT / "docs" / "MACOS_PACKAGING.md"
        if not doc.is_file():
            self.skipTest("MACOS_PACKAGING.md not written yet")
        text = doc.read_text(encoding="utf-8")
        self.assertIn("Keychain", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("ffmpeg", text.lower())


class SecuritySourceTests(unittest.TestCase):
    def test_no_zero_bind_in_editor_server_tree(self) -> None:
        for path in (ROOT / "server-editor").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("0.0.0.0", text, path)

    def test_generated_scripts_qwen_and_local_only(self) -> None:
        generators = list(ROOT.glob("generate_subtitle_*.py"))
        names = {p.name for p in generators}
        self.assertEqual(
            names,
            {"generate_subtitle_qwen_api.py", "generate_subtitle_local.py"},
        )


if __name__ == "__main__":
    unittest.main()
