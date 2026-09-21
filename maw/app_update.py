"""Safe GitHub Release checks for the focused MAW-bd macOS app."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Final

REPOSITORY: Final = "Swing233/MAW-bd"
LATEST_RELEASE_API: Final = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
LATEST_RELEASE_PAGE: Final = f"https://github.com/{REPOSITORY}/releases/latest"
RELEASE_TAG_PREFIX: Final = f"https://github.com/{REPOSITORY}/releases/tag/"
ASSET_URL_PREFIX: Final = f"https://github.com/{REPOSITORY}/releases/download/"
MAX_RESPONSE_BYTES: Final = 1024 * 1024
_VERSION_RE: Final = re.compile(r"^v?(\d+)(?:\.(\d+))(?:\.(\d+))(?:\.(\d+))?$")


class UpdateCheckError(RuntimeError):
    """The update service could not return a trustworthy latest release."""


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
    assets = payload.get("assets")
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            url = str(item.get("browser_download_url") or "")
            if name.endswith("macOS-arm64.zip") and url.startswith(ASSET_URL_PREFIX):
                asset_name = name
                download_url = url
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
        "notes": notes,
        "publishedAt": str(payload.get("published_at") or ""),
    }
