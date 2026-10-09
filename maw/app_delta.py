"""File-level signed-app deltas; no writes to the running app."""
from __future__ import annotations

import base64
import ctypes
import sys
import hashlib
import json
import os
import plistlib
import posixpath
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 3 * 1024**3


def signing_attributes(path: Path) -> dict:
    if sys.platform != "darwin":
        return {}
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    libc.listxattr.restype = libc.getxattr.restype = ctypes.c_ssize_t
    name = os.fsencode(path)
    size = libc.listxattr(name, None, 0, 0)
    if size < 0:
        raise OSError(ctypes.get_errno(), "无法读取签名属性")
    buffer = ctypes.create_string_buffer(size)
    if libc.listxattr(name, buffer, size, 0) < 0:
        raise OSError(ctypes.get_errno(), "无法读取签名属性")
    result = {}
    for key in buffer.raw.split(b"\0"):
        if not key.startswith(b"com.apple.cs."):
            continue
        length = libc.getxattr(name, key, None, 0, 0, 0)
        if length < 0 or length > 1024 * 1024:
            raise ValueError("签名属性大小无效")
        value = ctypes.create_string_buffer(length)
        if libc.getxattr(name, key, value, length, 0, 0) != length:
            raise OSError(ctypes.get_errno(), "无法读取签名属性")
        result[key.decode("ascii")] = base64.b64encode(value.raw).decode("ascii")
    return result


def set_signing_attribute(path: Path, key: str, value: bytes) -> None:
    if sys.platform != "darwin":
        raise ValueError("签名属性需要 macOS")
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    if libc.setxattr(os.fsencode(path), key.encode("ascii"), value, len(value), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "无法写入签名属性")


def snapshot(app: Path) -> dict:
    records = {}
    for root, dirs, files in os.walk(app, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(root) / name
            key = path.relative_to(app).as_posix()
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                record = {"kind": "link", "target": os.readlink(path)}
            elif path.is_dir():
                record = {"kind": "dir", "mode": mode}
            elif path.is_file():
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                record = {"kind": "file", "mode": mode, "size": path.stat().st_size, "sha256": digest}
            else:
                raise ValueError("应用包含不支持的文件类型")
            if not path.is_symlink():
                attrs = signing_attributes(path)
                if attrs:
                    record["signingAttributes"] = attrs
            records[key] = record
    validate_records(records)
    return records


def validate_records(records: dict) -> None:
    if not isinstance(records, dict) or len(records) > 100000:
        raise ValueError("增量文件清单无效")
    total = 0
    for name, record in records.items():
        if not isinstance(name, str):
            raise ValueError("增量路径无效")
        parts = PurePosixPath(name).parts
        if not parts or name != "/".join(parts) or any(p in {".", ".."} for p in parts) or name.startswith("/") or "\\" in name:
            raise ValueError("增量包路径无效")
        if not isinstance(record, dict):
            raise ValueError("增量文件记录无效")
        for parent in PurePosixPath(name).parents:
            if str(parent) != "." and records.get(str(parent), {}).get("kind") != "dir":
                raise ValueError("增量路径穿过非目录")
        attrs = record.get("signingAttributes", {})
        if not isinstance(attrs, dict) or len(attrs) > 16:
            raise ValueError("增量签名属性无效")
        for key, encoded in attrs.items():
            if not isinstance(key, str) or not key.startswith("com.apple.cs.") or not isinstance(encoded, str) or len(encoded) > 1024 * 1024:
                raise ValueError("增量签名属性无效")
            total += len(base64.b64decode(encoded, validate=True))
        kind = record.get("kind")
        if kind == "link":
            if attrs:
                raise ValueError("符号链接不能携带签名属性")
            target = record.get("target")
            if not isinstance(target, str) or target.startswith("/") or "\\" in target:
                raise ValueError("增量符号链接无效")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if resolved == ".." or resolved.startswith("../"):
                raise ValueError("增量链接指向应用外")
        elif kind in {"file", "dir"}:
            mode = record.get("mode")
            if type(mode) is not int or not 0 <= mode <= 0o777:
                raise ValueError("增量权限无效")
            if kind == "file":
                size = record.get("size")
                digest = record.get("sha256")
                if type(size) is not int or size < 0 or not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise ValueError("增量文件摘要无效")
                total += size
        else:
            raise ValueError("增量文件类型无效")
    if total > MAX_BYTES:
        raise ValueError("增量目标过大")


def bundle_version(app: Path) -> str:
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "com.moy.maw.bdversion":
        raise ValueError("应用标识不匹配")
    return info["CFBundleShortVersionString"]


def build_delta(base: Path, target: Path, output: Path) -> dict:
    before, after = snapshot(base), snapshot(target)
    manifest = {"schema": 1, "fromVersion": bundle_version(base), "toVersion": bundle_version(target), "base": before, "target": after}
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        for name, record in after.items():
            if record["kind"] == "file" and record != before.get(name):
                archive.write(target / name, "files/" + name)
    return manifest


def apply_delta(base: Path, archive_path: Path, destination: Path, from_version: str, to_version: str) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 100001 or len({i.filename for i in entries}) != len(entries) or sum(i.file_size for i in entries) > MAX_BYTES:
            raise ValueError("增量归档无效或过大")
        if archive.getinfo("manifest.json").file_size > 32 * 1024**2:
            raise ValueError("增量清单过大")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("增量清单无效")
        if manifest.get("schema") != 1 or manifest.get("fromVersion") != from_version or manifest.get("toVersion") != to_version:
            raise ValueError("增量版本不匹配")
        before, after = manifest["base"], manifest["target"]
        validate_records(before)
        validate_records(after)
        if bundle_version(base) != from_version or snapshot(base) != before:
            raise ValueError("本机应用与增量基础版本不一致")
        changed = {"files/" + name for name, rec in after.items() if rec["kind"] == "file" and rec != before.get(name)}
        if {i.filename for i in entries} != changed | {"manifest.json"}:
            raise ValueError("增量负载与清单不一致")
        destination.mkdir()
        for name in sorted(after, key=lambda n: (len(PurePosixPath(n).parts), n)):
            rec = after[name]
            path = destination / name
            if rec["kind"] == "dir":
                path.mkdir()
            elif rec["kind"] == "file":
                if "files/" + name in changed:
                    entry = archive.getinfo("files/" + name)
                    if entry.file_size != rec["size"]:
                        raise ValueError("增量文件大小不匹配")
                    with archive.open(entry) as source, path.open("wb") as output:
                        shutil.copyfileobj(source, output)
                else:
                    shutil.copyfile(base / name, path)
                path.chmod(rec["mode"])
        # Links come last: payload writes never follow a link.
        for name, rec in after.items():
            if rec["kind"] == "link":
                (destination / name).symlink_to(rec["target"])
        for name, rec in after.items():
            for key, encoded in rec.get("signingAttributes", {}).items():
                set_signing_attribute(destination / name, key, base64.b64decode(encoded, validate=True))
        for name, rec in after.items():
            if rec["kind"] == "dir":
                (destination / name).chmod(rec["mode"])
        if snapshot(destination) != after or bundle_version(destination) != to_version:
            raise ValueError("重建应用校验失败")
