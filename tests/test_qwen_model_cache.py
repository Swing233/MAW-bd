import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import types
from maw.local_asr import _complete_qwen_snapshot, _qwen_model_location, QwenAsrEngine


def fixture(cache, model="Qwen/Qwen3-ASR-1.7B", sharded=False):
    repo=Path(cache)/("models--"+model.replace("/","--"));(repo/"refs").mkdir(parents=True)
    (repo/"refs"/"main").write_text("revision")
    p=repo/"snapshots"/"revision";p.mkdir(parents=True)
    for name in ["config.json","preprocessor_config.json","tokenizer_config.json"]:(p/name).write_text("{}")
    for name in ["vocab.json","merges.txt"]:(p/name).write_text("data")
    if sharded:
        (p/"model.safetensors.index.json").write_text(json.dumps({"weight_map":{"one":"one.safetensors","two":"two.safetensors"}}))
        for name in ["one.safetensors","two.safetensors"]:(p/name).write_bytes(b"weights")
    else:(p/"model.safetensors").write_bytes(b"weights")
    return p

class QwenCacheTests(unittest.TestCase):
    def test_complete_cache_never_contacts_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{"HF_HUB_CACHE":tmp},clear=True):
            p=fixture(tmp,sharded=True)
            download=Mock()
            with patch.dict("sys.modules", {"huggingface_hub":types.SimpleNamespace(snapshot_download=download)}):
                self.assertEqual(_qwen_model_location("Qwen/Qwen3-ASR-1.7B"),str(p))
            download.assert_not_called()

    def test_partial_and_broken_shards_are_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=fixture(tmp,sharded=True);self.assertTrue(_complete_qwen_snapshot(p))
            (p/"two.safetensors").unlink();self.assertFalse(_complete_qwen_snapshot(p))
            (p/"two.safetensors").write_bytes(b"");self.assertFalse(_complete_qwen_snapshot(p))
            (p/"config.json").write_text("invalid");self.assertFalse(_complete_qwen_snapshot(p))

    def test_download_falls_back_and_does_not_send_token(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"HF_HUB_CACHE":tmp},clear=True):
            p=fixture(tmp)
            download=Mock(side_effect=[OSError("timeout"),str(p)])
            with patch.dict("sys.modules", {"huggingface_hub":types.SimpleNamespace(snapshot_download=download)}):
                (p.parent.parent/"refs"/"main").unlink()
                self.assertEqual(_qwen_model_location("Qwen/Qwen3-ASR-1.7B"),str(p))
            self.assertEqual([c.kwargs["endpoint"] for c in download.call_args_list],["https://hf-mirror.com","https://huggingface.co"])
            self.assertTrue(all(c.kwargs["token"] is False for c in download.call_args_list))

    def test_explicit_endpoint_and_path_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"HF_HUB_CACHE":tmp,"HF_ENDPOINT":"https://example.invalid"},clear=True):
            self.assertEqual(_qwen_model_location(tmp),tmp)
            download=Mock(side_effect=OSError("offline"))
            with patch.dict("sys.modules", {"huggingface_hub":types.SimpleNamespace(snapshot_download=download)}):
                with self.assertRaisesRegex(RuntimeError,"模型下载失败"):_qwen_model_location("Qwen/model")
            self.assertEqual(download.call_count,1)
            self.assertEqual(download.call_args.kwargs["endpoint"],"https://example.invalid")

    def test_asr_and_aligner_both_pass_local_paths(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"HF_HUB_CACHE":tmp},clear=True):
            p=fixture(tmp);a=fixture(tmp,"Qwen/Qwen3-ForcedAligner-0.6B")
            model=Mock();torch=types.SimpleNamespace(float16="fp16",bfloat16="bf16",float32="fp32")
            with patch.dict("sys.modules",{"torch":torch,"qwen_asr":types.SimpleNamespace(Qwen3ASRModel=model)}),patch("maw.local_asr.resolve_device",return_value="cpu"):
                QwenAsrEngine()._load()
            self.assertEqual(model.from_pretrained.call_args.args[0],str(p))
            self.assertEqual(model.from_pretrained.call_args.kwargs["forced_aligner"],str(a))


class LocalProgressTests(unittest.TestCase):
    def test_only_milestones_and_real_chunks_are_forwarded(self):
        from maw.focus_launcher import _local_progress
        for text in ["Retrying in 1s", "Loading checkpoint shards: 50%", "The following generation flags", "Traceback"]:
            self.assertIsNone(_local_progress(text))
        self.assertIsNotNone(_local_progress("[local] QwenASR loaded"))
        self.assertIsNotNone(_local_progress("[local] 警告：对齐失败"))
        result=_local_progress("[local] 正在识别第 2/4 段（30s - 60s）")
        self.assertEqual(result["progress"],25)
        self.assertTrue(result["progressKnown"])
        self.assertIsNone(_local_progress("[local] 正在识别第 0/0 段"))
