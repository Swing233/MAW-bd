"""Build the macOS ICNS asset using native IconServices-compatible encoding."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "maw.ico"
TARGET = ROOT / "assets" / "maw.icns"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# PNG payloads copied directly into small ICNS tags decode incorrectly in
# IconServices. Let iconutil choose the native encoding for every representation.
SOURCE_SIZES = (16, 32, 64, 128, 256)
ICONSET_SIZES = (16, 32, 128, 256, 512)


def read_png_frames(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    if len(data) < 6 or data[:2] != b"\x00\x00" or data[2:4] != b"\x01\x00":
        raise ValueError(f"{path} is not an ICO file")

    count = int.from_bytes(data[4:6], "little")
    frames: dict[int, bytes] = {}
    for index in range(count):
        entry_offset = 6 + index * 16
        if entry_offset + 16 > len(data):
            raise ValueError(f"{path} has a truncated ICO directory")
        width = data[entry_offset] or 256
        height = data[entry_offset + 1] or 256
        size = int.from_bytes(data[entry_offset + 8 : entry_offset + 12], "little")
        offset = int.from_bytes(data[entry_offset + 12 : entry_offset + 16], "little")
        payload = data[offset : offset + size]
        if width != height or len(payload) != size or not payload.startswith(PNG_SIGNATURE):
            raise ValueError(f"ICO frame {width}x{height} is not a complete PNG payload")
        if width in SOURCE_SIZES:
            frames[width] = payload

    missing = sorted(set(SOURCE_SIZES) - set(frames))
    if missing:
        sizes = ", ".join(f"{size}x{size}" for size in missing)
        raise ValueError(f"{path} is missing required icon sizes: {sizes}")
    return frames


def build_icns(frames: dict[int, bytes]) -> bytes:
    with tempfile.TemporaryDirectory(prefix="maw-icon-") as directory:
        root = Path(directory)
        iconset = root / "maw.iconset"
        iconset.mkdir()
        for size, payload in frames.items():
            (root / f"source-{size}.png").write_bytes(payload)
        for size in ICONSET_SIZES:
            for scale in (1, 2):
                pixels = size * scale
                source_size = pixels if pixels in frames else max(frames)
                source = root / f"source-{source_size}.png"
                suffix = "@2x" if scale == 2 else ""
                target = iconset / f"icon_{size}x{size}{suffix}.png"
                subprocess.run(
                    ["/usr/bin/sips", "-z", str(pixels), str(pixels), str(source), "--out", str(target)],
                    check=True, capture_output=True,
                )
        result = root / "maw.icns"
        subprocess.run(
            ["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(result)],
            check=True, capture_output=True,
        )
        return result.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the tracked ICNS matches the source ICO without writing it",
    )
    args = parser.parse_args()

    expected = build_icns(read_png_frames(SOURCE))
    if args.check:
        actual = TARGET.read_bytes() if TARGET.is_file() else None
        if actual != expected:
            raise SystemExit(f"{TARGET} is missing or out of date; run this script without --check")
        print(f"{TARGET} is up to date")
        return 0

    TARGET.write_bytes(expected)
    print(f"Wrote {TARGET} ({len(expected)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
