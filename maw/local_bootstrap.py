"""App-owned local ASR runtime, prepared by a bundled uv without system Python."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from maw.gui_workflow import TranscriptionCancelledError
from maw.local_log import redact_sensitive_text


def data_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "MAW-bd"


def runtime_python() -> Path:
    return data_root() / "local-runtime" / "bin" / "python"


def resources() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "bootstrap"
    return Path(__file__).resolve().parents[1] / "assets" / "runtime"


def bootstrap_uv() -> Path:
    if getattr(sys, "frozen", False):
        path = resources() / "uv"
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise RuntimeError("应用缺少内置环境安装器，请使用完整安装包")
    path = shutil.which("uv")
    candidate = Path(path) if path else Path.home() / ".local/bin/uv"
    if not candidate.is_file():
        raise RuntimeError("源码运行需要 uv；正式应用自带安装器")
    return candidate


def runtime_ready() -> bool:
    try:
        req = resources() / "requirements-local.txt"
        marker = json.loads((runtime_python().parent.parent / "ready.json").read_text())
        return runtime_python().is_file() and marker.get("requirementsSha256") == hashlib.sha256(req.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return False


def run_command(command, env, cancel, emit):
    if cancel.is_set():
        raise TranscriptionCancelledError()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, env=env, start_new_session=True)
    lines = deque(maxlen=8)
    def read():
        for line in process.stdout:
            text = redact_sensitive_text(line.strip())
            if text:
                lines.append(text)
                emit(text)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    started = last = time.monotonic()
    try:
        while process.poll() is None:
            if cancel.wait(0.2):
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                raise TranscriptionCancelledError()
            now = time.monotonic()
            if now - last >= 5:
                emit(f"运行环境下载/安装中 · 已用时 {int(now - started)} 秒")
                last = now
        reader.join(timeout=2)
        if cancel.is_set():
            raise TranscriptionCancelledError()
        if process.returncode:
            raise RuntimeError("运行环境安装失败：" + " · ".join(lines)[-1500:])
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        reader.join(timeout=2)
        process.stdout.close()


def ensure_runtime(engine, cancel, emit, *, runner=run_command) -> Path:
    imports = {"qwen-asr": "from qwen_asr import Qwen3ASRModel",
               "funasr": "from funasr import AutoModel",
               "whisper": "from faster_whisper import WhisperModel"}
    if engine not in imports:
        raise ValueError("不支持的本地引擎")
    if cancel.is_set():
        raise TranscriptionCancelledError()
    python = runtime_python()
    root = python.parent.parent
    req = resources() / "requirements-local.txt"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    env = os.environ.copy()
    # Keep Python, caches and all changes outside the signed .app and system paths.
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(key, None)
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
                "UV_PYTHON_INSTALL_DIR": str(data_root() / "python"),
                "UV_CACHE_DIR": str(data_root() / "download-cache"),
                "UV_PYTHON_DOWNLOADS": "automatic", "UV_NO_CONFIG": "1"})
    verify = [str(python), "-c", imports[engine] + "; import jieba, quapeaks; print('LOCAL_RUNTIME_READY')"]
    if runtime_ready():
        emit("正在检查已有本地运行环境…")
        try:
            runner(verify, env, cancel, emit)
            return python
        except RuntimeError:
            emit("本地运行环境需要修复，正在自动准备…")
    uv = bootstrap_uv()
    root.parent.mkdir(parents=True, exist_ok=True)
    marker = root / "ready.json"
    marker.unlink(missing_ok=True)
    if not python.is_file():
        emit("首次准备：正在下载应用专用 Python，无需安装系统 Python 或另一份 MAW")
        runner([str(uv), "--no-config", "venv", "--python", "3.11", "--managed-python", str(root)], env, cancel, emit)
    emit("正在安装本地识别依赖；首次安装可能下载较多文件，请保持窗口打开")
    runner([str(uv), "--no-config", "pip", "install", "--python", str(python),
            "--require-hashes", "--index-url", "https://pypi.org/simple", "-r", str(req)], env, cancel, emit)
    emit("正在验证本地运行环境…")
    runner(verify, env, cancel, emit)
    if cancel.is_set():
        raise TranscriptionCancelledError()
    if not python.is_file():
        raise RuntimeError("应用专用 Python 安装不完整")
    marker.write_text(json.dumps({"requirementsSha256": digest}), encoding="utf-8")
    emit("本地运行环境已就绪，继续准备模型…")
    return python
