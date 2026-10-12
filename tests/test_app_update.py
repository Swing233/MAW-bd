"""GitHub Release update checks."""

from __future__ import annotations

import json
import io
import sys
import urllib.error
import hashlib
import plistlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from maw.app_update import (
    UpdateCheckError,
    UpdateInstallError,
    _validate_app_bundle,
    _validate_zip_members,
    check_latest_release,
    is_newer_version,
    stage_update,
    version_key,
)


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self._payload


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        # These installer fixtures represent the macOS package on any test host.
        platform = patch("maw.app_update.sys.platform", "darwin")
        platform.start()
        self.addCleanup(platform.stop)

    def test_release_cache_reuses_metadata_across_installed_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "release.json"
            with patch("maw.app_update.time.time", return_value=1000), patch(
                "maw.app_update.urllib.request.urlopen", return_value=_Response({"tag_name": "v1.8.0", "assets": []})
            ) as request:
                self.assertTrue(check_latest_release("1.7.0", cache_path=cache)["available"])
                result = check_latest_release("1.8.0", cache_path=cache)
                self.assertFalse(result["available"])
                self.assertTrue(result["cached"])
                request.assert_called_once()

    def test_rate_limit_cooldown_survives_restart_and_stops_requests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "release.json"
            error = urllib.error.HTTPError("https://api.github.com", 403, "rate limit exceeded",
                                           {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1600"},
                                           io.BytesIO(b'{"message":"API rate limit exceeded"}'))
            with patch("maw.app_update.time.time", return_value=1000), patch(
                "maw.app_update.urllib.request.urlopen", side_effect=error
            ) as request:
                for _ in range(2):
                    with self.assertRaisesRegex(UpdateCheckError, "10 分钟"):
                        check_latest_release("1.7.0", cache_path=cache)
                request.assert_called_once()
            with patch("maw.app_update.time.time", return_value=1601), patch(
                "maw.app_update.urllib.request.urlopen", return_value=_Response({"tag_name":"v1.8.0"})
            ) as request:
                self.assertTrue(check_latest_release("1.7.0", cache_path=cache)["available"])
                request.assert_called_once()

    def test_secondary_rate_limit_reuses_cached_result_without_claiming_freshness(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "release.json"
            cache.write_text(json.dumps({"payload":{"tag_name":"v1.8.0"}, "fetchedAt":100}), encoding="utf-8")
            error = urllib.error.HTTPError("https://api.github.com", 429, "slow down", {"Retry-After":"180"}, io.BytesIO(b''))
            with patch("maw.app_update.time.time", return_value=1000), patch("maw.app_update.urllib.request.urlopen", side_effect=error):
                result = check_latest_release("1.7.0", cache_path=cache)
            self.assertTrue(result["cached"])
            self.assertIn("3 分钟", result["warning"])
            self.assertTrue(result["available"])

    def test_unrelated_forbidden_error_does_not_start_rate_limit_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp) / "release.json"
            error = urllib.error.HTTPError("https://api.github.com", 403, "Forbidden", {}, io.BytesIO(b'Forbidden'))
            with patch("maw.app_update.urllib.request.urlopen", side_effect=error):
                with self.assertRaisesRegex(UpdateCheckError, "HTTP 403"):
                    check_latest_release("1.7.0", cache_path=cache)
            self.assertFalse(cache.exists())

    def test_numeric_version_comparison(self) -> None:
        self.assertEqual(version_key("v1.2.10"), (1, 2, 10, 0))
        self.assertTrue(is_newer_version("1.10.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.0.1", "1.0.1"))

    def test_latest_release_selects_arm64_asset(self) -> None:
        payload = {
            "tag_name": "v1.1.0",
            "body": "修复与更新",
            "published_at": "2026-09-21T00:00:00Z",
            "assets": [
                {
                    "name": "MAW-bd-1.1.0-macOS-arm64.zip",
                    "browser_download_url": "https://github.com/Swing233/MAW-bd/releases/download/v1.1.0/MAW-bd-1.1.0-macOS-arm64.zip",
                    "size": 42,
                    "digest": "sha256:" + "a" * 64,
                }
            ],
        }
        with patch("maw.app_update.urllib.request.urlopen", return_value=_Response(payload)):
            result = check_latest_release("1.0.1")
        self.assertTrue(result["available"])
        self.assertEqual(result["latestVersion"], "1.1.0")
        self.assertEqual(result["assetSize"], 42)
        self.assertEqual(result["assetDigest"], "sha256:" + "a" * 64)
        self.assertTrue(str(result["downloadUrl"]).endswith("macOS-arm64.zip"))

    def test_untrusted_asset_url_is_not_returned(self) -> None:
        payload = {
            "tag_name": "v1.1.0",
            "assets": [{"name": "MAW-bd-1.1.0-macOS-arm64.zip", "browser_download_url": "https://example.invalid/update.zip"}],
        }
        with patch("maw.app_update.urllib.request.urlopen", return_value=_Response(payload)):
            result = check_latest_release("1.0.1")
        self.assertEqual(result["downloadUrl"], "")
        self.assertTrue(str(result["releaseUrl"]).startswith("https://github.com/Swing233/MAW-bd/releases/tag/"))

    def test_invalid_release_tag_is_rejected(self) -> None:
        with patch("maw.app_update.urllib.request.urlopen", return_value=_Response({"tag_name": "nightly"})):
            with self.assertRaises(UpdateCheckError):
                check_latest_release("1.0.1")

    def test_installer_rejects_zip_traversal_and_outside_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("MAW-bd.app/../../escaped", "bad")
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(UpdateInstallError):
                    _validate_zip_members(archive)

            link = zipfile.ZipInfo("MAW-bd.app/Contents/Resources/escape")
            link.create_system = 3
            link.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(link, "../../../../outside")
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaises(UpdateInstallError):
                    _validate_zip_members(archive)

    def test_installer_accepts_official_archive_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive_path = Path(temp) / "good.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("MAW-bd.app/Contents/Info.plist", b"plist")
                archive.writestr("__MACOSX/MAW-bd.app/._Contents", b"metadata")
            with zipfile.ZipFile(archive_path) as archive:
                _validate_zip_members(archive)

    def test_installer_rejects_wrong_bundle_id_or_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            app = Path(temp) / "MAW-bd.app"
            info = app / "Contents" / "Info.plist"
            info.parent.mkdir(parents=True)
            program = app / "Contents" / "MacOS" / "MAW"
            program.parent.mkdir()
            program.write_bytes(b"executable")
            info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "other", "CFBundleShortVersionString": "1.2.0"}))
            with self.assertRaises(UpdateInstallError):
                _validate_app_bundle(app, "1.2.0")
            info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.moy.maw.bdversion", "CFBundleShortVersionString": "1.1.0"}))
            with self.assertRaises(UpdateInstallError):
                _validate_app_bundle(app, "1.2.0")

    @unittest.skipUnless(sys.platform == "darwin", "macOS shell installer integration")
    def test_helper_swaps_app_after_parent_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = root / "MAW-bd.app"
            staged = root / ".MAW-bd-update-test.app"
            backup = root / ".MAW-bd-backup-test.app"
            result = root / "result.txt"
            current.mkdir()
            staged.mkdir()
            (current / "version").write_text("old", encoding="utf-8")
            (staged / "version").write_text("new", encoding="utf-8")
            helper = Path(__file__).resolve().parents[1] / "maw" / "update_install.sh"
            subprocess.run(
                ["/bin/sh", str(helper), "99999999", str(current), str(staged), str(backup), str(result), "--no-open"],
                check=True, timeout=5,
            )
            self.assertEqual((current / "version").read_text(encoding="utf-8"), "new")
            self.assertEqual((backup / "version").read_text(encoding="utf-8"), "old")
            self.assertTrue(result.read_text(encoding="utf-8").startswith("ok|"))

    def test_digest_mismatch_never_replaces_installed_app(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = root / "MAW-bd.app"
            app.mkdir()
            (app / "marker").write_text("old", encoding="utf-8")
            payload = b"untrusted archive"
            release = {
                "available": True,
                "latestVersion": "1.2.0",
                "assetName": "MAW-bd-1.2.0-macOS-arm64.zip",
                "downloadUrl": "https://github.com/Swing233/MAW-bd/releases/download/v1.2.0/MAW-bd-1.2.0-macOS-arm64.zip",
                "assetDigest": "sha256:" + hashlib.sha256(b"different").hexdigest(),
                "assetSize": len(payload),
            }

            class Stream:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return None

                def __init__(self):
                    self.sent = False

                def read(self, _size):
                    if self.sent:
                        return b""
                    self.sent = True
                    return payload

            with (
                patch("maw.app_update.update_cache_root", return_value=root / "cache"),
                patch("maw.app_update.urllib.request.urlopen", return_value=Stream()),
            ):
                with self.assertRaisesRegex(UpdateInstallError, "SHA-256"):
                    stage_update(release, current_app=app)
            self.assertEqual((app / "marker").read_text(encoding="utf-8"), "old")
            self.assertEqual(list(root.glob(".MAW-bd-update-*.app")), [])


if __name__ == "__main__":
    unittest.main()
