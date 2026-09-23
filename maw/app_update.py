"""Safe GitHub Release checks for the focused MAW-bd macOS app."""

from __future__ import annotations

import json
import hashlib
import os
import posixpath
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
import urllib.error
import urllib.request
from typing import Final

REPOSITORY: Final = "Swing233/MAW-bd"
LATEST_RELEASE_API: Final = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
LATEST_RELEASE_PAGE: Final = f"https://github.com/{REPOSITORY}/releases/latest"
RELEASE_TAG_PREFIX: Final = f"https://github.com/{REPOSITORY}/releases/tag/"
ASSET_URL_PREFIX: Final = f"https://github.com/{REPOSITORY}/releases/download/"
MAX_RESPONSE_BYTES: Final = 1024 * 1024
MAX_ARCHIVE_BYTES: Final = 800 * 1024 * 1024
MAX_UNPACKED_BYTES: Final = 3 * 1024 * 1024 * 1024
EXPECTED_BUNDLE_ID: Final = "com.moy.maw.bdversion"
APP_NAME: Final = "MAW-bd.app"
_VERSION_RE: Final = re.compile(r"^v?(\d+)(?:\.(\d+))(?:\.(\d+))(?:\.(\d+))?$")
_DIGEST_RE: Final = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


class UpdateCheckError(RuntimeError):
    """The update service could not return a trustworthy latest release."""


class UpdateInstallError(RuntimeError):
    """An update cannot be safely installed."""


def version_key(value: str) -> tuple[int, int, int, int]:
    """Return a comparable numeric key for stable MAW-bd release versions."""

    match = _VERSION_RE.fullmatch(str(value or "").strip())
    if match is None:
        raise ValueError(f"不支持的版本号：{value}")
    parts = [int(part or 0) for part in match.groups()]
    return tuple(parts)  # type: ignore[return-value]


def is_newer_version(candidate: str, current: str) -> bool:
    return version_key(candidate) > version_key(current)


def check_latest_release(current_version: str, *, timeout: float = 6.0) -> dict[str, object]:
    """Read the latest stable release and return a UI-safe update payload."""

    request = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"MAW-bd/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS API
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as error:
        raise UpdateCheckError(f"无法连接 GitHub：{error}") from error
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpdateCheckError("GitHub 更新响应过大")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise UpdateCheckError("GitHub 更新响应格式无效") from error
    if not isinstance(payload, dict):
        raise UpdateCheckError("GitHub 更新响应格式无效")

    tag = str(payload.get("tag_name") or "").strip()
    try:
        latest_version = tag.removeprefix("v")
        available = is_newer_version(latest_version, current_version)
    except ValueError as error:
        raise UpdateCheckError("GitHub 最新版本标签无效") from error

    release_url = RELEASE_TAG_PREFIX + tag
    asset_name = ""
    download_url = ""
    asset_size = 0
    asset_digest = ""
    assets = payload.get("assets")
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            url = str(item.get("browser_download_url") or "")
            expected_name = f"MAW-bd-{latest_version}-macOS-arm64.zip"
            expected_url = f"{ASSET_URL_PREFIX}{tag}/{expected_name}"
            if name == expected_name and url == expected_url:
                asset_name = name
                download_url = url
                digest = str(item.get("digest") or "")
                asset_digest = digest.lower() if _DIGEST_RE.fullmatch(digest) else ""
                try:
                    asset_size = max(0, int(item.get("size") or 0))
                except (TypeError, ValueError):
                    asset_size = 0
                break

    notes = str(payload.get("body") or "").strip()
    if len(notes) > 4000:
        notes = notes[:3999] + "…"
    return {
        "ok": True,
        "currentVersion": current_version,
        "latestVersion": latest_version,
        "available": available,
        "releaseUrl": release_url,
        "downloadUrl": download_url,
        "assetName": asset_name,
        "assetSize": asset_size,
        "assetDigest": asset_digest,
        "notes": notes,
        "publishedAt": str(payload.get("published_at") or ""),
    }


def current_app_bundle(executable: str | None = None) -> Path | None:
    """Find our installed app from the running executable, never a caller path."""

    path = Path(executable or sys.executable).resolve()
    for parent in path.parents:
        if parent.name == APP_NAME and path == parent / "Contents" / "MacOS" / "MAW":
            return parent
    return None


def update_cache_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "MAW" / "updates"


def update_result_path() -> Path:
    return update_cache_root() / "last-result.txt"


def read_update_result() -> str:
    """Consume the install helper's one-shot status after relaunch."""

    path = update_result_path()
    try:
        message = path.read_text(encoding="utf-8")[:500].strip()
        path.unlink(missing_ok=True)
    except (OSError, UnicodeError):
        return ""
    return message


def _validate_release_for_install(release: Mapping[str, object]) -> tuple[str, str, int, str]:
    version = str(release.get("latestVersion") or "")
    tag = f"v{version}"
    try:
        version_key(version)
    except ValueError as error:
        raise UpdateInstallError("更新版本号无效") from error
    name = f"MAW-bd-{version}-macOS-arm64.zip"
    url = f"{ASSET_URL_PREFIX}{tag}/{name}"
    digest = str(release.get("assetDigest") or "")
    size = release.get("assetSize")
    if release.get("available") is not True or release.get("assetName") != name or release.get("downloadUrl") != url:
        raise UpdateInstallError("没有可信的新版 macOS 安装包")
    if not _DIGEST_RE.fullmatch(digest):
        raise UpdateInstallError("新版缺少 SHA-256 校验值，无法自动安装")
    if not isinstance(size, int) or not 0 < size <= MAX_ARCHIVE_BYTES:
        raise UpdateInstallError("安装包大小无效")
    return version, url, size, digest.split(":", 1)[1].lower()


def _validate_zip_members(archive: zipfile.ZipFile) -> None:
    total = 0
    for member in archive.infolist():
        name = member.filename
        parts = PurePosixPath(name).parts
        if (not parts or parts[0] not in {APP_NAME, "__MACOSX"}
                or name.startswith("/") or any(part in {".", ".."} for part in parts)):
            raise UpdateInstallError("安装包包含不安全的路径")
        if ((member.external_attr >> 16) & 0o170000) == 0o120000:
            try:
                target = archive.read(member).decode("utf-8", errors="strict")
            except UnicodeError as error:
                raise UpdateInstallError("安装包符号链接无效") from error
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if parts[0] != APP_NAME or not resolved.startswith(APP_NAME + "/"):
                raise UpdateInstallError("安装包包含指向应用外的符号链接")
        total += member.file_size
        if total > MAX_UNPACKED_BYTES:
            raise UpdateInstallError("解压后的安装包过大")


def _validate_app_bundle(app: Path, expected_version: str) -> None:
    try:
        with (app / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, ValueError, TypeError) as error:
        raise UpdateInstallError("新版应用缺少有效的 Info.plist") from error
    if info.get("CFBundleIdentifier") != EXPECTED_BUNDLE_ID:
        raise UpdateInstallError("新版应用标识不匹配")
    if info.get("CFBundleShortVersionString") != expected_version:
        raise UpdateInstallError("新版应用版本不匹配")
    if not (app / "Contents" / "MacOS" / "MAW").is_file():
        raise UpdateInstallError("新版应用缺少主程序")
    try:
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
            check=True, capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise UpdateInstallError("新版应用签名校验失败") from error


def _helper_source() -> Path:
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "updater" / "update_install.sh"
    return bundled if bundled.is_file() else Path(__file__).with_name("update_install.sh")


def stage_update(
    release: Mapping[str, object],
    *,
    current_app: Path | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> dict[str, str]:
    """Download, hash-check and stage a signed app next to the installed one."""

    if sys.platform != "darwin":
        raise UpdateInstallError("自动安装仅支持 macOS")
    app = current_app or current_app_bundle()
    if app is None or app.name != APP_NAME or not app.is_dir():
        raise UpdateInstallError("请从已安装的 MAW-bd.app 中运行自动更新")
    version, url, expected_size, expected_hash = _validate_release_for_install(release)
    if not os.access(app.parent, os.W_OK):
        raise UpdateInstallError("应用所在目录不可写；请将 MAW-bd.app 安装到当前用户可写的位置")
    cache = update_cache_root()
    cache.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    staged = app.parent / f".MAW-bd-update-{token}.app"
    backup = app.parent / f".MAW-bd-backup-{token}.app"
    helper = cache / f"update-{token}.sh"
    notify = progress or (lambda _percent, _message: None)
    try:
        with tempfile.TemporaryDirectory(prefix="stage-", dir=cache) as temp:
            archive_path = Path(temp) / "update.zip"
            request = urllib.request.Request(url, headers={"User-Agent": "MAW-bd-updater"})
            sha = hashlib.sha256()
            received = 0
            notify(0, "正在下载新版…")
            try:
                with urllib.request.urlopen(request, timeout=30) as response, archive_path.open("wb") as output:  # noqa: S310 - fixed release URL + digest
                    while chunk := response.read(1024 * 1024):
                        received += len(chunk)
                        if received > MAX_ARCHIVE_BYTES or received > expected_size:
                            raise UpdateInstallError("安装包大小与发布信息不符")
                        sha.update(chunk)
                        output.write(chunk)
                        notify(min(85, int(received * 85 / expected_size)), "正在下载新版…")
            except (OSError, urllib.error.URLError, TimeoutError) as error:
                raise UpdateInstallError(f"下载新版失败：{error}") from error
            if received != expected_size or sha.hexdigest() != expected_hash:
                raise UpdateInstallError("安装包 SHA-256 或大小校验失败")
            notify(88, "正在验证安装包…")
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    _validate_zip_members(archive)
            except (OSError, zipfile.BadZipFile) as error:
                raise UpdateInstallError("安装包 ZIP 格式无效") from error
            unpacked = Path(temp) / "unpacked"
            unpacked.mkdir()
            subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive_path), str(unpacked)], check=True, timeout=180)
            candidate = unpacked / APP_NAME
            _validate_app_bundle(candidate, version)
            notify(94, "正在准备替换应用…")
            subprocess.run(["/usr/bin/ditto", str(candidate), str(staged)], check=True, timeout=180)
            _validate_app_bundle(staged, version)
            shutil.copy2(_helper_source(), helper)
            helper.chmod(0o700)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        helper.unlink(missing_ok=True)
        raise
    notify(100, "新版已验证，正在重启安装…")
    return {"current": str(app), "staged": str(staged), "backup": str(backup), "helper": str(helper)}


def launch_install_helper(staged: Mapping[str, str], *, parent_pid: int | None = None) -> None:
    """Start an external helper that swaps apps only after this process exits."""

    result = update_result_path()
    result.unlink(missing_ok=True)
    subprocess.Popen(
        ["/bin/sh", staged["helper"], str(parent_pid or os.getpid()), staged["current"],
         staged["staged"], staged["backup"], str(result)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
