"""Focused Launcher API — import → ASR → revise → editor only."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Mapping

from maw.bdversion.revise import revise_project
from maw.gui_config import DEFAULT_MODEL_ID, QWEN3_ASR_MODEL_ID, QWEN_AUDIO_MODEL_ID, load_env
from maw.gui_web import (
    EventPump,
    LocalLogSink,
    default_paths,
)
from maw.gui_workflow import (
    TranscriptionCancelledError,
    TranscriptionRequest,
    default_srt_path,
    run_transcription,
)
from maw.postprocess_io import read_srt
from maw.project_io import write_mosp

MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ts", ".m4v", ".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
MANUSCRIPT_EXTS = {".txt", ".md", ".markdown", ".docx"}


def local_runtime_python() -> Path:
    return Path.home() / "Library" / "Application Support" / "MAW" / "local-runtime" / "bin" / "python"


def local_model_cache_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "MAW" / "model-cache"


class FocusedLauncherApi:
    """pywebview JS API for the 4-step focused workflow."""

    def __init__(
        self,
        *,
        paths=None,
        default_server_port: int | None = None,
        log_sink: LocalLogSink | None = None,
    ) -> None:
        self.paths = paths or default_paths()
        self.default_server_port = default_server_port
        self._log_sink = log_sink
        self.pump = EventPump(window_getter=self._window)
        self.cancel_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.server_process: subprocess.Popen[str] | None = None
        self._server_project = ""
        self._server_url = ""
        self._status: dict[str, Any] = {
            "step": "idle",
            "message": "",
            "progress": 0,
            "busy": False,
            "error": "",
        }
        self._result: dict[str, Any] = {
            "mediaPath": "",
            "manuscriptPath": "",
            "manuscriptText": "",
            "srtPath": "",
            "projectPath": "",
            "revisedProjectPath": "",
            "revisedSrtPath": "",
        }
        self._step_progress: dict[str, int] = {
            "asr": 0,
            "revise": 0,
            "editor": 0,
        }

    def _set_status(self, **kwargs: Any) -> None:
        self._status.update(kwargs)
        step = str(self._status.get("step") or "")
        progress = kwargs.get("progress")
        if isinstance(progress, (int, float)):
            if step in {"asr", "asr_done"}:
                self._step_progress["asr"] = int(progress)
            elif step in {"revise", "revise_done"}:
                self._step_progress["revise"] = int(progress)
            elif step == "editor":
                self._step_progress["editor"] = 100
            if step == "error":
                # keep last non-zero bars
                pass
        event = {"type": "focusStatus", **self._status, "stepProgress": dict(self._step_progress)}
        self.pump.enqueue(event)

    def _emit_llm_delta(self, kind: str, text: str) -> None:
        """Forward redacted model progress/output to the Launcher's log rail."""

        value = str(text or "")
        if not value and kind not in {"reset"}:
            return
        # The callback only receives provider output, never headers or API keys.
        self.pump.enqueue({"type": "focusLlmDelta", "kind": str(kind), "text": value})

    # ---------- config ----------
    def save_config(self, payload: Mapping[str, object]) -> dict[str, object]:
        env_path = self.paths.env_path
        env_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()

        def put(key: str, value: object) -> None:
            text = "" if value is None else str(value).strip()
            if text:
                existing[key] = text
            else:
                existing.pop(key, None)

        # ASR uses local model — do not require/save DashScope from GUI
        put("MAW_POSTPROCESS_DEEPSEEK_API_KEY", payload.get("deepseekApiKey"))
        put("DEEPSEEK_API_KEY", payload.get("deepseekApiKey"))
        put("MAW_POSTPROCESS_DEEPSEEK_MODEL", payload.get("deepseekModel"))
        content = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
        env_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(env_path)}

    def build_gpt_srt_prompt(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        """Build a GPT-ready SRT revision prompt (+ optional manuscript) for copy."""

        payload = payload or {}
        project = str(payload.get("projectPath") or self._result.get("projectPath") or "").strip()
        srt_path = str(payload.get("srtPath") or self._result.get("srtPath") or "").strip()
        manuscript = str(payload.get("manuscriptText") or self._result.get("manuscriptText") or "").strip()
        custom = str(payload.get("customPrompt") or "").strip()
        srt_text = ""
        src = srt_path or ""
        if src and Path(src).is_file():
            _raw = Path(src).read_bytes()
            if _raw.startswith(b"\xef\xbb\xbf"):
                _raw = _raw[3:]
            srt_text = _raw.decode("utf-8")
        elif project and Path(project).is_file():
            try:
                from maw.bdversion.revise import _srt_from_segments, _load_project

                proj = _load_project(Path(project))
                srt_text = _srt_from_segments(proj.get("segments") or [])
            except Exception:
                srt_text = ""
        if not srt_text.strip():
            return {"ok": False, "error": "请先完成 ASR，再生成提示词"}

        output_stem = Path(src or project or "字幕").stem or "字幕"
        output_name = f"{output_stem}.校对.srt"

        lines = [
            "你是一名专业的字幕校对助手。请直接修改下面的 SRT 文案。",
            "",
            "【最高规则】",
            "1. 语音是真源：保留现场口语、即兴、重复、口误，不要改成书面文稿全文。",
            "2. 文稿（若有）只用于修正：同音/近音错字、错别字、人名、地名、专有名词、技术词。",
            "3. 不允许润色句式，不允许扩写或删减实质内容。",
            "4. 不确定时保持原文。",
            f"5. 请直接生成并提供一个名为「{output_name}」的 UTF-8 .srt 文件供下载，不要只回复说明。",
            "6. 保持序号、条数、分段边界与时间码完全不变，只改每条字幕内部的文字。",
            "7. 不得合并、拆分、删除或重排任何字幕条目。",
            "8. 如果当前界面无法创建文件附件，再输出完整 SRT 原文；不要解释，不要使用 Markdown 代码块。",
            "",
        ]
        if custom:
            lines.append(f"【用户额外要求】\n{custom}\n")
        if manuscript:
            lines.append(f"【文稿参考（仅纠错用，勿照抄）】\n{manuscript[:6000]}\n")
        lines.append("【待修改的 SRT】")
        lines.append(srt_text.strip())
        prompt = "\n".join(lines)
        self._result["gptPrompt"] = prompt
        return {"ok": True, "prompt": prompt, "length": len(prompt)}

    def browse_media(self, _payload=None) -> dict[str, object]:
        import webview

        window = self._window()
        if window is None:
            return {"ok": False, "error": "window not ready"}
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("媒体文件 (*.mp4;*.mkv;*.mov;*.wav;*.mp3;*.m4a;*.flac)",),
        )
        if not result:
            return {"ok": True, "path": ""}
        path = str(result[0])
        if Path(path).suffix.lower() not in MEDIA_EXTS:
            return {"ok": False, "error": "不支持的媒体类型"}
        self._result["mediaPath"] = path
        self._set_status(step="ready", message="已选择媒体", error="")
        return {"ok": True, "path": path}

    def _window(self):
        import webview

        windows = getattr(webview, "windows", None) or []
        return windows[0] if windows else None

    # ---------- state ----------
    def get_state(self, _payload: Mapping[str, object] | None = None) -> dict[str, object]:
        env = load_env(self.paths.env_path)
        rt_py = local_runtime_python()
        return {
            "ok": True,
            "title": "MAW-bd",
            "status": {**self._status, "stepProgress": dict(self._step_progress)},
            "result": dict(self._result),
            "config": {
                "dashscopeApiKey": bool(env.get("DASHSCOPE_API_KEY")),
                "deepseekApiKey": bool(env.get("MAW_POSTPROCESS_DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY")),
                "modelId": "local-qwen3-asr",
                "asrModes": [
                    {"id": "local", "label": "本地模型（默认）"},
                    {"id": "cloud", "label": "云端 Qwen API"},
                ],
                "localEngines": [
                    {"id": "qwen-asr", "label": "Qwen3-ASR 1.7B"},
                    {"id": "funasr", "label": "FunASR paraformer-zh"},
                    {"id": "whisper", "label": "faster-whisper"},
                ],
                "localModel": "Qwen/Qwen3-ASR-1.7B",
                "localRuntimeReady": rt_py.is_file(),
                "localRuntimePath": str(rt_py),
                "cloudModels": [
                    {"id": QWEN_AUDIO_MODEL_ID, "label": "qwen-audio-3.0"},
                    {"id": QWEN3_ASR_MODEL_ID, "label": "qwen3-asr"},
                ],
                "reviseModes": [
                    {"id": "deepseek", "label": "DeepSeek 保守校对"},
                    {"id": "custom", "label": "自定义提示词"},
                ],
                "deepseekModel": env.get("MAW_POSTPROCESS_DEEPSEEK_MODEL") or "deepseek-flash",
            },
        }

    def set_manuscript_text(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        payload = payload or {}
        text = str(payload.get("text") or "")
        self._result["manuscriptText"] = text
        # marker only — never store paste body in manuscriptPath
        self._result["manuscriptPath"] = "(pasted)" if text.strip() else ""
        if text.strip():
            self._set_status(step="ready", message="已添加文稿（对话框输入）", error="")
        return {"ok": True, "hasText": bool(text.strip()), "length": len(text)}

    def clear_manuscript(self, _payload=None) -> dict[str, object]:
        self._result["manuscriptPath"] = ""
        self._result["manuscriptText"] = ""
        return {"ok": True}

    # ---------- ASR ----------
    def start_asr(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        if self.worker and self.worker.is_alive():
            return {"ok": False, "error": "任务进行中"}
        payload = payload or {}
        media = str(payload.get("mediaPath") or self._result.get("mediaPath") or "").strip()
        if not media or not Path(media).is_file():
            return {"ok": False, "error": "请先选择媒体文件"}
        asr_mode = str(payload.get("asrMode") or "local").strip() or "local"
        engine = str(payload.get("localEngine") or "qwen-asr").strip() or "qwen-asr"
        local_model = str(payload.get("localModel") or "Qwen/Qwen3-ASR-1.7B")
        if engine not in {"qwen-asr", "funasr", "whisper"}:
            engine = "qwen-asr"
        model = str(payload.get("modelId") or DEFAULT_MODEL_ID)
        if model not in {QWEN_AUDIO_MODEL_ID, QWEN3_ASR_MODEL_ID}:
            model = DEFAULT_MODEL_ID

        media_path = Path(media)
        if asr_mode == "local":
            srt_path = default_srt_path(media_path, provider="local", model=f"{engine}-local")
        else:
            env = load_env(self.paths.env_path)
            api_key = env.get("DASHSCOPE_API_KEY", "").strip()
            if not api_key:
                return {"ok": False, "error": "云端 ASR 需要 DASHSCOPE_API_KEY"}
            srt_path = default_srt_path(media_path, provider="qwen", model=model)
        self._result["mediaPath"] = media
        self._result["srtPath"] = str(srt_path)
        self._result["revisedProjectPath"] = ""
        self._result["revisedSrtPath"] = ""
        self.cancel_event = threading.Event()
        label = "本地模型" if asr_mode == "local" else "云端 Qwen"
        self._step_progress["asr"] = 0
        self._set_status(step="asr", message=f"正在 ASR 识别（{label}）…", progress=0, busy=True, error="")
        self.pump.start()
        self.worker = threading.Thread(
            target=self._asr_worker,
            args=(media_path, srt_path, asr_mode, engine, model, local_model),
            daemon=True,
        )
        self.worker.start()
        return {"ok": True, "srtPath": str(srt_path), "asrMode": asr_mode}

    def _asr_worker(self, media_path: Path, srt_path: Path, asr_mode: str, engine: str, model: str, local_model: str = "Qwen/Qwen3-ASR-1.7B") -> None:
        try:
            if asr_mode == "local":
                self._run_local_asr(media_path, srt_path, engine, local_model=local_model)
            else:
                self._run_cloud_asr(media_path, srt_path, model)
        except TranscriptionCancelledError:
            self._set_status(step="idle", message="已取消", busy=False, error="")
        except Exception as error:  # noqa: BLE001
            self._set_status(step="error", message="ASR 失败", busy=False, error=str(error))


    def _run_cloud_asr(self, media_path: Path, srt_path: Path, model: str) -> None:
        env = load_env(self.paths.env_path)
        api_key = env.get("DASHSCOPE_API_KEY", "").strip()
        request = TranscriptionRequest(
            media_path=media_path,
            srt_path=srt_path,
            model=model,
            api_key=api_key,
            provider="qwen",
            generate_html=False,
        )
        self._set_status(progress=30, message="调用云端 Qwen ASR…")
        result = run_transcription(request, cancel_event=self.cancel_event)
        self._result["srtPath"] = str(result.srt_path)
        self._result["projectPath"] = str(result.json_path)
        self._set_status(step="asr_done", message="ASR 完成（仅识别，未额外断句）", progress=100, busy=False, error="")

    def _run_local_asr(self, media_path: Path, srt_path: Path, engine: str, local_model: str = "Qwen/Qwen3-ASR-1.7B") -> None:
        runtime_py = local_runtime_python()
        if not runtime_py.is_file():
            raise RuntimeError(
                f"未找到本地推理环境：{runtime_py}\n"
                "请先安装 MAW 本地 Runtime，或在界面改用云端 Qwen。"
            )
        script = self.paths.root / "generate_subtitle_local.py"
        if not script.is_file():
            exe = Path(sys.executable)
            alt = exe.parent.parent / "Resources" / "local-runtime" / "generate_subtitle_local.py"
            script = alt if alt.is_file() else script
        if not script.is_file():
            raise RuntimeError("找不到 generate_subtitle_local.py")
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        cache_root = local_model_cache_root()
        runtime_root = script.parent
        env = os.environ.copy()
        env["MAW_MODEL_CACHE_ROOT"] = str(cache_root)
        env["HF_HOME"] = str(cache_root / "huggingface")
        env["MODELSCOPE_CACHE"] = str(cache_root / "modelscope")
        env["PYTHONPATH"] = str(runtime_root) + os.pathsep + str(self.paths.root) + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [
            str(runtime_py),
            str(script),
            str(media_path),
            "--engine",
            engine,
            "--json",
            "--no-html",
            "--device",
            "auto",
            "--max-len",
            "20",
            "--min-len",
            "5",
            "--gap-split",
            "750",
            "-o",
            str(srt_path),
        ]
        if engine == "qwen-asr":
            model = str(local_model or "Qwen/Qwen3-ASR-1.7B")
            cmd.extend(["--model", model])
        self._set_status(progress=20, message=f"本地引擎 {engine} 启动中…（{model if engine=='qwen-asr' else engine}）")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        self._local_process = process
        collected: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            collected.append(line)
            if self.cancel_event.is_set():
                process.terminate()
                raise TranscriptionCancelledError()
            text = line.strip()
            if text:
                self._set_status(progress=40, message=text[:180])
        code = process.wait()
        self._local_process = None
        if self.cancel_event.is_set():
            raise TranscriptionCancelledError()
        if code != 0:
            tail = "".join(collected)[-800:]
            raise RuntimeError(f"本地 ASR 退出码 {code}：{tail}")
        # discover outputs (may have engine suffix)
        project = srt_path.with_suffix(".mosp")
        if not project.exists():
            candidates = sorted(srt_path.parent.glob(srt_path.stem + "*.mosp"))
            project = candidates[0] if candidates else project
        actual_srt = srt_path
        if not actual_srt.exists():
            cands = sorted(srt_path.parent.glob(srt_path.stem + "*.srt"))
            actual_srt = cands[0] if cands else actual_srt
        self._result["srtPath"] = str(actual_srt)
        self._result["projectPath"] = str(project)
        self._set_status(step="asr_done", message="ASR 完成（仅识别，未额外断句）", progress=100, busy=False, error="")

    # ---------- revise ----------
    def start_revise(self, payload: Mapping[str, object]) -> dict[str, object]:
        if self.worker and self.worker.is_alive():
            return {"ok": False, "error": "任务进行中"}
        project = str(payload.get("projectPath") or self._result.get("projectPath") or "").strip()
        if not project:
            srt = str(self._result.get("srtPath") or "")
            if srt:
                base = Path(srt).with_suffix(".mosp")
                project = str(base) if base.exists() else ""
        project = str(project or "").strip()
        if not project or len(project) > 1024 or "\n" in project:
            return {"ok": False, "error": "工程路径无效，请先完成 ASR"}
        try:
            if not Path(project).is_file():
                return {"ok": False, "error": "请先完成 ASR（需要 .mosp 工程）"}
        except OSError:
            return {"ok": False, "error": "工程路径无效，请先完成 ASR"}
        mode = str(payload.get("mode") or "deepseek")
        env = load_env(self.paths.env_path)
        api_key = (
            str(payload.get("deepseekApiKey") or "").strip()
            or env.get("MAW_POSTPROCESS_DEEPSEEK_API_KEY", "").strip()
            or env.get("DEEPSEEK_API_KEY", "").strip()
        )
        model = str(payload.get("deepseekModel") or env.get("MAW_POSTPROCESS_DEEPSEEK_MODEL") or "deepseek-flash")
        custom_prompt = str(payload.get("customPrompt") or "")
        # Manuscript is TEXT only. Never pass long pastes as a filesystem path.
        manuscript = str(payload.get("manuscriptText") or self._result.get("manuscriptText") or "")
        ms_path = str(payload.get("manuscriptPath") or self._result.get("manuscriptPath") or "")
        if not manuscript.strip() and ms_path and ms_path not in {"(pasted)", "-"} and len(ms_path) < 512 and "\n" not in ms_path:
            manuscript = ms_path  # real short path to .txt/.md/.docx
        self._step_progress["revise"] = 0
        self._set_status(step="revise", message="正在修订字幕…", progress=0, busy=True, error="")
        self.pump.start()
        self.worker = threading.Thread(
            target=self._revise_worker,
            args=(project, mode, api_key, model, custom_prompt, manuscript),
            daemon=True,
        )
        self.worker.start()
        return {"ok": True}

    def _revise_worker(self, project: str, mode: str, api_key: str, model: str, custom_prompt: str, manuscript: str) -> None:
        try:
            self._set_status(progress=50, message="调用 LLM…")
            out = revise_project(
                project,
                mode=mode,
                api_key=api_key,
                model=model,
                custom_prompt=custom_prompt,
                apply_to_text=True,
                manuscript=manuscript or None,
                on_llm_delta=self._emit_llm_delta,
            )
            if not out.get("ok"):
                self._set_status(step="error", message="修订失败", busy=False, error=str(out.get("error") or "unknown"))
                return
            self._result["projectPath"] = out.get("projectPath") or project
            self._result["revisedProjectPath"] = out.get("projectPath") or ""
            self._result["revisedSrtPath"] = out.get("srtPath") or ""
            self._result["srtPath"] = out.get("srtPath") or self._result.get("srtPath") or ""
            used = "含文稿参考" if out.get("manuscriptUsed") else "无文稿"
            msg = f"修订完成（{out.get('changedCues', 0)} 条有改动 · {used}）"
            msg += " · 保留 ASR 分段与时间轴"
            self._step_progress["revise"] = 100
            self._set_status(step="revise_done", message=msg, progress=100, busy=False, error="")
        except Exception as error:  # noqa: BLE001
            self._set_status(step="error", message="修订失败", busy=False, error=str(error))

    def stop_task(self, _payload=None) -> dict[str, object]:
        self.cancel_event.set()
        proc = getattr(self, "_local_process", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        return {"ok": True}

    # ---------- editor ----------


    def start_resegment(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        """Re-split current/ revised project into short one-sentence cues."""

        if self.worker and self.worker.is_alive():
            return {"ok": False, "error": "任务进行中"}
        payload = payload or {}
        project = str(
            payload.get("projectPath")
            or self._result.get("revisedProjectPath")
            or self._result.get("projectPath")
            or ""
        ).strip()
        if not project:
            return {"ok": False, "error": "请先 ASR / 修订"}
        try:
            if not Path(project).is_file():
                return {"ok": False, "error": "工程文件不存在"}
        except OSError:
            return {"ok": False, "error": "工程路径无效"}

        def worker() -> None:
            try:
                self._set_status(step="resegment", message="正在按句断句…", progress=30, busy=True, error="")
                from maw.bdversion.revise import resegment_project

                out = resegment_project(project, max_len=20, min_len=5, gap_split_ms=750)
                if not out.get("ok"):
                    self._set_status(step="error", message="断句失败", busy=False, error=str(out.get("error") or "unknown"))
                    return
                self._result["revisedProjectPath"] = out.get("projectPath") or project
                self._result["revisedSrtPath"] = out.get("srtPath") or ""
                self._result["projectPath"] = out.get("projectPath") or project
                self._result["srtPath"] = out.get("srtPath") or self._result.get("srtPath") or ""
                self._step_progress["revise"] = 100
                self._set_status(
                    step="resegment_done",
                    message=f"断句完成（{out.get('cueCount', 0)} 条）",
                    progress=100,
                    busy=False,
                    error="",
                )
            except Exception as error:  # noqa: BLE001
                self._set_status(step="error", message="断句失败", busy=False, error=str(error))

        self.pump.start()
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()
        return {"ok": True}

    def open_existing_project(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        """Native dialog: pick .mosp/.json and open it in MAWE."""

        import webview

        payload = payload or {}
        project = str(payload.get("projectPath") or "").strip()
        if not project:
            window = self._window()
            if window is None:
                return {"ok": False, "error": "window not ready"}
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("工程 (*.mosp;*.json)",),
            )
            if not result:
                return {"ok": True, "cancelled": True}
            project = str(result[0])
        path = Path(project).expanduser()
        if not path.is_file():
            return {"ok": False, "error": "工程文件不存在"}
        if path.suffix.lower() not in {".mosp", ".json"}:
            return {"ok": False, "error": "仅支持 .mosp / .json 工程"}
        self._result["projectPath"] = str(path)
        # media: try sibling guess — editor will prompt if missing
        self._result["revisedProjectPath"] = ""
        media = str(payload.get("mediaPath") or "").strip()
        opened = self.open_editor({"projectPath": str(path), "mediaPath": media})
        if not opened.get("ok"):
            return opened
        self._set_status(step="editor", message=f"已导入工程：{path.name}", progress=100, busy=False, error="")
        return {**opened, "projectPath": str(path)}

    def open_media_editor(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        """Create/open a media-backed edit project without running ASR."""

        import webview

        payload = payload or {}
        media = str(payload.get("mediaPath") or "").strip()
        if not media:
            window = self._window()
            if window is None:
                return {"ok": False, "error": "window not ready"}
            result = window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("视频 / 音频 (*.mp4;*.mov;*.mkv;*.m4v;*.wav;*.mp3;*.m4a;*.flac)",),
            )
            if not result:
                return {"ok": True, "cancelled": True}
            media = str(result[0])
        media_path = Path(media).expanduser().resolve()
        if not media_path.is_file() or media_path.suffix.lower() not in MEDIA_EXTS:
            return {"ok": False, "error": "请选择有效的 MP4 或其它受支持音视频文件"}

        project_path = media_path.with_name(f"{media_path.stem}.maw-edit.mosp")
        srt_path = media_path.with_suffix(".srt")
        if not project_path.exists():
            try:
                project = read_srt(srt_path) if srt_path.is_file() else {"segments": []}
                project["media"] = str(media_path)
                if srt_path.is_file():
                    project["model"] = "srt-import"
                write_mosp(project_path, project, media_path=media_path)
            except Exception as error:  # noqa: BLE001
                return {"ok": False, "error": f"无法创建编辑工程：{error}"}

        self._result["mediaPath"] = str(media_path)
        self._result["projectPath"] = str(project_path)
        self._result["revisedProjectPath"] = ""
        self._result["srtPath"] = str(srt_path) if srt_path.is_file() else ""
        opened = self.open_editor({"projectPath": str(project_path)})
        if not opened.get("ok"):
            return opened
        message = f"已载入同名 SRT：{srt_path.name}" if srt_path.is_file() else "编辑器已打开，可在其中加载 SRT"
        self._set_status(step="editor", message=message, progress=100, busy=False, error="")
        return {
            **opened,
            "mediaPath": str(media_path),
            "projectPath": str(project_path),
            "srtPath": str(srt_path) if srt_path.is_file() else "",
            "importedSrt": srt_path.is_file(),
        }

    def open_editor(self, payload: Mapping[str, object] | None = None) -> dict[str, object]:
        payload = payload or {}
        project = str(
            payload.get("projectPath")
            or self._result.get("revisedProjectPath")
            or self._result.get("projectPath")
            or ""
        ).strip()
        media = str(payload.get("mediaPath") or self._result.get("mediaPath") or "").strip()
        if project:
            if len(project) > 1024 or "\n" in project:
                return {"ok": False, "error": "工程路径无效"}
            try:
                if not Path(project).is_file():
                    return {"ok": False, "error": f"工程文件不存在：{project[:200]}"}
            except OSError:
                return {"ok": False, "error": "工程路径无效"}
        if media:
            try:
                if not Path(media).is_file():
                    media = ""  # missing media must not block editor
            except OSError:
                media = ""
        if not project:
            media = ""  # blank editor can open before media is selected

        # Reopening the same editor must not discard unsaved browser work.
        if self.server_process and self.server_process.poll() is None:
            if self._server_url and (not project or project == self._server_project):
                try:
                    import webbrowser

                    webbrowser.open(self._server_url)
                except Exception:
                    pass
                return {
                    "ok": True,
                    "projectPath": self._server_project,
                    "blank": not bool(self._server_project),
                    "url": self._server_url,
                }
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=2)
            except Exception:
                pass
            self.server_process = None
            self._server_project = ""
            self._server_url = ""

        # pick a free port (8250 or scan)
        port = int(self.default_server_port or 8250)
        for _ in range(32):
            if self._port_free(port):
                break
            port += 1
        else:
            return {"ok": False, "error": "本机 8250 起连续端口均被占用，请关闭已打开的编辑器"}

        frozen = bool(getattr(sys, "frozen", False))
        env = os.environ.copy()
        root = str(self.paths.root)
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        # Keep waveform generation enabled even for a blank editor.  A blank
        # server has no media to process at startup, but it can later take over
        # a .mosp opened from the editor.  That takeover must generate/reuse the
        # sidecar on the backend; otherwise large media falls back to the
        # browser decoder and is rejected by its memory guard.
        if frozen:
            cmd = [sys.executable, "--serve"]
        else:
            serve_py = self.paths.root / "server-editor" / "serve.py"
            if not serve_py.is_file():
                return {"ok": False, "error": f"找不到 server-editor：{serve_py}"}
            cmd = [sys.executable, str(serve_py)]
        cmd.extend([project] if project else ["--blank"])
        cmd.extend(["--no-open", "-p", str(port)])
        if media:
            cmd.extend(["-m", media])

        try:
            self.server_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": f"启动编辑器进程失败：{error}"}

        url = f"http://127.0.0.1:{port}/"
        ready = self._wait_http_ready(url, timeout=20.0)
        if not ready:
            if self.server_process and self.server_process.poll() is not None:
                code = self.server_process.returncode
                return {"ok": False, "error": f"编辑器进程已退出（退出码 {code}）"}
            return {"ok": False, "error": f"编辑器未在 {url} 就绪，请检查工程/端口后重试"}

        self._server_project = project
        self._server_url = url

        # open browser from this process
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

        self._step_progress["editor"] = 100
        self._set_status(
            step="editor",
            message=f"编辑器已启动 {url}",
            progress=100,
            busy=False,
            error="",
        )
        return {"ok": True, "projectPath": project, "blank": not bool(project), "url": url, "port": port}

    @staticmethod
    def _port_free(port: int) -> bool:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.3)
            try:
                sock.connect(("127.0.0.1", port))
            except OSError:
                return True
            return False

    @staticmethod
    def _wait_http_ready(url: str, timeout: float = 20.0) -> bool:
        import time
        import urllib.request

        deadline = time.time() + timeout
        probe = url.rstrip("/") + "/api/startup-status"
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(probe, timeout=1.0) as resp:
                    if 200 <= int(getattr(resp, "status", 200) or 200) < 300:
                        return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def shutdown(self, _payload=None) -> dict[str, object]:
        self.cancel_event.set()
        proc = getattr(self, "_local_process", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        return {"ok": True}
