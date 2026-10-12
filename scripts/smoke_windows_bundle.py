"""Exercise the packaged Windows editor and bundled media tools without API keys."""

import argparse
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request


def smoke(app: Path) -> None:
    executable = app / "MAW-bd.exe"
    with executable.open("rb") as binary:
        header = binary.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise RuntimeError("Not a Windows PE executable")
        binary.seek(struct.unpack_from("<I", header, 60)[0])
        pe = binary.read(6)
        if (
            pe[:4] != b"PE\0\0"
            or len(pe) != 6
            or struct.unpack_from("<H", pe, 4)[0] != 0x8664
        ):
            raise RuntimeError("Windows package must contain an x64 executable")
    for relative in [
        "MAW-bd.exe",
        "_internal/bootstrap/uv.exe",
        "_internal/bootstrap/requirements-local.txt",
        "_internal/local-runtime/generate_subtitle_local.py",
        "ffmpeg/bin/ffmpeg.exe",
        "ffmpeg/bin/ffprobe.exe",
    ]:
        if not (app / relative).is_file():
            raise RuntimeError(f"Missing Windows payload: {relative}")
    forbidden = [
        p
        for p in app.rglob("*")
        if p.name == ".env" or p.suffix in {".mosp", ".srt", ".safetensors"}
    ]
    if forbidden:
        raise RuntimeError("User data found in Windows package")
    with tempfile.TemporaryDirectory(prefix="maw-win-smoke-") as temp:
        root = Path(temp) / "字幕 测试工程"
        root.mkdir()
        media = root / "演示视频.mp4"
        subprocess.run(
            [
                str(app / "ffmpeg/bin/ffmpeg.exe"),
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x180:r=25",
                "-t",
                "2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(media),
            ],
            check=True,
            timeout=30,
        )
        project = root / "字幕工程.mosp"
        project.write_text(
            json.dumps(
                {
                    "media": str(media),
                    "segments": [
                        {
                            "start": 0,
                            "end": 1000,
                            "text": "Windows 字幕测试",
                            "items": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = os.environ.copy()
        (root / "empty.env").touch()
        env.update(
            MAW_ENV_FILE=str(root / "empty.env"),
            MAW_APP_DATA_ROOT=str(root / "settings"),
            MAW_BD_DATA_ROOT=str(root / "runtime"),
            PYINSTALLER_RESET_ENVIRONMENT="1",
        )
        with (root / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    str(executable),
                    "--serve",
                    str(project),
                    "--media",
                    str(media),
                    "--no-open",
                    "--no-waveform",
                    "--port",
                    str(port),
                ],
                stdout=log,
                stderr=log,
                env=env,
            )
            try:
                deadline = time.monotonic() + 45
                url = f"http://127.0.0.1:{port}/"
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(
                            (root / "server.log").read_text(encoding="utf-8")
                        )
                    try:
                        with urllib.request.urlopen(
                            url + "api/startup-status", timeout=2
                        ) as response:
                            status = json.load(response)
                        if status.get("status") == "error":
                            raise RuntimeError(f"Packaged startup error: {status}")
                        if status.get("status") == "ready":
                            with urllib.request.urlopen(url, timeout=2) as response:
                                page = response.read().decode("utf-8")
                            if (
                                "Windows 字幕测试" not in page
                                or "MaweProofread" not in page
                            ):
                                raise RuntimeError(
                                    "Packaged editor is missing project text or proofreader"
                                )
                            media_request = urllib.request.Request(
                                url + "media", headers={"Range": "bytes=0-15"}
                            )
                            with urllib.request.urlopen(
                                media_request, timeout=2
                            ) as response:
                                if response.status != 206 or len(response.read()) != 16:
                                    raise RuntimeError(
                                        "Packaged media seek did not return the requested range"
                                    )
                            print(
                                "Windows packaged editor, Chinese paths, media seek and FFmpeg passed."
                            )
                            return
                    except OSError:
                        pass
                    time.sleep(0.2)
                raise RuntimeError("Packaged Windows editor did not become ready")
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    smoke(args.app.resolve())
