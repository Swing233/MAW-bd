import hashlib
import io
import json
import plistlib
import tempfile
import sys
import base64
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from maw.app_delta import apply_delta, build_delta, snapshot, set_signing_attribute, signing_attributes
from maw.app_update import _download_archive, check_latest_release, stage_update


class DeltaTests(unittest.TestCase):
    def app(self, root, version):
        root.mkdir()
        (root / "Contents").mkdir()
        (root / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": "com.moy.maw.bdversion", "CFBundleShortVersionString": version}))
        (root / "runtime").write_bytes(bytes(range(256)) * 4096)
        (root / "main").write_text(version)
        (root / "main").chmod(0o755)
        (root / "alias").symlink_to("main")
        return root

    def test_roundtrip_preserves_links_permissions_adds_and_deletes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, target = self.app(root / "base", "1.4.0"), self.app(root / "target", "1.5.0")
            (base / "obsolete").write_text("removed")
            (target / "new").write_text("added")
            before = snapshot(base)
            archive = root / "delta.zip"
            build_delta(base, target, archive)
            with zipfile.ZipFile(archive) as z:
                self.assertNotIn("files/runtime", z.namelist())
            apply_delta(base, archive, root / "result", "1.4.0", "1.5.0")
            self.assertEqual(snapshot(root / "result"), snapshot(target))
            self.assertEqual(snapshot(base), before)
            self.assertLess(archive.stat().st_size, (base / "runtime").stat().st_size)

    @unittest.skipUnless(sys.platform == "darwin", "macOS signing attributes")
    def test_signing_attributes_survive_delta_reconstruction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, target = self.app(root / "base", "1.4.0"), self.app(root / "target", "1.5.0")
            value = b"signature fixture"
            set_signing_attribute(target / "main", "com.apple.cs.CodeSignature", value)
            archive = root / "delta.zip"
            build_delta(base, target, archive)
            apply_delta(base, archive, root / "result", "1.4.0", "1.5.0")
            self.assertEqual(signing_attributes(root / "result/main"),
                             {"com.apple.cs.CodeSignature": base64.b64encode(value).decode("ascii")})

    def test_modified_base_and_wrong_version_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, target = self.app(root / "base", "1.4.0"), self.app(root / "target", "1.5.0")
            archive = root / "delta.zip"
            build_delta(base, target, archive)
            with self.assertRaises(ValueError):
                apply_delta(base, archive, root / "out", "1.3.0", "1.5.0")
            (base / "main").write_text("modified")
            with self.assertRaisesRegex(ValueError, "基础版本"):
                apply_delta(base, archive, root / "out", "1.4.0", "1.5.0")
            self.assertFalse((root / "out").exists())

    def test_unsafe_paths_and_payload_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, target = self.app(root / "base", "1.4.0"), self.app(root / "target", "1.5.0")
            archive = root / "delta.zip"
            manifest = build_delta(base, target, archive)
            for name in ("../escape", "alias/escape", "/escape"):
                bad = json.loads(json.dumps(manifest))
                bad["target"][name] = {"kind": "dir", "mode": 493}
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("manifest.json", json.dumps(bad))
                with self.assertRaises(ValueError):
                    apply_delta(base, archive, root / "out", "1.4.0", "1.5.0")
            build_delta(base, target, archive)
            with zipfile.ZipFile(archive) as z:
                entries = {i.filename: z.read(i) for i in z.infolist()}
            entries["files/main"] = b"evil!"
            with zipfile.ZipFile(archive, "w") as z:
                for name, data in entries.items():
                    z.writestr(name, data)
            with self.assertRaises(ValueError):
                apply_delta(base, archive, root / "out", "1.4.0", "1.5.0")

    def test_release_selects_only_exact_smaller_delta(self):
        def asset(name, size):
            return {"name": name, "size": size, "digest": "sha256:" + "a" * 64,
                    "browser_download_url": "https://github.com/Swing233/MAW-bd/releases/download/v1.5.0/" + name}
        full = asset("MAW-bd-1.5.0-macOS-arm64.zip", 1000)
        delta = asset("MAW-bd-1.4.0-to-1.5.0-macOS-arm64.delta.zip", 100)
        for current, expected in (("1.4.0", delta), ("1.3.0", None)):
            response = io.BytesIO(json.dumps({"tag_name": "v1.5.0", "assets": [delta, full]}).encode())
            with patch("maw.app_update.urllib.request.urlopen", return_value=response):
                result = check_latest_release(current)
            self.assertEqual(result["incremental"], None if expected is None else {
                "assetName": delta["name"], "assetSize": 100,
                "assetDigest": delta["digest"], "downloadUrl": delta["browser_download_url"]})

    def test_download_reports_bytes_total_and_speed(self):
        payload = b"hello" * 100000
        reports = []
        with tempfile.TemporaryDirectory() as temp, patch("maw.app_update.urllib.request.urlopen", return_value=io.BytesIO(payload)):
            _download_archive("https://example.invalid", len(payload), hashlib.sha256(payload).hexdigest(),
                              Path(temp) / "download", lambda *_: None, reports.append, "incremental")
        self.assertEqual(reports[0]["downloadedBytes"], 0)
        self.assertEqual(reports[-1]["downloadedBytes"], len(payload))
        self.assertEqual(reports[-1]["totalBytes"], len(payload))
        self.assertGreater(reports[-1]["bytesPerSecond"], 0)

    def test_staging_incremental_and_full_fallback(self):
        for method, broken in (("auto", False), ("auto", True), ("full", False)):
            with self.subTest(method=method, broken=broken), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                base = self.app(root / "MAW-bd.app", "1.4.0")
                target = self.app(root / "target", "1.5.0")
                delta_path = root / "delta.zip"
                build_delta(base, target, delta_path)
                delta_bytes = delta_path.read_bytes()
                if broken:
                    (base / "main").write_text("modified")
                original = snapshot(base)
                name = "MAW-bd-1.5.0-macOS-arm64.zip"
                delta_name = "MAW-bd-1.4.0-to-1.5.0-macOS-arm64.delta.zip"
                prefix = "https://github.com/Swing233/MAW-bd/releases/download/v1.5.0/"
                release = {"available": True, "currentVersion": "1.4.0", "latestVersion": "1.5.0",
                           "assetName": name, "assetSize": len(delta_bytes) + 100, "assetDigest": "sha256:" + "a" * 64,
                           "downloadUrl": prefix + name, "incremental": {
                               "assetName": delta_name, "assetSize": len(delta_bytes),
                               "assetDigest": "sha256:" + hashlib.sha256(delta_bytes).hexdigest(), "downloadUrl": prefix + delta_name}}
                downloads = []
                def download(url, size, digest, path, notify, transfer, kind):
                    downloads.append(kind)
                    path.write_bytes(delta_bytes if kind == "incremental" else b"full")
                def ditto(args, **kwargs):
                    import shutil
                    if "-x" in args:
                        shutil.copytree(target, Path(args[-1]) / "MAW-bd.app", symlinks=True)
                    else:
                        shutil.copytree(args[-2], args[-1], symlinks=True)
                with (patch("maw.app_update.update_cache_root", return_value=root / "cache"),
                      patch("maw.app_update._download_archive", side_effect=download),
                      patch("maw.app_update._validate_app_bundle"),
                      patch("maw.app_update._validate_zip_members"),
                      patch("maw.app_update.zipfile.ZipFile", wraps=zipfile.ZipFile) as z,
                      patch("maw.app_update.subprocess.run", side_effect=ditto)):
                    # Full extraction mock still needs a parseable ZIP.
                    def download_zip(*args):
                        download(*args)
                        if args[-1] == "full":
                            with zipfile.ZipFile(args[3], "w") as archive:
                                archive.writestr("placeholder", "ok")
                    with patch("maw.app_update._download_archive", side_effect=download_zip):
                        staged = stage_update(release, current_app=base, method=method)
                self.assertEqual(snapshot(Path(staged["staged"])), snapshot(target))
                self.assertEqual(snapshot(base), original)
                self.assertEqual(downloads, ["full"] if method == "full" else ["incremental", "full"] if broken else ["incremental"])
