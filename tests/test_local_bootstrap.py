import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from maw.local_bootstrap import ensure_runtime, bootstrap_uv, runtime_ready
from maw.gui_workflow import TranscriptionCancelledError


class BootstrapTests(unittest.TestCase):
    def fixture(self, root):
        res = root / "resources"
        res.mkdir()
        (res / "requirements-local.txt").write_text("fake==1.0 --hash=sha256:fixture")
        return res, root / "data/local-runtime/bin/python"

    def test_fresh_install_needs_no_system_python_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            res, python = self.fixture(root)
            commands = []
            def run(command, env, cancel, emit):
                commands.append((command, env))
                if "venv" in command:
                    python.parent.mkdir(parents=True)
                    python.touch()
            with (patch("maw.local_bootstrap.resources", return_value=res),
                  patch("maw.local_bootstrap.runtime_python", return_value=python),
                  patch("maw.local_bootstrap.data_root", return_value=root / "data"),
                  patch("maw.local_bootstrap.bootstrap_uv", return_value=root / "bundled/uv")):
                self.assertEqual(ensure_runtime("whisper", threading.Event(), lambda _: None, runner=run), python)
                self.assertTrue(runtime_ready())
            self.assertEqual(len(commands), 3)
            self.assertIn("--managed-python", commands[0][0])
            self.assertIn("--require-hashes", commands[1][0])
            self.assertNotIn("PYTHONPATH", commands[0][1])
            self.assertTrue(str(root / "data") in commands[0][1]["UV_PYTHON_INSTALL_DIR"])

    def test_ready_environment_reused_but_missing_package_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            res, python = self.fixture(root)
            python.parent.mkdir(parents=True)
            python.touch()
            marker = python.parent.parent / "ready.json"
            marker.write_text(json.dumps({"requirementsSha256": hashlib.sha256((res / "requirements-local.txt").read_bytes()).hexdigest()}))
            for broken in (False, True):
                calls = []
                def run(command, *_):
                    calls.append(command)
                    if broken and len(calls) == 1:
                        raise RuntimeError("missing package")
                with (patch("maw.local_bootstrap.resources", return_value=res),
                      patch("maw.local_bootstrap.runtime_python", return_value=python),
                      patch("maw.local_bootstrap.data_root", return_value=root / "data"),
                      patch("maw.local_bootstrap.bootstrap_uv", return_value=root / "uv")):
                    ensure_runtime("qwen-asr", threading.Event(), lambda _: None, runner=run)
                self.assertEqual(len(calls), 3 if broken else 1)
                self.assertIn("qwen_asr", calls[-1][-1])

    def test_failed_install_or_cancel_never_marks_ready(self):
        for cancelled in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                res, python = self.fixture(root)
                cancel = threading.Event()
                def run(*_):
                    if cancelled:
                        cancel.set()
                        raise TranscriptionCancelledError()
                    raise RuntimeError("network failure")
                with (patch("maw.local_bootstrap.resources", return_value=res),
                      patch("maw.local_bootstrap.runtime_python", return_value=python),
                      patch("maw.local_bootstrap.data_root", return_value=root / "data"),
                      patch("maw.local_bootstrap.bootstrap_uv", return_value=root / "uv")):
                    with self.assertRaises(TranscriptionCancelledError if cancelled else RuntimeError):
                        ensure_runtime("whisper", cancel, lambda _: None, runner=run)
                self.assertFalse((python.parent.parent / "ready.json").exists())

    def test_frozen_app_requires_its_own_installer(self):
        with tempfile.TemporaryDirectory() as temp, patch("maw.local_bootstrap.sys.frozen", True, create=True), patch("maw.local_bootstrap.resources", return_value=Path(temp)):
            with self.assertRaisesRegex(RuntimeError, "内置"):
                bootstrap_uv()
            uv = Path(temp) / "uv"
            uv.touch()
            uv.chmod(0o755)
            self.assertEqual(bootstrap_uv(), uv)
