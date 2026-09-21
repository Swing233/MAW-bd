# -*- mode: python ; coding: utf-8 -*-
# MAW bdversion focused packaging (macOS .app + Windows/Linux via PyInstaller).
# Only dual-Qwen ASR + localhost MAWE + bdversion proofread + local SRT→FCPXML page.

import sys
from pathlib import Path

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules
except ImportError:  # pragma: no cover
    collect_data_files = lambda _package: []
    collect_submodules = lambda _package: []

ROOT = Path(SPECPATH).resolve()

binaries = []
if sys.platform == "linux":
    try:
        import subprocess

        def _ld_so_path(name: str) -> str | None:
            table = subprocess.check_output(["ldconfig", "-p"], text=True, stderr=subprocess.DEVNULL)
            for line in table.splitlines():
                parts = line.split("=>")
                if len(parts) == 2 and name in parts[0]:
                    return parts[1].strip()
            return None

        libxcb_cursor = _ld_so_path("libxcb-cursor.so.0")
        if libxcb_cursor:
            binaries.append((libxcb_cursor, "PyQt6/Qt6/lib"))
            unversioned = Path(libxcb_cursor).with_name("libxcb-cursor.so")
            if not unversioned.exists():
                import shutil
                import tempfile

                tmpdir = tempfile.mkdtemp(prefix="maw-spec-")
                unversioned = Path(tmpdir) / "libxcb-cursor.so"
                shutil.copy2(libxcb_cursor, unversioned)
            binaries.append((str(unversioned), "PyQt6/Qt6/lib"))
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: libxcb-cursor collection failed: {exc}", file=sys.stderr)

# local-runtime payload: Qwen transcription + project IO needed by CLI subprocess
_runtime_maw_files = [
    "__init__.py",
    "app_paths.py",
    "colors.py",
    "console.py",
    "ffmpeg.py",
    "gui_config.py",
    "language.py",
    "local_segment.py",
    "local_asr.py",
    "media.py",
    "project.py",
    "project_io.py",
    "project_preview.py",
    "qwen_audio.py",
    "speaker.py",
    "stickers.py",
    "output_naming.py",
    "waveform.py",
    "quapeaks.py",
    "mopeaks.py",
    "media_cache.py",
]

datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "server-editor"), "server-editor"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "blank-editor.html"), "."),
    (str(ROOT / "assets" / "maw.ico"), "assets"),
    (str(ROOT / "assets" / "maw.icns"), "assets"),
    (str(ROOT / "assets" / "show.webp"), "assets"),
    (str(ROOT / "generate_subtitle_qwen_api.py"), "local-runtime"),
    (str(ROOT / "generate_subtitle_local.py"), "local-runtime"),
    (str(ROOT / "edit.py"), "local-runtime"),
]
for _name in _runtime_maw_files:
    _src = ROOT / "maw" / _name
    if _src.is_file():
        datas.append((str(_src), "local-runtime/maw"))  # dest is directory
for _sub in (ROOT / "maw" / "bdversion").glob("*.py"):
    datas.append((str(_sub), "local-runtime/maw/bdversion"))

# web/ already includes editor-proofread.js, srt2fcpxml-page/, launcher/

opencc_datas = collect_data_files("opencc")
datas.extend(opencc_datas)
opencc_hiddenimports = collect_submodules("opencc")

excluded_modules = [
    "funasr",
    "hf_xet",
    "huggingface_hub",
    "modelscope",
    "qwen_asr",
    "onnxruntime",
    "rapidocr",
    "torch",
    "torchaudio",
    "transformers",
    "moss_transcribe_diarize",
    # removed non-core providers / tools (focused build)
    "maw.soniox",
    "maw.tencent",
    "maw.doubao",
    "maw.bcut",
    "maw.local_asr",
    "maw.local_models",
    "maw.local_runtime",
    "maw.local_runtime_worker",
    "maw.moss_runtime",
    "maw.ocr_runtime",
    "maw.ocr_runtime_worker",
    "maw.postprocess_match",
    "maw.postprocess_ocr",
    "maw.script_alignment",
    "generate_subtitle_soniox_api",
    "generate_subtitle_tencent_api",
    "generate_subtitle_doubao_api",
    "generate_subtitle_bcut_api",
    "generate_subtitle_openai_api",
    "generate_subtitle_local",
]

a = Analysis(
    [str(ROOT / "maw_gui.py")],
    pathex=[str(ROOT), str(ROOT / "server-editor")],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "edit",
        "serve",
        "generate_subtitle_qwen_api",
        "generate_subtitle_local",
        "maw.local_asr",
        "maw.app_paths",
        "maw.cli",
        "maw.colors",
        "maw.console",
        "maw.ffmpeg",
        "maw.gui_config",
        "maw.gui_platform",
        "maw.gui_web",
        "maw.gui_workflow",
        "maw.language",
        "maw.launcher_batch",
        "maw.media",
        "maw.media_cache",
        "maw.mopeaks",
        "maw.notify",
        "maw.output_naming",
        "maw.postprocess",
        "maw.postprocess_ffmpeg",
        "maw.postprocess_io",
        "maw.postprocess_llm",
        "maw.postprocess_pipeline",
        "maw.project",
        "maw.project_backups",
        "maw.project_io",
        "maw.project_preview",
        "maw.pyinstaller_utf8",
        "maw.qwen_audio",
        "maw.quapeaks",
        "maw.speaker",
        "maw.stickers",
        "maw.text_conversion",
        "maw.waveform",
        # focused proofread domain
        "maw.bdversion",
        "maw.bdversion.alignment",
        "maw.bdversion.deepseek",
        "maw.bdversion.dual_asr",
        "maw.bdversion.manuscript",
        "maw.bdversion.metrics",
        "maw.bdversion.normalize",
        "maw.bdversion.project_meta",
        "maw.bdversion.status",
        "opencc",
        *opencc_hiddenimports,
        "quapeaks",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "maw" / "pyinstaller_utf8.py")],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MAW',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'maw.ico') if sys.platform == 'win32' else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MAW',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='MAW-bd.app',
        icon=str(ROOT / 'assets' / 'maw.icns'),
        bundle_identifier='com.moy.maw.bdversion',
        info_plist={
            "CFBundleDisplayName": "MAW-bd",
            "CFBundleName": "MAW-bd",
            "CFBundleShortVersionString": "1.6.0-beta.4",
            "CFBundleVersion": "1.6.0-beta.4",
            "NSHighResolutionCapable": True,
        },
    )
