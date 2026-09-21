"""GitHub Release update checks."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from maw.app_update import UpdateCheckError, check_latest_release, is_newer_version, version_key


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
                }
            ],
        }
        with patch("maw.app_update.urllib.request.urlopen", return_value=_Response(payload)):
            result = check_latest_release("1.0.1")
        self.assertTrue(result["available"])
        self.assertEqual(result["latestVersion"], "1.1.0")
        self.assertEqual(result["assetSize"], 42)
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


if __name__ == "__main__":
    unittest.main()
