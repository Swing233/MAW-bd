import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from maw.focus_launcher import FocusedLauncherApi


class ModelDownloadTests(unittest.TestCase):
    def test_invalid_engine_and_missing_runtime_do_not_start(self):
        api = FocusedLauncherApi()
        self.assertFalse(api.download_local_model({"localEngine": "unknown"})["ok"])
        with patch("maw.focus_launcher.local_runtime_python", return_value=Path("/nonexistent/runtime")):
            self.assertIn("运行时", api.download_local_model({})["error"])
        self.assertIsNone(api.worker)

    def test_busy_task_cannot_start_second_download(self):
        api = FocusedLauncherApi()
        api.worker = Mock()
        api.worker.is_alive.return_value = True
        self.assertFalse(api.download_local_model({})["ok"])

    def test_background_download_uses_selected_engine_and_asr_cache(self):
        for engine in ("qwen-asr", "funasr", "whisper"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as temp:
                runtime = Path(temp) / "python"
                runtime.touch()
                api = FocusedLauncherApi()
                process = Mock()
                process.stdout = io.StringIO("模型准备完成\n")
                process.poll.return_value = 0
                process.returncode = 0
                with (patch("maw.focus_launcher.local_runtime_python", return_value=runtime),
                      patch("maw.focus_launcher.local_model_cache_root", return_value=Path(temp) / "cache"),
                      patch("maw.focus_launcher.subprocess.Popen", return_value=process) as popen,
                      patch.object(api.pump, "start")):
                    result = api.download_local_model({"localEngine": engine})
                    self.assertTrue(result["started"])
                    api.worker.join(timeout=3)
                self.assertFalse(api.worker.is_alive())
                self.assertEqual(api._model_preparation, {"engine": engine, "state": "ready"})
                args, kwargs = popen.call_args
                self.assertEqual(args[0][-1], engine)
                self.assertIn("create_local_engine", args[0][-2])
                self.assertEqual(kwargs["env"]["HF_HUB_CACHE"], str(Path(temp) / "cache/huggingface/hub"))
                self.assertEqual(kwargs["env"]["MODELSCOPE_CACHE"], str(Path(temp) / "cache/modelscope"))
                self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
                self.assertEqual(api._status["step"], "model_download_done")
                self.assertFalse(api._status["busy"])

    def test_download_error_is_reported_without_exposing_keys(self):
        api = FocusedLauncherApi()
        process = Mock()
        process.stdout = io.StringIO("DASHSCOPE_API_KEY=sk-test-secret-value\n")
        process.poll.return_value = 1
        process.returncode = 1
        with patch("maw.focus_launcher.subprocess.Popen", return_value=process):
            api._download_model_worker("qwen-asr")
        self.assertEqual(api._model_preparation["state"], "error")
        self.assertNotIn("sk-test-secret-value", api._status["error"])
        self.assertFalse(api._status["busy"])

    def test_cancel_terminates_silent_download_and_keeps_cache(self):
        api = FocusedLauncherApi()
        process = Mock()
        process.stdout = io.StringIO("")
        process.poll.side_effect = [None, 0]
        api.cancel_event.set()
        with patch("maw.focus_launcher.subprocess.Popen", return_value=process):
            api._download_model_worker("whisper")
        process.terminate.assert_called_once()
        self.assertEqual(api._model_preparation["state"], "cancelled")
        self.assertFalse(api._status["busy"])
        self.assertIn("缓存会保留", api._status["message"])
