import types
import unittest
from unittest.mock import Mock, patch

from maw.local_asr import QwenAsrEngine


class QwenPrecisionTests(unittest.TestCase):
    def test_mps_uses_float32_for_asr_and_aligner(self):
        torch = types.SimpleNamespace(float16="fp16", bfloat16="bf16", float32="fp32")
        model = Mock()
        with patch.dict("sys.modules", {"torch": torch, "qwen_asr": types.SimpleNamespace(Qwen3ASRModel=model)}), patch("maw.local_asr.resolve_device", return_value="mps"):
            QwenAsrEngine()._load()
        kwargs = model.from_pretrained.call_args.kwargs
        self.assertEqual(kwargs["dtype"], "fp32")
        self.assertEqual(kwargs["forced_aligner_kwargs"]["dtype"], "fp32")

    def test_cpu_remains_float32_and_mps_load_failure_falls_back(self):
        torch = types.SimpleNamespace(float16="fp16", bfloat16="bf16", float32="fp32", mps=types.SimpleNamespace(empty_cache=lambda: None))
        model = Mock()
        model.from_pretrained.side_effect = [RuntimeError("unsupported"), object()]
        with patch.dict("sys.modules", {"torch": torch, "qwen_asr": types.SimpleNamespace(Qwen3ASRModel=model)}), patch("maw.local_asr.resolve_device", return_value="mps"):
            QwenAsrEngine()._load()
        self.assertEqual(model.from_pretrained.call_args.kwargs["dtype"], "fp32")
        self.assertEqual(model.from_pretrained.call_args.kwargs["device_map"], "cpu")


    def test_empty_mps_auto_result_retries_cpu_without_changing_input(self):
        engine = QwenAsrEngine()
        engine._active_device = "mps"
        empty = types.SimpleNamespace(text="")
        complete = types.SimpleNamespace(text="大家好")
        engine._transcribe_once = Mock(side_effect=[empty, complete])
        events = []
        with patch.dict("sys.modules", {"torch": types.SimpleNamespace(mps=types.SimpleNamespace(empty_cache=lambda: None))}):
            result = engine.transcribe("audio.wav", on_event=events.append)
        self.assertIs(result, complete)
        self.assertEqual(engine._transcribe_once.call_args_list[0], engine._transcribe_once.call_args_list[1])
        self.assertEqual(engine.device, "auto")
        self.assertIn("CPU", events[0])

    def test_nonempty_result_and_explicit_device_are_not_retried(self):
        for device, text in (("auto", "大家好"), ("mps", "")):
            engine = QwenAsrEngine(device=device)
            engine._active_device = "mps"
            engine._transcribe_once = Mock(return_value=types.SimpleNamespace(text=text))
            engine.transcribe("audio.wav")
            engine._transcribe_once.assert_called_once()

    def test_cuda_keeps_float16_for_both_models(self):
        torch = types.SimpleNamespace(float16="fp16", bfloat16="bf16", float32="fp32")
        model = Mock()
        with patch.dict("sys.modules", {"torch": torch, "qwen_asr": types.SimpleNamespace(Qwen3ASRModel=model)}), patch("maw.local_asr.resolve_device", return_value="cuda"):
            QwenAsrEngine()._load()
        kwargs = model.from_pretrained.call_args.kwargs
        self.assertEqual(kwargs["dtype"], "fp16")
        self.assertEqual(kwargs["forced_aligner_kwargs"]["dtype"], "fp16")
