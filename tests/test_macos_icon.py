"""Native icon decoding must preserve small Finder representations."""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_macos_icon import SOURCE, TARGET, read_png_frames


@unittest.skipUnless(sys.platform == "darwin", "requires macOS iconutil and sips")
class MacOSIconTests(unittest.TestCase):
    def test_finder_sizes_decode_as_source_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            iconset = root / "decoded.iconset"
            subprocess.run(["/usr/bin/iconutil", "-c", "iconset", str(TARGET), "-o", str(iconset)],
                           check=True, capture_output=True)
            for size in (16, 32):
                with self.subTest(size=size):
                    source = root / f"source-{size}.png"
                    source.write_bytes(read_png_frames(SOURCE)[size])
                    images = (source, iconset / f"icon_{size}x{size}.png")
                    pixels = []
                    for index, image in enumerate(images):
                        bmp = root / f"{size}-{index}.bmp"
                        subprocess.run(["/usr/bin/sips", "-s", "format", "bmp", str(image), "--out", str(bmp)],
                                       check=True, capture_output=True)
                        data = bmp.read_bytes()
                        self.assertEqual(struct.unpack_from("<iiHH", data, 18), (size, -size, 1, 32))
                        pixels.append(data[struct.unpack_from("<I", data, 10)[0]:])
                    differences = []
                    for offset in range(0, len(pixels[0]), 4):
                        original, decoded = (data[offset:offset + 4] for data in pixels)
                        self.assertEqual(original[3], decoded[3])
                        differences.append(max(abs(a - b) for a, b in zip(original[:3], decoded[:3])))
                    # Native classic icon encoding may round or replace an edge pixel.
                    # Require 99% of pixels to match, rejecting the old scrambled image.
                    self.assertLessEqual(sum(delta > 2 for delta in differences), max(1, size * size // 100))
                    self.assertLess(sum(differences) / len(differences), 2)
            for size in (16, 32, 128, 256, 512):
                for suffix in ("", "@2x"):
                    self.assertTrue((iconset / f"icon_{size}x{size}{suffix}.png").is_file())
