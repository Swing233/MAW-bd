import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from maw.app_update import ASSET_URL_PREFIX, UpdateInstallError, _download_release


class MirrorTests(unittest.TestCase):
    def test_mirror_error_and_hash_mismatch_fall_back_to_official(self):
        payload = b"official file"
        requests = []
        transfers = []
        def open_url(request, **kwargs):
            requests.append(request.full_url)
            self.assertNotIn("Authorization", request.headers)
            if request.full_url.startswith("https://ghfast.top/"):
                raise OSError("unavailable")
            return io.BytesIO(b"tampered file" if request.full_url.startswith("https://gh-proxy.org/") else payload)
        with tempfile.TemporaryDirectory() as temp, patch("maw.app_update.urllib.request.urlopen", side_effect=open_url):
            path = Path(temp) / "asset"
            url = ASSET_URL_PREFIX + "v1.6.0/MAW-bd-1.6.0-macOS-arm64.zip"
            _download_release(url, len(payload), hashlib.sha256(payload).hexdigest(), path,
                              lambda *_: None, transfers.append, "full", "auto")
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(requests, ["https://ghfast.top/" + url, "https://gh-proxy.org/" + url, url])
            self.assertEqual(transfers[-1]["sourceLabel"], "GitHub 直连")

    def test_direct_skips_mirrors_and_invalid_source_is_rejected(self):
        url = ASSET_URL_PREFIX + "v1.6.0/asset.zip"
        with patch("maw.app_update._download_archive") as download:
            _download_release(url, 1, "hash", Path("unused"), lambda *_: None, None, "incremental", "github")
            self.assertEqual(download.call_args.args[0], url)
            download.assert_called_once()
            for source in ("http://custom.invalid", "unknown"):
                with self.assertRaises(UpdateInstallError):
                    _download_release(url, 1, "hash", Path("unused"), lambda *_: None, None, "full", source)

    def test_all_sources_fail_without_accepting_a_bad_package(self):
        with patch("maw.app_update._download_archive", side_effect=UpdateInstallError("bad hash")) as download:
            with self.assertRaisesRegex(UpdateInstallError, "所有下载线路"):
                _download_release(ASSET_URL_PREFIX + "v1.6.0/asset.zip", 1, "hash", Path("unused"), lambda *_: None, None, "full", "ghproxy")
            self.assertEqual(download.call_count, 3)
